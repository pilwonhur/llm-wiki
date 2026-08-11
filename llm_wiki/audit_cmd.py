"""`llm-wiki audit` — 품질 감사 (F5.x). 문서를 수정하지 않는다 — 보고만.

Phase 0 audit 워크플로우의 검사 항목을 결정적 코드로 이관:
링크(NFC 비교)·페이지 범위·status·코멘트·규칙파일·충돌 사본·manifest 정합.
LLM이 필요한 검사(중복 의심·모순 탐지)는 백엔드 증분에서 추가.
"""
from __future__ import annotations

import re
import subprocess
import sys
from datetime import date, datetime
from pathlib import Path

from .core import STATUS_VALUES, frontmatter, nfc, require_project, today

WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:#page=(\d+))?[^\]]*\]\]")


def _pdf_pages(path: Path) -> int | None:
    """PDF 페이지 수 — macOS Spotlight 우선, 실패 시 None (범위 검사 생략)."""
    if sys.platform == "darwin":
        try:
            out = subprocess.run(["mdls", "-name", "kMDItemNumberOfPages", "-raw", str(path)],
                                 capture_output=True, text=True, timeout=10).stdout.strip()
            if out.isdigit():
                return int(out)
        except Exception:
            pass
    try:  # pypdf가 있으면 사용 (선택 의존성)
        from pypdf import PdfReader  # type: ignore
        return len(PdfReader(str(path)).pages)
    except Exception:
        return None


def cmd_audit(args) -> None:
    proj = require_project()
    cfg = proj.config()
    stale_days = int((cfg.get("review") or {}).get("stale_draft_days", 14) or 14)

    docs = list(proj.wiki_docs())
    titles = {nfc(p.stem) for p in docs}
    source_files = {nfc(p.name): p for p in (proj.root / "20_Sources").rglob("*") if p.is_file()}
    pdf_pages = {name: _pdf_pages(p) for name, p in source_files.items() if name.endswith(".pdf")}

    broken, rangeerr, nosrc, badstatus, stale, badcomment, warnings = [], [], [], [], [], [], []
    cite_total = 0
    for p in docs:
        rel = str(p.relative_to(proj.root / "30_Wiki"))
        text = p.read_text(encoding="utf-8")
        fm = frontmatter(text)
        status = fm.get("status")
        if status not in STATUS_VALUES:
            badstatus.append(f"{rel} (status: {status!r})")
        if status == "draft":
            try:
                created = date.fromisoformat(str(fm.get("created")))
                if (date.today() - created).days >= stale_days:
                    stale.append(f"{rel} ({(date.today() - created).days}일)")
            except (TypeError, ValueError):
                pass
        if "근거 확인 필요" in text or "검증 필요" in text:
            warnings.append(rel)
        # 코멘트 형식: 항목이 있으면 날짜·실명 굵게 요구
        cm = re.search(r"##\s*코멘트\n(.*)$", text, re.S)
        if cm:
            for line in cm.group(1).splitlines():
                if line.strip().startswith("- ") and not re.match(
                        r"- \d{4}-\d{2}-\d{2} \*\*[^*]+\*\*", line.strip()):
                    badcomment.append(f"{rel}: {line.strip()[:40]}")
        if not re.search(r"##\s*근거\s*\n+\s*-\s*\[\[", text):
            nosrc.append(rel)
        for m in WIKILINK.finditer(text):
            target, page = nfc(m.group(1).strip()), m.group(2)
            if target.startswith("20_Sources"):
                cite_total += 1
                fname = nfc(Path(target).name)
                if fname not in source_files:
                    broken.append(f"{rel} → {target}")
                elif page and pdf_pages.get(fname) and int(page) > pdf_pages[fname]:
                    rangeerr.append(f"{rel} → {fname}#page={page} (실제 {pdf_pages[fname]}쪽)")
            elif target not in titles:
                broken.append(f"{rel} → [[{target}]]")

    conflicts = [str(p.relative_to(proj.root)) for p in proj.root.rglob("*")
                 if "conflicted copy" in p.name or "충돌" in p.name]
    manifest = proj.manifest()
    missing = [s["path"] for s in manifest["sources"] if not (proj.root / s["path"]).exists()]
    claude_md = (proj.root / "CLAUDE.md")
    dup_rules = (claude_md.exists() and claude_md.read_text(encoding="utf-8").strip() != "@AGENTS.md")
    unchecked_pdfs = [n for n, v in pdf_pages.items() if v is None]

    checks = [
        ("깨진 wikilink", broken),
        ("페이지 범위 초과 인용", rangeerr),
        ("출처 없는 문서", nosrc),
        ("status 이상", badstatus),
        (f"장기 방치 draft ({stale_days}일+)", stale),
        ("코멘트 형식 오류", badcomment),
        ("동기화 충돌 사본", conflicts),
        ("manifest 원자료 불일치", missing),
        ("규칙 파일 이중화", ["CLAUDE.md에 import 외 내용"] if dup_rules else []),
    ]
    total_issues = sum(len(v) for _, v in checks)

    # 리포트 작성
    rid = datetime.now().strftime("%Y-%m-%d-%H%M")
    report = [f"# 감사 리포트 — {today()} (CLI)", "",
              f"대상: 30_Wiki {len(docs)}개 문서, 원자료 인용 {cite_total}건 "
              f"(범위 검사: PDF {len(pdf_pages) - len(unchecked_pdfs)}/{len(pdf_pages)}건 페이지 수 확인). "
              "문서 수정 없음.", "", "| 검사 | 건수 |", "|---|---|"]
    for name, items in checks:
        report.append(f"| {name} | {len(items)} |")
    report.append(f"| 검증 필요 표시 잔존 (참고) | {len(warnings)} |")
    for name, items in checks:
        if items:
            report += ["", f"## {name}"] + [f"- {i}" for i in items]
    if warnings:
        report += ["", "## 검증 필요 표시 잔존 (오류 아님 — 원자료 대기)"] + [f"- {w}" for w in warnings]
    if unchecked_pdfs:
        report += ["", f"## 페이지 수 미확인 PDF (범위 검사 생략): {', '.join(unchecked_pdfs)}"]
    out = proj.meta / "audit" / f"{rid}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text("\n".join(report) + "\n", encoding="utf-8")

    proj.log("audit 실행 (CLI)", [f"리포트: {out.relative_to(proj.root)}",
                                  f"발견 {total_issues}건, 검증 필요 표시 {len(warnings)}건"])
    print(f"✓ 감사 완료 — 발견 {total_issues}건 (리포트: {out.relative_to(proj.root)})")
    for name, items in checks:
        if items:
            print(f"  [{name}] {len(items)}건")
            for i in items[:5]:
                print(f"    - {i}")
    if total_issues == 0:
        print("  전 항목 이상 없음.")
    if warnings:
        print(f"  참고: 검증 필요 표시 {len(warnings)}건 (미등록 원자료 대기 — 오류 아님)")
