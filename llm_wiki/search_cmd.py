"""`llm-wiki search` — 전문 검색 (F6.1~F6.2, SQLite FTS5 — 표준 라이브러리).

인덱스는 파생물이다: 언제든 Markdown에서 전체 재구축 (N2). 문서 변경 감지 시
자동 재구축하므로 별도 reindex가 필수는 아니지만 명령으로도 제공한다.
approved > reviewed > draft 순으로 우선 노출 (F7.3과 동일 정책).
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

from .core import Project, frontmatter, require_project

RANK = {"approved": 0, "reviewed": 1, "draft": 2, "disputed": 3, "deprecated": 4}


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
    safe = '"' + q.replace('"', " ") + '"'
    try:
        rows = con.execute(
            "SELECT path, title, status, snippet(docs, 4, '[', ']', '…', 12) "
            "FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT 30", (safe,)).fetchall()
    except sqlite3.OperationalError:
        rows = []
    if not rows:  # 구문 검색 실패 시 단순 OR 검색
        terms = " OR ".join(w for w in q.split() if w)
        try:
            rows = con.execute(
                "SELECT path, title, status, snippet(docs, 4, '[', ']', '…', 12) "
                "FROM docs WHERE docs MATCH ? ORDER BY rank LIMIT 30", (terms,)).fetchall()
        except sqlite3.OperationalError:
            rows = []
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
