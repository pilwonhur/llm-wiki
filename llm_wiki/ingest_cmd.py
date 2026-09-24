"""`llm-wiki ingest` — Inbox 자료 접수 (F1.1~F1.7, F13.1).

결정적 처리: 스캔 → 해시 → 중복 검사 → 파일명 정규화 → 분류 → 이동 → manifest.
분류는 대화형 확인(기본 추정 제시)이며, 추정에 확신이 없으면 기본값이 보류다 (F1.5).
메타데이터의 LLM 추출은 백엔드 연동 증분에서 추가 — 현재는 파일명 기반 + 사람 확인.
"""
from __future__ import annotations

import re
import shutil
from pathlib import Path

from .core import (SOURCE_TYPES, Project, field_pattern, nfc, require_project,
                   safe_name, sha256_file, today)

SKIP_NAMES = {".gitkeep", ".DS_Store"}


HOLD = "h"  # 분류 추정 불가 — 이동하지 않고 Inbox에 둔다 (F1.5)

# 파일명 키워드. 검사 순서가 우선순위다 — "기획회의"는 meeting, "회사소개서"는 reference.
_KEYWORDS = (
    ("meeting", ("회의", "meeting", "minutes")),
    ("reference", ("회사소개", "소개서", "카탈로그", "catalog", "brochure", "datasheet",
                   "사양서", "규격", "보도자료")),
    ("proposal", ("계획서", "proposal", "제안서", "별첨", "양식", "과제", "사업", "기획")),
    ("experiment", ("실험", "experiment")),
    ("dataset", ("dataset", "데이터셋")),
)
# paper는 긍정 신호가 있을 때만 — 예전에는 모든 미분류 파일이 paper로 떨어졌다
_PAPER_NAME = re.compile(
    r"arxiv|(?<![a-z])doi(?![a-z])|et[ _.]?al\b|논문|journal|proceedings|\b\d{4}\.\d{4,5}(?:v\d+)?\b"
    r"|^[a-z]{2,}[ _-]?(?:19|20)\d{2}(?!\d)")
_PAPER_BODY = re.compile(r"doi\.org/|\bdoi:\s*10\.|\barxiv:\s*\d")
_MAIL_HEADER = re.compile(r"^(?:from|to|cc|subject|date|보낸\s?사람|받는\s?사람|참조|제목)\s*:",
                          re.M)
TEXT_EXTS = (".md", ".markdown", ".txt", ".html", ".htm", ".eml")


def _frontmatter(head: str) -> str:
    m = re.match(r"---\n(.*?)\n---", head, re.S)
    return m.group(1) if m else ""


def _fm_tags(fm: str) -> set[str]:
    """frontmatter의 tags/type 값 (인라인 `[a, b]`·쉼표·목록형 모두)."""
    m = re.search(r"^(?:tags|type)\s*:(.*(?:\n\s+-.*)*)", fm, re.M)
    return set(re.findall(r"[\w가-힣-]+", m.group(1))) if m else set()


def _guess_type(name: str, head: str = "") -> str:
    """분류 추정. 확신이 없으면 HOLD — 추측으로 옮기지 않는다.

    `head`는 텍스트 파일의 앞부분(없으면 파일명만 본다). PDF 본문은 읽지 않는다.
    """
    # macOS·Dropbox는 한글 파일명을 NFD로 돌려준다 — 정규화 없이는 한글 키워드가 맞지 않는다
    n = nfc(name).lower()
    h = nfc(head).lower()
    fm = _frontmatter(h)
    tags = _fm_tags(fm)
    if tags & {"meeting", "meeting-minutes", "minutes", "회의록", "회의"}:
        return "meeting"
    for typ, keys in _KEYWORDS:
        if any(k in n for k in keys):
            return typ
    if (n.endswith((".html", ".htm", ".url")) or "clip" in n
            or re.search(r"^(?:source|url)\s*:\s*[\"']?https?://", fm, re.M)):
        return "webclip"
    if _PAPER_NAME.search(n):
        return "paper"
    if h and len(_MAIL_HEADER.findall(h)) < 2 and _PAPER_BODY.search(h):
        return "paper"
    return HOLD


def _head(path: Path, size: int = 8000) -> str:
    if path.suffix.lower() not in TEXT_EXTS:
        return ""
    try:
        with path.open("r", encoding="utf-8", errors="replace") as fh:
            return fh.read(size)
    except OSError:
        return ""


def _qa_asker(path: Path) -> str:
    """Q&A 제출물의 귀속은 폴더가 아니라 파일에 적힌 질문자다 (F10.x 실명 귀속)."""
    head = path.read_text(encoding="utf-8", errors="replace")
    m = re.search(rf"^-\s*(?:{field_pattern('asker')})\s*:\s*(.+)$", head, re.M)
    return nfc(m.group(1).strip()) if m and m.group(1).strip() else "unknown"


def _members(proj: Project) -> set[str]:
    p = proj.root / "00_Project" / "members.md"
    names = set()
    if p.exists():
        for line in p.read_text(encoding="utf-8").splitlines():
            if line.startswith("|") and "---" not in line and "이름" not in line:
                cell = line.split("|")[1].strip()
                if cell and "TODO" not in cell:
                    names.add(nfc(cell))
    return names


def cmd_ingest(args) -> None:
    proj = require_project()
    proj.acquire_lock("ingest")
    try:
        _ingest(proj, assume_yes=args.yes)
    finally:
        proj.release_lock()


