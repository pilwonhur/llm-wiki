"""`llm-wiki serve-mcp` — MCP stdio 서버 (F7.x). 표준 라이브러리만으로 구현.

외부 AI 비서(Claude Code·Codex·Gemini CLI·OpenClaw)가 붙는 도구 중립 창구.
쓰기 권한은 설계대로 제한된다: Wiki 본문 직접 수정 도구는 없다 —
요청 제출(wiki_request_edit)·Q&A 제출(wiki_save_qa)·코멘트 append(wiki_add_comment)뿐.
모든 질의는 관심도 로그에 실명과 함께 기록된다 (F11.1).
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

from . import search_cmd
from .core import Project, frontmatter, nfc, require_project, today

PROTOCOL_VERSION = "2024-11-05"


def _tool(name, desc, props, required):
    return {"name": name, "description": desc,
            "inputSchema": {"type": "object", "properties": props, "required": required}}


TOOLS = [
    _tool("wiki_search", "Wiki 전문 검색. approved/reviewed 우선.",
          {"query": {"type": "string"}, "include_draft": {"type": "boolean"},
           "asker": {"type": "string", "description": "질문자 실명 (필수)"}},
          ["query", "asker"]),
    _tool("wiki_read", "Wiki 문서 읽기 (30_Wiki 상대경로).",
          {"path": {"type": "string"}}, ["path"]),
    _tool("wiki_status", "프로젝트 현황 요약 (원자료·문서·검토 대기).", {}, []),
    _tool("wiki_request_edit", "Wiki 변경 요청 제출 (직접 수정 불가 — 다음 compile에서 처리).",
          {"path": {"type": "string"}, "suggestion": {"type": "string"},
           "rationale": {"type": "string"}, "author": {"type": "string"}},
          ["path", "suggestion", "author"]),
    _tool("wiki_add_comment", "문서 코멘트 섹션에 기록용 코멘트 append (본문 수정 불가).",
          {"path": {"type": "string"}, "comment": {"type": "string"},
           "author": {"type": "string"}}, ["path", "comment", "author"]),
    _tool("wiki_save_qa", "사람이 동의한 Q&A 신규 정보를 원자료 후보로 제출 (10_Inbox/_qa).",
          {"question": {"type": "string"},
           "items": {"type": "array", "items": {"type": "object", "properties": {
               "content": {"type": "string"},
               "kind": {"type": "string", "enum": ["web", "prior_knowledge", "researcher_input"]},
               "source_urls": {"type": "array", "items": {"type": "string"}}}}},
           "asker": {"type": "string"}}, ["question", "items", "asker"]),
    _tool("wiki_activity", "구성원 활동 요약 (업로드·질의·코멘트·검토).",
          {"member": {"type": "string"}}, []),
]


def _log_query(proj: Project, q: str, asker: str, hits: int) -> None:
    proj.log_query(q, asker, hits, via="mcp")


def _call(proj: Project, name: str, a: dict) -> str:
    if name == "wiki_search":
        res = search_cmd.query(proj, a["query"], include_draft=a.get("include_draft", False))
        _log_query(proj, a["query"], a.get("asker", "unknown"), len(res))
        return json.dumps(res, ensure_ascii=False, indent=1)

    if name == "wiki_read":
        p = (proj.root / a["path"]).resolve()
        wiki = (proj.root / "30_Wiki").resolve()
        if not str(p).startswith(str(wiki)) or not p.suffix == ".md" or not p.exists():
            return "오류: 30_Wiki 안의 .md 문서만 읽을 수 있습니다."
        return p.read_text(encoding="utf-8")

    if name == "wiki_status":
        m = proj.manifest()
        counts: dict = {}
        for p in proj.wiki_docs():
            s = frontmatter(p.read_text(encoding="utf-8")).get("status", "?")
            counts[s] = counts.get(s, 0) + 1
        return json.dumps({"project": proj.config().get("project"),
                           "sources": len(m["sources"]),
                           "unprocessed": sum(1 for s in m["sources"] if not s.get("processed")),
                           "wiki": counts, "proposals": len(proj.proposals())},
                          ensure_ascii=False)

    if name == "wiki_request_edit":
        d = proj.root / "10_Inbox" / "_requests"
        d.mkdir(parents=True, exist_ok=True)
        fn = d / f"{today()}-{datetime.now().strftime('%H%M%S')}-요청.md"
        fn.write_text(f"# 편찬 요청 (외부 비서 경유)\n\n- 요청자: {a['author']}\n"
                      f"- 대상: {a['path']}\n- 일시: {today()}\n\n## 제안\n{a['suggestion']}\n\n"
                      f"## 근거\n{a.get('rationale', '')}\n", encoding="utf-8")
        return f"요청 접수: {fn.relative_to(proj.root)} — 다음 compile에서 처리됩니다."

    if name == "wiki_add_comment":
        p = (proj.root / a["path"]).resolve()
        if not str(p).startswith(str((proj.root / "30_Wiki").resolve())) or not p.exists():
            return "오류: 30_Wiki 안의 문서가 아닙니다."
        text = p.read_text(encoding="utf-8")
        line = f"- {today()} **{a['author']}**: {a['comment']}"
        if "## 코멘트" in text:
            text = text.rstrip() + "\n" + line + "\n"
        else:
            text = text.rstrip() + f"\n\n## 코멘트\n\n{line}\n"
        p.write_text(text, encoding="utf-8")  # append 전용 — 본문 비수정 (F12.2)
        return "코멘트 추가 완료 (기록 전용 — 편찬 근거로 쓰이지 않음)"

    if name == "wiki_save_qa":
        d = proj.root / "10_Inbox" / "_qa"
        d.mkdir(parents=True, exist_ok=True)
        bad = [i for i in a["items"] if i.get("kind") == "web" and not i.get("source_urls")]
        if bad:
            return "오류: web 유형은 source_urls(URL) 없이는 승격 불가 (F10.3)."
        fn = d / f"{today()}-{datetime.now().strftime('%H%M%S')}-qa.md"
        body = [f"# Q&A 세션 ({today()})", f"- 질문자: {a['asker']}",
                f"- 질문: {a['question']}", ""]
        for i, it in enumerate(a["items"], 1):
            body += [f"## 항목 {i} [{it.get('kind')}]", it.get("content", ""),
                     *([f"- 출처: {u}" for u in it.get("source_urls", [])]), ""]
        fn.write_text("\n".join(body), encoding="utf-8")
        return f"저장: {fn.relative_to(proj.root)} — ingest 후 편찬 시 반영됩니다."

    if name == "wiki_activity":
        m = proj.manifest()
        acts: dict = {}
        for s in m["sources"]:
            u = s.get("added_by", "unknown")
            acts.setdefault(u, {"업로드": 0, "질의": 0, "검토": 0, "코멘트": 0})["업로드"] += 1
        qf = proj.meta / "metrics" / "queries.jsonl"
        if qf.exists():
            for ln in qf.read_text(encoding="utf-8").splitlines():
                u = json.loads(ln).get("asker", "unknown")
                acts.setdefault(u, {"업로드": 0, "질의": 0, "검토": 0, "코멘트": 0})["질의"] += 1
        import re
        for p in proj.wiki_docs():
            t = p.read_text(encoding="utf-8")
            rv = frontmatter(t).get("reviewer")
            if rv:
                acts.setdefault(str(rv), {"업로드": 0, "질의": 0, "검토": 0, "코멘트": 0})["검토"] += 1
            for mm in re.finditer(r"^- \d{4}-\d{2}-\d{2} \*\*([^*]+)\*\*", t, re.M):
                acts.setdefault(mm.group(1), {"업로드": 0, "질의": 0, "검토": 0, "코멘트": 0})["코멘트"] += 1
        member = a.get("member")
        if member:
            acts = {member: acts.get(nfc(member), {})}
        return json.dumps(acts, ensure_ascii=False, indent=1)

    return f"알 수 없는 도구: {name}"


def cmd_serve_mcp(args) -> None:
    if getattr(args, "project", None):
        root = Path(args.project).resolve()
        if not (root / ".llm-wiki").is_dir():
            raise SystemExit(f"오류: {root} 는 llm-wiki 프로젝트가 아닙니다 (.llm-wiki 없음)")
        proj = Project(root)
    else:
        proj = require_project()
    out = sys.stdout

    def send(obj):
        out.write(json.dumps(obj, ensure_ascii=False) + "\n")
        out.flush()

    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except json.JSONDecodeError:
            continue
        rid, method = req.get("id"), req.get("method", "")
        if method == "initialize":
            send({"jsonrpc": "2.0", "id": rid, "result": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "llm-wiki", "version": "0.1.0"}}})
        elif method == "tools/list":
            send({"jsonrpc": "2.0", "id": rid, "result": {"tools": TOOLS}})
        elif method == "tools/call":
            p = req.get("params", {})
            try:
                text = _call(proj, p.get("name", ""), p.get("arguments", {}) or {})
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": text}]}})
            except Exception as e:
                send({"jsonrpc": "2.0", "id": rid, "result": {
                    "content": [{"type": "text", "text": f"오류: {e}"}], "isError": True}})
        elif method == "ping":
            send({"jsonrpc": "2.0", "id": rid, "result": {}})
        elif rid is not None:  # 알 수 없는 요청
            send({"jsonrpc": "2.0", "id": rid,
                  "error": {"code": -32601, "message": f"unknown method {method}"}})
