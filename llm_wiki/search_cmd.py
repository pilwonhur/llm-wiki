"""`llm-wiki search` — 전문 검색 (F6.1~F6.2, SQLite FTS5 — 표준 라이브러리).

인덱스는 파생물이다: 언제든 Markdown에서 전체 재구축 (N2). 문서 변경 감지 시
자동 재구축하므로 별도 reindex가 필수는 아니지만 명령으로도 제공한다.
approved > reviewed > draft 순으로 우선 노출 (F7.3과 동일 정책).
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

from .core import Project, frontmatter, require_project

RANK = {"approved": 0, "reviewed": 1, "draft": 2, "disputed": 3, "deprecated": 4}

# 한국어 조사·어미를 떼고 접두 검색으로 넘긴다. FTS5의 unicode61 토크나이저는
# "근거가"와 "근거는"을 다른 토큰으로 보기 때문에, 문장형 질문은 그대로 넣으면
# 거의 0건이 된다 (ask가 이 경로를 쓴다). 형태소 분석기 없이 접미사 사전으로 근사 — 의존성 0 유지.
JOSA = ("으로부터", "에서는", "에게서", "이라고", "으로는", "에서도", "라고", "으로",
        "에서", "에게", "까지", "부터", "보다", "처럼", "마다", "조차", "이나", "와의",
        "과의", "에는", "의", "을", "를", "이", "가", "은", "는", "에", "도", "만",
        "와", "과", "로", "야",
        # 용언 어미 — "채택한/채택했다" 를 "채택*" 로 모아 접두 검색이 원형까지 잡게 한다
        "했나요", "하나요", "했었", "했다", "한다", "했던", "하는", "되는", "됐다",
        "이다", "입니다", "였다", "나요", "네요", "한", "했", "된", "됐")
STOPWORDS = {"뭐야", "뭔가", "무엇", "무엇인가", "어떻게", "어떤", "어느", "왜", "언제",
             "어디", "누구", "알려줘", "설명해줘", "정리해줘", "해줘", "인가", "인가요",
             "있나", "있나요", "하나요", "했나", "했나요", "되나", "되나요", "이란",
             "란", "대해", "대한", "관련", "그리고", "하지만", "것", "수", "때"}
MIN_STEM = 2

# 영어도 같은 방식으로 근사한다 — FTS5는 스테밍을 안 하므로 "actuators"로 물으면
# 본문의 "actuator"를 놓친다 (접두 검색은 짧은 쪽→긴 쪽만 잡아준다).
# 어간을 뽑아 접두 검색으로 넘기면 양방향이 해결된다.
# 치환("ies"→"y")이 아니라 **잘라내기만** 한다 — 접두 검색이라 글자를 바꾸면
# 원형과 접두가 어긋난다 ("series"→"sery" 는 series 를 못 잡는다).
# 자르기만 하면 어간이 원형·활용형 모두의 접두가 되어 양방향이 잡힌다.
EN_SUFFIXES = ("edness", "ments", "ings", "ment", "ness", "ies", "ing",
               "ers", "ed", "er", "es", "ly", "s")
EN_STOPWORDS = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being", "am",
    "do", "does", "did", "doing", "have", "has", "had", "of", "in", "on", "at",
    "to", "for", "from", "by", "with", "about", "into", "over", "and", "or",
    "but", "if", "then", "than", "so", "as", "that", "this", "these", "those",
    "it", "its", "they", "them", "their", "we", "our", "you", "your", "i",
    "he", "she", "his", "her", "what", "which", "who", "whom", "when", "where",
    "why", "how", "can", "could", "should", "would", "will", "shall", "may",
    "might", "must", "not", "no", "there", "here", "any", "some", "all", "me",
    "tell", "explain", "describe", "summarize", "show", "give", "please",
}
MIN_EN_STEM = 4   # 짧은 단어를 뭉개지 않게 (spring→spr, series→sery 방지)


def _en_stem(w: str) -> str:
    low = w.lower()
    for suf in EN_SUFFIXES:
        if low.endswith(suf) and len(low) - len(suf) >= MIN_EN_STEM:
            return low[: -len(suf)]
    return low


def _is_hangul(w: str) -> bool:
    return any("가" <= c <= "힣" for c in w)


def _stem(w: str) -> str:
    ordered = sorted(JOSA, key=len, reverse=True)
    for _ in range(2):          # "채택한다는" 처럼 어미+조사가 겹친 경우까지
        for j in ordered:
            if w.endswith(j) and len(w) - len(j) >= MIN_STEM:
                w = w[: -len(j)]
                break
        else:
            break
    return w


def terms(q: str) -> list[str]:
    """질문 문장 → 검색 토큰. 토큰별로 언어를 보고 처리한다 (한·영 혼용 문서 대응).

    한글: 조사·어미 제거 + 의문사 제외 / 영어: 접미사 정규화 + 불용어 제외.
    """
    out = []
    for w in re.findall(r"[0-9A-Za-z가-힣]+", q):
        if _is_hangul(w):
            if w in STOPWORDS:
                continue
            s = _stem(w)
            if s in STOPWORDS:
                continue
        elif w.isalpha():
            if w.lower() in EN_STOPWORDS:
                continue
            s = _en_stem(w)
            if s in EN_STOPWORDS:
                continue
        else:
            s = w
        if s and s not in out:
            out.append(s)
    return out


def _match(con: sqlite3.Connection, expr: str) -> list:
    try:
        return con.execute(
            "SELECT path, title, status, snippet(docs, 4, '[', ']', '…', 12) "
            "FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT 30", (expr,)).fetchall()
    except sqlite3.OperationalError:
        return []


def _index_path(proj: Project) -> Path:
    d = proj.meta / "index"
    d.mkdir(exist_ok=True)
    return d / "fts.sqlite"


def build_index(proj: Project) -> sqlite3.Connection:
    db_path = _index_path(proj)
    docs = list(proj.wiki_docs())
    newest = max((p.stat().st_mtime for p in docs), default=0)
    if db_path.exists() and db_path.stat().st_mtime >= newest:
        return sqlite3.connect(db_path)  # 최신 상태 — 재사용
    db_path.unlink(missing_ok=True)
    con = sqlite3.connect(db_path)
    con.execute("CREATE VIRTUAL TABLE docs USING fts5(path, title, aliases, status, body)")
    for p in docs:
        text = p.read_text(encoding="utf-8")
        fm = frontmatter(text)
        con.execute("INSERT INTO docs VALUES (?,?,?,?,?)", (
            str(p.relative_to(proj.root)), p.stem,
            " ".join(map(str, fm.get("aliases") or [])),
            str(fm.get("status", "")), text))
    con.commit()
    return con


def query(proj: Project, q: str, include_draft: bool = True, limit: int = 10) -> list[dict]:
    con = build_index(proj)
    rows = _match(con, '"' + q.replace('"', " ") + '"')      # ① 구문 그대로
    toks = terms(q)
    if not rows and toks:                                     # ② 어간 접두 AND (정밀)
        rows = _match(con, " AND ".join(f'"{t}"*' for t in toks))
    if not rows and toks:                                     # ③ 어간 접두 OR (재현율)
        rows = _match(con, " OR ".join(f'"{t}"*' for t in toks))
    if not rows:                                              # ④ 원형 그대로 OR
        rows = _match(con, " OR ".join(f'"{w}"' for w in q.split() if w))
    out = [{"path": r[0], "title": r[1], "status": r[2], "snippet": r[3]} for r in rows]
    if not include_draft:
        out = [r for r in out if r["status"] in ("approved", "reviewed")]
    out.sort(key=lambda r: RANK.get(r["status"], 9))
    return out[:limit]


def cmd_search(args) -> None:
    proj = require_project()
    results = query(proj, " ".join(args.query), include_draft=not args.no_draft)
    if not results:
        print("검색 결과 없음")
        return
    for r in results:
        print(f"[{r['status']}] {r['title']}  ({r['path']})")
        print(f"    {r['snippet']}")


def cmd_reindex(args) -> None:
    proj = require_project()
    _index_path(proj).unlink(missing_ok=True)
    build_index(proj)
    print("✓ 인덱스 재구축 완료 (.llm-wiki/index/fts.sqlite)")
