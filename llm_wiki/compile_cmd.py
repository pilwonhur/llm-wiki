"""`llm-wiki compile` — 내장 편찬 파이프라인 (F2.x).

CLI가 큐·안전장치·검증·기록을 담당하고, LLM은 문서 내용만 만든다:
  자료별로 [편찬 프롬프트] → LLM → [JSON 문서 목록] → 코드 수준 검증 → 쓰기.

코드 수준 강제 (프롬프트가 아니라 여기서 막는다):
  - 쓰기 경로는 30_Wiki 안으로 제한 (N1)
  - 생성·갱신 문서의 status는 무조건 draft로 강제 (F2.9)
  - 대상 문서가 reviewed 이상이면 update를 propose로 강등 (규칙 3)
  - 기존 문서의 "## 코멘트" 섹션은 갱신 시 원본 그대로 보존 (F12.1)
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from . import backends
from .core import (LANG_NAME, WARN_TEXT, Project, field_pattern, frontmatter,
                   heading, heading_pattern, lang_of, nfc, require_project,
                   run_id, today, unique_path)

PROTOCOL_HEAD = """
출력은 반드시 아래 JSON 배열 **하나만** 출력하라 (설명·마크다운 펜스 금지):
[
  {"action": "create" | "update" | "propose",
   "path": "30_Wiki/<하위폴더>/<문서명>.md",
   "content": "<문서 전체 Markdown (frontmatter 포함, 템플릿 준수)>"}
]
- create: 새 문서. update: 기존 draft 문서의 전체 교체본. propose: reviewed 이상
  문서에 대한 변경 제안 (content는 '현재 내용/제안 내용/근거' 구조의 제안서).
