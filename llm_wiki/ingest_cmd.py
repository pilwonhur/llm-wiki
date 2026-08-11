"""`llm-wiki ingest` — Inbox 자료 접수 (F1.1~F1.7, F13.1).

결정적 처리: 스캔 → 해시 → 중복 검사 → 파일명 정규화 → 분류 → 이동 → manifest.
분류는 대화형 확인(기본 추정 제시)이며, 불확실하면 보류한다 (F1.5).
메타데이터의 LLM 추출은 백엔드 연동 증분에서 추가 — 현재는 파일명 기반 + 사람 확인.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .core import SOURCE_TYPES, Project, nfc, require_project, safe_name, sha256_file, today

SKIP_NAMES = {".gitkeep", ".DS_Store"}


def _guess_type(name: str) -> str:
    n = name.lower()
    if any(k in n for k in ("회의", "meeting", "minutes")):
        return "meeting"
    if any(k in n for k in ("계획서", "proposal", "제안서", "별첨")):
        return "proposal"
    if any(k in n for k in ("실험", "experiment")):
        return "experiment"
    if any(k in n for k in ("dataset", "데이터셋")):
        return "dataset"
    if n.endswith((".html", ".url")) or "clip" in n:
        return "webclip"
    return "paper"


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
             and "_qa" not in p.parts and "_requests" not in p.parts]
    if not files:
        print("10_Inbox 에 처리할 자료가 없습니다.")
        return

    done, dups, held, log = [], [], [], []
    for f in files:
        rel = f.relative_to(inbox)
        # 업로더 귀속 (F13.1): 첫 단계 하위폴더명
        uploader = nfc(rel.parts[0]) if len(rel.parts) > 1 else "unknown"
        if uploader != "unknown" and members and uploader not in members and uploader != cfg_reviewer:
            log.append(f"미등록 업로더 폴더 '{uploader}' — members.md 확인 요망 (등록은 진행)")

        digest = sha256_file(f)
        if digest in known_hashes:
            dups.append(f"{rel} (기존: {known_hashes[digest]})")
            continue

        guess = _guess_type(f.name)
        if assume_yes:
            typ = guess
        else:
            keys = "/".join(SOURCE_TYPES)
            ans = input(f"  {rel}\n    분류 [{guess}] ({keys}, h=보류): ").strip().lower()
            if ans == "h":
                held.append(str(rel))
                continue
            typ = ans if ans in SOURCE_TYPES else guess

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
        known_hashes[digest] = entry["path"]
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
    unknown = [d for d in done if "(unknown)" in d or ", unknown)" in d]
    if unknown:
        print("  주의: 업로더 미상 — 다음부터 10_Inbox/<이름>/ 폴더를 사용하세요.")
    if done:
        print("다음: `llm-wiki compile` 로 편찬하세요.")
