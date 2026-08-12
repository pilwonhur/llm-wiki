"""`llm-wiki ask` — Wiki에 근거해 질문에 답한다 (F6.3, MCP 없이 터미널에서).

검색(FTS5)으로 근거 문서를 고르고, 그 발췌만 프롬프트에 넣어 백엔드에 묻는다.
RAG처럼 매번 원자료를 다시 읽는 게 아니라 **이미 편찬된 Wiki**를 근거로 답한다.

코드 수준 강제 (프롬프트 신뢰 금지):
  - 근거는 30_Wiki 문서에서만 뽑는다 — 원자료·Inbox는 쓰지 않는다
  - 답변은 어디에도 쓰지 않는다. Wiki 수정 경로는 compile·review 뿐이다 (N1)
  - Q&A 승격은 '모델 배경지식' 항목만, 사람의 명시 동의 후 10_Inbox/_qa/ 로만
    (Wiki 요약의 재유입 = AI 자기 참조 순환을 코드에서 차단)
  - 모든 질의는 실명과 함께 관심도 로그에 남는다 (F11.1)
"""
from __future__ import annotations

import os
import re
import sys
from datetime import datetime
from pathlib import Path

from . import backends, search_cmd
from .core import (LANG_NAME, Project, field, heading, heading_pattern,
                   lang_of, require_project, today, unique_path)

DOC_CHARS = 6000        # 문서 하나에서 프롬프트에 넣을 최대 길이
TOTAL_CHARS = 40000     # 근거 전체 상한

PROMPT = """너는 연구실 Wiki 질의응답 도우미다. 아래 **Wiki 발췌만을 근거로** 질문에 답한다.

## 질문
{question}

## Wiki 발췌 (근거 — 이것 말고 다른 자료는 없다)
{context}

## 규칙
- Wiki 발췌로 뒷받침되는 내용만 본문에 쓰고, 문장 끝마다 근거 번호를 붙여라: [1], [2]
- 발췌에 없으면 없다고 말하라. 지어내지 마라.
- 발췌만으로 부족해 배경지식을 덧붙여야 한다면, 본문과 분리해 맨 끝에 이 제목으로 모아라:
  {bg}
  이 섹션의 각 항목은 `- ` 로 시작하는 한 줄짜리 사실 진술이어야 한다 (검증 가능한 형태).
  덧붙일 배경지식이 없으면 이 섹션 자체를 쓰지 마라.
- status가 draft인 근거를 쓸 때는 해당 문장에 (draft) 를 표시하라 — 미검토 내용이다.
- 답변 언어: **{lang_name}**. 군더더기 없이. 인사말·요약 재진술 금지."""

NO_CONTEXT_PROMPT = """너는 연구실 Wiki 질의응답 도우미다.
아래 질문에 대해 **Wiki에서 근거 문서를 하나도 찾지 못했다**.

## 질문
{question}

## 규칙
- 첫 줄에 "Wiki에 근거 문서가 없습니다." 라고 명시하라.
- 그 다음 배경지식으로 답할 수 있는 부분만 아래 제목 아래에 모아라:
  {bg}
  각 항목은 `- ` 로 시작하는 한 줄짜리 사실 진술.
- 프로젝트 고유 사실(실험값·결정·인물)은 배경지식으로 답할 수 없다. 모른다고 하라.
- 답변 언어: **{lang_name}**. 군더더기 없이."""


def _asker(args) -> str:
    """질의 귀속 실명 — 관심도 로그와 Q&A 승격에 함께 기록된다."""
    return (args.asker or os.environ.get("LLM_WIKI_ASKER")
            or os.environ.get("USER") or "unknown")


def _context(proj: Project, hits: list[dict]) -> tuple[str, list[dict]]:
    """검색 결과 → 번호 매긴 근거 블록. 30_Wiki 밖은 애초에 인덱스에 없다."""
    blocks, used, total = [], [], 0
    for i, h in enumerate(hits, 1):
        p = proj.root / h["path"]
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        text = text[:DOC_CHARS]
        if total + len(text) > TOTAL_CHARS:
            break
        total += len(text)
        blocks.append(f"[{i}] {h['path']}  (status: {h['status']})\n<<<\n{text}\n>>>")
        used.append(h)
    return "\n\n".join(blocks), used