- 기존 문서 내용을 확실히 모르면 update 대신 propose를 선택하라.
- 모든 핵심 주장에 [[원자료경로#page=N]] 인용 (PDF는 물리 페이지 번호).
"""


def _protocol(lang: str) -> str:
    """JSON 예시에 중괄호가 있어 f-string으로 만들 수 없다 — 상수 + 언어별 꼬리."""
    warn = WARN_TEXT[lang][0]
    return PROTOCOL_HEAD + (
        f'- 근거를 못 찾은 서술은 "> [!warning] {warn}" callout.\n'
        f'- 자료가 기존 Wiki와 모순되면 임의로 고르지 말고 '
        f'"## {heading(lang, "conflict")}"에 양측 기록.\n'
        f'- **문서 본문과 섹션 제목은 {LANG_NAME[lang]}로 쓴다.** 섹션 제목은 템플릿의 것을\n'
        f'  글자 그대로 사용하라 — 코드가 이 제목으로 코멘트 보존·출처 검사를 수행한다.\n')


def _wiki_index(proj: Project) -> str:
    rows = []
    for p in proj.wiki_docs():
        fm = frontmatter(p.read_text(encoding="utf-8"))
        rows.append(f"- {p.relative_to(proj.root)} | status={fm.get('status')} | "
                    f"aliases={fm.get('aliases', [])}")
    return "\n".join(rows) or "(아직 문서 없음)"


def _read_context(proj: Project) -> str:
    parts = []
    for name in ("scope.md", "glossary.md"):
        p = proj.root / "00_Project" / name
        if p.exists():
            parts.append(f"### 00_Project/{name}\n{p.read_text(encoding='utf-8')[:4000]}")
    return "\n\n".join(parts)


def _source_text(proj: Project, src: dict, agentic: bool) -> str | None:
    """자료 본문. 에이전트형 백엔드는 경로만 주면 스스로 읽는다."""
    p = proj.root / src["path"]
    if agentic:
        return None  # 프롬프트에 경로만 포함
    if p.suffix.lower() in (".md", ".txt"):
        return p.read_text(encoding="utf-8", errors="replace")[:60000]
    if p.suffix.lower() == ".pdf":
        try:
            from pypdf import PdfReader  # 선택 의존성 [pdf]
            return "\n".join(f"[물리 페이지 {i+1}]\n" + (pg.extract_text() or "")
                             for i, pg in enumerate(PdfReader(str(p)).pages))[:120000]
        except ImportError:
            raise backends.BackendError(
                f"{p.name}: API/Ollama 백엔드로 PDF를 처리하려면 pypdf가 필요합니다 "
                "(pipx inject llm-wiki pypdf). OAuth(Claude CLI) 백엔드는 불필요.")
    return None


def _build_prompt(proj: Project, src: dict, index: str, ctx: str,
                  template: str, agentic: bool, text: str | None,
                  lang: str = "ko") -> str:
    src_block = (f"원자료 파일: {src['path']} — 이 파일을 직접 읽어라 (인용 페이지는 "
                 "PDF 물리 페이지 번호를 실제 확인). 프로젝트 폴더 밖은 읽지 마라."
                 if agentic else
                 f"원자료 ({src['path']}) 본문:\n<<<\n{text}\n>>>")
    return f"""너는 연구실 Wiki 편찬자다. 아래 원자료 1건을 근거로 지식 문서를 편찬한다.

## 프로젝트 맥락
{ctx}

## 기존 Wiki 색인 (중복 생성 금지 — 같은 개념·다른 표기는 aliases와 대조)
{index}

## 원자료 메타데이터
제목: {src.get('title')} / 저자: {src.get('authors')} / 연도: {src.get('year')} / 종류: {src.get('type')}

{src_block}

## 문서 템플릿 (정확히 준수)
{template}

## 규칙
- status는 draft만. 코멘트 섹션은 절대 건드리지 않는다. 배경지식 서술에는
  "(모델 배경지식 — 검증 필요)" 표시. 프로젝트 자료 기반 내용과 명확히 구분.
- 이 자료에서 나올 문서는 보통 1~4건이다. 억지로 늘리지 마라.
- 출력 언어: **{LANG_NAME[lang]}** (전문 용어는 첫 등장 시 원문 병기).
{_protocol(lang)}"""


def _extract_json(text: str):
    m = re.search(r"\[.*\]", text, re.S)
    if not m:
        raise ValueError("응답에서 JSON 배열을 찾지 못함")
    return json.loads(m.group(0))


def _force_draft(content: str) -> str:
    content = re.sub(r"^status:.*$", "status: draft", content, count=1, flags=re.M)
    content = re.sub(r"^reviewer:.*$", "reviewer:", content, count=1, flags=re.M)
    return content


def _apply(proj: Project, rid: str, items: list, report: list) -> None:
    for it in items:
        action = it.get("action")
        rel = nfc(str(it.get("path", "")))
        content = it.get("content", "")
        target = (proj.root / rel).resolve()
        # N1: 경로 화이트리스트 — 30_Wiki 밖 쓰기 차단
        if not str(target).startswith(str((proj.root / "30_Wiki").resolve())):
            report.append(f"차단: 30_Wiki 밖 쓰기 시도 ({rel})")
            continue
        if action == "propose" or "_Proposals" in rel:
            name = Path(rel).stem.split("-2")[0]
            target = proj.root / "30_Wiki" / "_Proposals" / f"{name}-{rid}.md"
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8")
            report.append(f"제안: {target.relative_to(proj.root)}")
            continue
        content = _force_draft(content)  # F2.9 코드 강제
        if target.exists():
            old = target.read_text(encoding="utf-8")
            old_fm = frontmatter(old)
            if old_fm.get("status") not in (None, "draft"):
                # 규칙 3: reviewed 이상 → 제안으로 강등
                target = proj.root / "30_Wiki" / "_Proposals" / f"{Path(rel).stem}-{rid}.md"
                target.parent.mkdir(parents=True, exist_ok=True)
                lang = lang_of(proj.config())
                target.write_text(f"# 변경 제안: [[{Path(rel).stem}]] (자동 강등)\n\n"
                                  f"대상이 {old_fm.get('status')} 상태라 직접 수정 불가.\n\n"
                                  f"## {heading(lang, 'prop_full')}\n\n{content}",
                                  encoding="utf-8")
                report.append(f"제안(강등): {target.relative_to(proj.root)}")
                continue
            # F12.1: 기존 코멘트 섹션 보존
            cm_re = rf"##\s*(?:{heading_pattern('comments')})\s*\n"
            oc = re.search(rf"({cm_re}.*)$", old, re.S)
            if oc:
                content = re.sub(rf"{cm_re}.*$", "", content, flags=re.S).rstrip()
                content += "\n\n" + oc.group(1)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(content, encoding="utf-8")
        report.append(f"{'갱신' if action == 'update' else '생성'}: {target.relative_to(proj.root)}")


# ---------------------------------------------------------------- 편찬 요청 (F7.x)
def pending_requests(proj: Project) -> list[Path]:
    d = proj.root / "10_Inbox" / "_requests"
    return sorted(p for p in d.glob("*.md")) if d.exists() else []


def _parse_request(text: str) -> dict:
    """요청 파일 파싱 (MCP wiki_request_edit 형식, 사람이 쓴 변형도 관대하게)."""
    def fld(key):
        m = re.search(rf"^-\s*(?:{field_pattern(key)})\s*:\s*(.+)$", text, re.M)
        return m.group(1).strip() if m else ""

    def section(key):
        m = re.search(rf"^##\s*(?:{heading_pattern(key)})\s*$(.*?)(?=^##\s|\Z)",
                      text, re.M | re.S)
        return m.group(1).strip() if m else ""

    suggestion = section("req_suggestion")
    return {"author": fld("requester") or "unknown",
            "target": fld("target"),
            "suggestion": suggestion or text.strip(),
            "rationale": section("req_rationale")}


def _process_requests(proj: Project, rid: str, report: list) -> tuple[int, int]:
    """`10_Inbox/_requests/` 의 변경 요청을 `_Proposals` 제안으로 변환한다.

    외부 비서는 Wiki를 직접 못 고친다 — 요청은 반드시 사람의 `review apply` 를 거친다.
    그래서 여기서는 LLM을 부르지 않고 제안서만 결정적으로 만든다 (병합은 review apply의 몫).
    """
    reqs = pending_requests(proj)
    if not reqs:
        return 0, 0
    lang = lang_of(proj.config())
    wiki = (proj.root / "30_Wiki").resolve()
    prop_dir = proj.root / "30_Wiki" / "_Proposals"
    archive = proj.root / "90_Archive" / "_requests"
    done = held = 0
    for f in reqs:
        r = _parse_request(f.read_text(encoding="utf-8", errors="replace"))
        rel = nfc(r["target"])
        target = (proj.root / rel).resolve() if rel else None
        # N1: 대상은 30_Wiki 안의 기존 문서여야 한다 (요청으로 새 문서를 만들지 않는다)
        if not rel or not str(target).startswith(str(wiki)) or not target.exists():
            report.append(f"요청 보류: {f.name} — 대상 문서를 찾지 못함 ({rel or '대상 미기재'})")
            held += 1
            continue
        status = frontmatter(target.read_text(encoding="utf-8")).get("status", "draft")
        # 같은 문서에 요청이 여러 건이면 제안서도 여러 개여야 한다 (덮어쓰기 금지)
        out = unique_path(prop_dir, f"{target.stem}-{rid}")
        out.write_text(
            f"---\ntarget: {target.relative_to(proj.root)}\n"
            f"requested_by: {r['author']}\nstatus_at_request: {status}\n"
            f"created: {today()}\nsource_request: {f.relative_to(proj.root)}\n---\n\n"
            f"# 변경 제안: [[{target.stem}]]\n\n"
            f"외부 비서 경유 요청 ({r['author']}) — 사람이 `llm-wiki review apply` 로 승인해야 반영된다.\n\n"
            f"## {heading(lang, 'prop_current')}\n"
            f"대상 문서 `{target.relative_to(proj.root)}` (status: {status}) 참조.\n\n"
            f"## {heading(lang, 'prop_new')}\n{r['suggestion']}\n\n"
            f"## {heading(lang, 'prop_reason')}\n"
            f"{r['rationale'] or '(요청자가 근거를 적지 않음 — 승인 전 확인 필요)'}\n",
            encoding="utf-8")
        archive.mkdir(parents=True, exist_ok=True)
        shutil.move(str(f), archive / f.name)   # 처리 흔적 보존 (재처리 방지)
        report.append(f"요청→제안: {f.name} → {out.relative_to(proj.root)} ({r['author']})")
        done += 1
    return done, held


def cmd_compile(args) -> None:
    proj = require_project()
    cfg = proj.config()
    m = proj.manifest()
    todo = [s for s in m["sources"] if not s.get("processed")]
    reqs = pending_requests(proj)
    if not todo and not reqs:
        print("처리할 자료가 없습니다 (manifest 전부 processed, 대기 중인 편찬 요청도 없음).")
        return

    # 요청만 있으면 LLM이 필요 없다 — 백엔드 없이도 처리되게 한다
    backend = backends.resolve(cfg, "compile") if todo else None
    agentic = backend.agentic if backend else False  # 에이전트형은 원자료를 스스로 읽는다
    keep = int((cfg.get("snapshot") or {}).get("backup_keep", 10) or 10)
    template = (proj.meta / "templates" / "wiki-doc.md").read_text(encoding="utf-8") \
        if (proj.meta / "templates" / "wiki-doc.md").exists() else ""

    proj.acquire_lock("compile")
    rid = run_id()
    try:
        proj.backup(rid, keep=keep)
        head = f"✓ 백업 {rid}"
        if todo:
            head += f" | 백엔드 {backend.describe()} | 대상 {len(todo)}건"
        if reqs:
            head += f" | 편찬 요청 {len(reqs)}건"
        print(head)
        ctx = _read_context(proj)
        report, failures, usage_total = [], [], {"input": 0, "output": 0, "cost_usd": 0.0}

        # 편찬 요청 → 제안 변환 (LLM 불필요, 사람의 review apply 를 거친다)
        req_done, req_held = _process_requests(proj, rid, report)
        for src in todo:  # 순차 큐 (F2.1) — 실패해도 다음 파일 진행
            name = Path(src["path"]).name
            try:
                index = _wiki_index(proj)  # 문서가 늘어나므로 매 파일 갱신
                text = _source_text(proj, src, agentic)
                prompt = _build_prompt(proj, src, index, ctx, template, agentic,
                                       text, lang_of(cfg))
                print(f"  · {name} 편찬 중...")
                out, usage = backend.complete(prompt, cwd=proj.root)
                items = _extract_json(out)
                _apply(proj, rid, items, report)
                src["processed"] = True
                proj.save_manifest(m)  # 파일 단위로 저장 — 중단 시 이어서 (C9)
                for k in ("input", "output"):
                    if usage.get(k):
                        usage_total[k] += usage[k]
                if usage.get("cost_usd"):
                    usage_total["cost_usd"] += usage["cost_usd"]
            except Exception as e:  # 실패 격리 (C8)
                failures.append(f"{name}: {e}")
                print(f"    실패: {e}")

        # 비용 기록 (N3)
        cost_line = (f"토큰 in {usage_total['input']} / out {usage_total['output']}"
                     + (f" / ${usage_total['cost_usd']:.4f}" if usage_total["cost_usd"] else ""))
        (proj.meta / "metrics").mkdir(exist_ok=True)
        if todo:
            with open(proj.meta / "metrics" / "costs.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"run": rid, "backend": backend.name, "model": backend.model,
                                    "sources": len(todo) - len(failures), **usage_total},
                                   ensure_ascii=False) + "\n")

        via = f"{backend.name}/{backend.model}" if backend else "요청 처리만"
        proj.log(f"compile 실행 (CLI, {rid}, {via})",
                 report + [f"실패 {len(failures)}건: " + "; ".join(failures)] * bool(failures)
                 + [cost_line])
        tail = (f"\n✓ 편찬 완료 — 산출 {len(report) - req_held}건, "
                f"실패 {len(failures)}건, {cost_line}")
        if req_done or req_held:
            tail += f"\n  편찬 요청: 제안 전환 {req_done}건" + (f", 보류 {req_held}건" if req_held else "")
        if req_held:
            tail += ("\n  보류 요청은 10_Inbox/_requests/ 에 남습니다 — 대상 경로를 고치거나 "
                     "파일을 지우세요.")
        print(tail)
        for r in report:
            print(f"  - {r}")
        if failures:
            print("  실패: " + "; ".join(failures))
        print(f"검토: `llm-wiki review` / 변경 확인: `llm-wiki diff {rid}` / 복원: `llm-wiki rollback {rid}`")
    finally:
        proj.release_lock()