def _ingest(proj: Project, assume_yes: bool) -> None:
    inbox = proj.root / "10_Inbox"
    manifest = proj.manifest()
    known_hashes = {s["hash"]: s["path"] for s in manifest["sources"]}
    members = _members(proj)
    cfg_reviewer = (proj.config().get("review") or {}).get("reviewer", "")

    files = [p for p in sorted(inbox.rglob("*"))
             if p.is_file() and p.name not in SKIP_NAMES
             and not p.name.startswith(".") and not p.name.endswith("-회의록초안.md")
             and "_requests" not in p.parts]   # _requests는 편찬 요청이라 원자료가 아니다
    if not files:
        print("10_Inbox 에 처리할 자료가 없습니다.")
        return

    done, dups, held, log = [], [], [], []
    plan = []  # (파일, rel, uploader, digest, typ) — 1차: 분류 확정만, 파일은 건드리지 않는다
    seen = dict(known_hashes)
    for f in files:
        rel = f.relative_to(inbox)
        # Q&A 제출물(ask·MCP wiki_save_qa)은 분류가 정해져 있고 귀속은 질문자다
        is_qa = "_qa" in rel.parts
        if is_qa:
            uploader = _qa_asker(f)
        else:
            # 업로더 귀속 (F13.1): 첫 단계 하위폴더명
            uploader = nfc(rel.parts[0]) if len(rel.parts) > 1 else "unknown"
        if uploader != "unknown" and members and uploader not in members and uploader != cfg_reviewer:
            log.append(f"미등록 업로더 '{uploader}' — members.md 확인 요망 (등록은 진행)")

        digest = sha256_file(f)
        if digest in seen:
            dups.append(f"{rel} (기존: {seen[digest]})")
            continue
        seen[digest] = str(rel)

        guess = "qa" if is_qa else _guess_type(f.name, _head(f))
        if assume_yes or is_qa:
            typ = guess
        else:
            keys = "/".join(SOURCE_TYPES)
            try:
                ans = input(f"  {rel}\n    분류 [{guess}] ({keys}, h=보류): ").strip().lower()
            except EOFError:
                # 비대화형(에이전트·cron)에서 답이 모자라면 아무것도 옮기지 않고 끝낸다
                raise SystemExit(
                    "\n입력이 끊겼습니다 — 이동·등록된 파일은 없습니다.\n"
                    "비대화형 실행은 `llm-wiki ingest --yes`(추정 분류 수용)를 쓰거나 "
                    "분류 답을 표준입력으로 넘기세요.")
            typ = ans or guess
            if typ not in SOURCE_TYPES and typ != HOLD:
                print(f"    알 수 없는 분류 '{ans}' — 보류합니다.")
                typ = HOLD
        if typ == HOLD:
            held.append(f"{rel} (분류 미정)" if assume_yes else str(rel))
            continue
        plan.append((f, rel, uploader, digest, typ))

    # 2차: 이동 + 등록. 파일마다 manifest를 저장해 중간에 죽어도 미등록 원자료가 남지 않는다
    for f, rel, uploader, digest, typ in plan:
        new_name = safe_name(f.name)  # F1.7
        dest_dir = proj.root / "20_Sources" / SOURCE_TYPES[typ]
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / new_name
        if dest.exists():  # 동명이인 파일 — 덮어쓰기 금지
            held.append(f"{rel} (동일 이름이 이미 존재: {dest.relative_to(proj.root)})")
            continue
        shutil.move(str(f), dest)
        entry = {
            "path": str(dest.relative_to(proj.root)),
            "hash": digest,
            "title": dest.stem,          # LLM 메타데이터 추출 전까지 잠정값
            "authors": "", "year": None,
            "type": typ,
            "added": today(), "added_by": uploader,
            "processed": False,
        }
        if new_name != nfc(f.name):
            entry["original_name"] = nfc(f.name)
            log.append(f"파일명 정규화: {f.name} → {new_name}")
        manifest["sources"].append(entry)
        proj.save_manifest(manifest)
        done.append(f"{rel} → {entry['path']} ({typ}, {uploader})")

        # 업로더 하위폴더가 비면 유지 (다음 업로드용), 파일만 이동됨

    proj.save_manifest(manifest)
    lines = ([f"등록 {len(done)}건:"] + [f"  {d}" for d in done]
             + ([f"중복 {len(dups)}건: " + "; ".join(dups)] if dups else [])
             + ([f"보류 {len(held)}건: " + "; ".join(held)] if held else []) + log)
    proj.log("ingest 실행 (CLI)", lines)
    print(f"\n✓ 등록 {len(done)} / 중복 {len(dups)} / 보류 {len(held)}")
    for d in done:
        print(f"  - {d}")
    if dups:
        print("  중복(미이동): " + "; ".join(dups))
    if held:
        print("  보류(Inbox 유지): " + "; ".join(held))
        if assume_yes:
            print("  분류를 정하려면 `llm-wiki ingest`(대화형)로 다시 실행하세요.")
    unknown = [d for d in done if "(unknown)" in d or ", unknown)" in d]
    if unknown:
        print("  주의: 업로더 미상 — 다음부터 10_Inbox/<이름>/ 폴더를 사용하세요.")
    if done:
        print("다음: `llm-wiki compile` 로 편찬하세요.")