def _bg_items(answer: str) -> list[str]:
    """답변에서 '모델 배경지식' 섹션의 항목만 뽑는다 — 승격 후보는 이것뿐이다."""
    m = re.search(rf"^#{{1,6}}\s*(?:{heading_pattern('background')})\s*$", answer, re.M)
    if not m:
        return []
    tail = answer[m.end():]
    tail = re.split(r"\n#{1,6} ", tail)[0]          # 다음 제목 전까지
    return [ln.strip()[2:].strip() for ln in tail.splitlines()
            if ln.strip().startswith(("- ", "* "))]


def _save_qa(proj: Project, question: str, asker: str, items: list[str]) -> Path:
    """MCP wiki_save_qa와 동일한 형식·경로 — ingest → compile 이 이어받는다."""
    fn = unique_path(proj.root / "10_Inbox" / "_qa",
                     f"{today()}-{datetime.now().strftime('%H%M%S')}-qa")
    lg = lang_of(proj.config())
    body = [f"# Q&A ({today()})", f"- {field(lg, 'asker')}: {asker}",
            f"- {field(lg, 'question')}: {question}",
            f"- {field(lg, 'via')}: llm-wiki ask", ""]
    for i, it in enumerate(items, 1):
        body += [f"## {heading(lg, 'item')} {i} [prior_knowledge]", it, ""]
    fn.write_text("\n".join(body), encoding="utf-8")
    return fn


def _consent(proj: Project, question: str, asker: str, items: list[str], args) -> None:
    """항목별 명시 동의 — 동의한 것만 원자료 후보가 된다 (F10.x)."""
    if not items or args.no_save_qa:
        return
    if not args.save_qa and not sys.stdin.isatty():
        print(f"\n(배경지식 {len(items)}건 — 저장하려면 --save-qa)")
        return
    chosen = items
    if not args.save_qa:
        print(f"\n위 답변의 '모델 배경지식' {len(items)}건은 Wiki 근거가 아닙니다.")
        print("원자료 후보로 저장하면 다음 편찬에서 검토를 거쳐 반영됩니다.")
        chosen = []
        for it in items:
            ans = input(f"  저장할까요? [y/N] {it[:70]}{'…' if len(it) > 70 else ''}\n  > ").strip().lower()
            if ans in ("y", "yes", "ㅇ"):
                chosen.append(it)
        if not chosen:
            print("저장하지 않았습니다.")
            return
    fn = _save_qa(proj, question, asker, chosen)
    print(f"\n✓ {len(chosen)}건 저장: {fn.relative_to(proj.root)}")
    print("  다음: `llm-wiki ingest` → `llm-wiki compile` 로 Wiki에 반영됩니다.")


def cmd_ask(args) -> None:
    proj = require_project()
    question = " ".join(args.question).strip()
    if not question:
        raise SystemExit("질문을 입력하세요: llm-wiki ask \"발목 강성은 어떻게 정했나\"")
    asker = _asker(args)

    cfg = proj.config()
    lang = lang_of(cfg)
    bg = f"## {heading(lang, 'background')}"
    hits = search_cmd.query(proj, question, include_draft=not args.no_draft,
                            limit=args.top)
    context, used = _context(proj, hits)
    backend = backends.resolve(cfg, "compile")

    if used:
        prompt = PROMPT.format(question=question, context=context, bg=bg,
                               lang_name=LANG_NAME[lang])
        print(f"근거 {len(used)}건 · 백엔드 {backend.describe()}\n")
    else:
        prompt = NO_CONTEXT_PROMPT.format(question=question, bg=bg,
                                          lang_name=LANG_NAME[lang])
        print(f"Wiki 근거 0건 · 백엔드 {backend.describe()}")
        print("(검색으로 관련 문서를 찾지 못했습니다 — 배경지식만으로 답합니다)\n")

    answer, usage = backend.complete(prompt, cwd=proj.root)
    answer = answer.strip()
    print(answer)

    if used:
        print("\n근거")
        for i, h in enumerate(used, 1):
            print(f"  [{i}] {h['path']}  ({h['status']})")
        if any(h["status"] == "draft" for h in used):
            print("  ! draft 근거가 포함됐습니다 — 미검토 내용입니다.")

    proj.log_query(question, asker, len(used), via="ask", model=backend.model,
                   input=usage.get("input"), output=usage.get("output"),
                   cost_usd=usage.get("cost_usd"))
    if usage.get("input") or usage.get("output"):
        print(f"\n토큰 in {usage.get('input') or 0} / out {usage.get('output') or 0}"
              + (f" / ${usage['cost_usd']:.4f}" if usage.get("cost_usd") else ""))

    _consent(proj, question, asker, _bg_items(answer), args)
