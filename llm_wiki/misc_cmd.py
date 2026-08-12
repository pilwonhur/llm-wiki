"""review / status / rollback / diff / models / compile(브리지) 명령."""
from __future__ import annotations

import difflib
from datetime import date
from pathlib import Path

from .core import (GLOBAL_REGISTRY, Project, dump_yamlish, frontmatter,
                   require_project, run_id, today)

REGISTRY = GLOBAL_REGISTRY


# ---------------------------------------------------------------- review (F4.2~F4.3)
def cmd_review(args) -> None:
    if getattr(args, "action", None) in ("apply", "reject"):
        _review_act(args)
        return
    proj = require_project()
    drafts, disputed = [], []
    for p in proj.wiki_docs():
        fm = frontmatter(p.read_text(encoding="utf-8"))
        rel = str(p.relative_to(proj.root / "30_Wiki"))
        if fm.get("status") == "draft":
            drafts.append((fm.get("created", ""), rel))
        elif fm.get("status") == "disputed":
            disputed.append(rel)
    props = [str(p.name) for p in proj.proposals()]

    if not (drafts or props or disputed):
        print("검토 대기 항목이 없습니다. ✓")
        return
    if drafts:
        print(f"검토 대기 draft {len(drafts)}건 (오래된 순):")
        for created, rel in sorted(drafts):
            print(f"  - {rel} (생성 {created})")
    if props:
        print(f"변경 제안 {len(props)}건 (30_Wiki/_Proposals/):")
        for name in props:
            print(f"  - {name}")
        print("  → 승인: 제안 내용을 원문서에 반영 후 제안 파일 삭제 / 거부: 사유 남기고 삭제")
    if disputed:
        print(f"disputed 판정 대기 {len(disputed)}건: " + ", ".join(disputed))
    print("\n검토 방법: 문서의 근거 링크를 원문과 대조 → frontmatter status를 reviewed로 편집")


def _review_act(args) -> None:
    """제안 승인(apply)·거부(reject) — F4.3.

    apply는 사람이 명령을 실행했다는 사실 자체가 승인이다. 병합문은 LLM이 만들되,
    코드가 강제한다: status·reviewer는 원문 유지(사람 부여값), 코멘트 섹션 보존,
    반영 전 백업. 실패·비정상 병합 시 원문 무변경.
    """
    import re as _re

    from . import backends
    from .core import nfc

    proj = require_project()
    if getattr(args, "all", False) and args.action == "apply":
        props = proj.proposals()
        if not props:
            print("대기 중인 제안이 없습니다.")
            return
        print(f"다음 제안 {len(props)}건을 모두 승인·반영합니다:")
        for p in props:
            print(f"  - {p.name}")
        try:
            ok = input("진행할까요? [y/N]: ").strip().lower() in ("y", "yes")
        except EOFError:
            ok = True  # 비대화형(스크립트·에이전트 경유)은 명령 실행 자체를 승인으로 간주
        if not ok:
            print("취소됨")
            return
        done, failed = 0, []
        for p in props:
            try:
                _apply_one(proj, p)
                done += 1
            except SystemExit as e:
                failed.append(f"{p.name}: {e}")
        print(f"\n✓ 일괄 반영 {done}건" + (f" / 실패 {len(failed)}건" if failed else ""))
        for f in failed:
            print(f"  실패: {f}")
        return

    if not args.proposal:
        raise SystemExit("사용법: llm-wiki review apply|reject <제안 파일명(일부)> 또는 apply --all")
    matches = [p for p in proj.proposals() if nfc(args.proposal) in nfc(p.name)]
    if len(matches) != 1:
        names = ", ".join(p.name for p in proj.proposals()) or "(없음)"
        raise SystemExit(f"제안을 특정하지 못했습니다 (매칭 {len(matches)}건). 보유: {names}")
    prop = matches[0]

    if args.action == "reject":
        proj.log("제안 거부 (review reject)", [f"{prop.name} — 사유: {args.reason or '미기재'}"])
        prop.unlink()
        print(f"✓ 거부·정리: {prop.name}" + (f" (사유: {args.reason})" if args.reason else ""))
        return

    _apply_one(proj, prop)


def _apply_one(proj, prop) -> None:
    import re as _re

    from . import backends
    from .core import nfc

    prop_text = prop.read_text(encoding="utf-8")
    m = _re.search(r'target:\s*"?([^"\n]+)"?', prop_text)
    target = proj.root / m.group(1).strip() if m else None
    if not target or not target.exists():
        # frontmatter에 target이 없으면 파일명에서 유추
        stem = _re.sub(r"-\d{8}-\d{6}$", "", prop.stem)
        cands = [p for p in proj.wiki_docs() if nfc(p.stem) == nfc(stem)]
        if len(cands) != 1:
            raise SystemExit(f"대상 문서를 찾지 못했습니다 ({prop.name}). 수동 반영이 필요합니다.")
        target = cands[0]

    old = target.read_text(encoding="utf-8")
    old_fm = frontmatter(old)
    proj.acquire_lock("review-apply")
    rid = run_id()
    try:
        proj.backup(rid)
        backend = backends.resolve(proj.config(), "compile")
        prompt = f"""아래 [제안]을 [원문서]에 반영한 문서 전체를 출력하라.
규칙: 제안된 변경만 반영하고 나머지는 그대로 유지. frontmatter의 status·reviewer·created는
원문 값 그대로. "## 코멘트" 섹션은 원문 그대로. updated는 {today()}로.
출력은 병합된 문서 전문만 (설명·펜스 금지, `---`로 시작).

[원문서: {target.relative_to(proj.root)}]
{old}

[제안: {prop.name}]
{prop_text}"""
        merged, usage = backend.complete(prompt, cwd=proj.root)
        merged = merged.strip()
        if merged.startswith("```"):
            merged = _re.sub(r"^```[a-z]*\n|\n```$", "", merged)
        # 코드 수준 강제: status·reviewer 원문 유지, 코멘트 섹션 원문 보존
        if not merged.startswith("---"):
            raise SystemExit("병합 결과가 문서 형식이 아닙니다 — 원문 무변경, 수동 반영 요망.")
        merged = _re.sub(r"^status:.*$", f"status: {old_fm.get('status', 'draft')}",
                         merged, count=1, flags=_re.M)
        merged = _re.sub(r"^reviewer:.*$", f"reviewer: {old_fm.get('reviewer', '')}",
                         merged, count=1, flags=_re.M)
        oc = _re.search(r"(## 코멘트\n.*)$", old, _re.S)
        if oc:
            merged = _re.sub(r"## 코멘트\n.*$", "", merged, flags=_re.S).rstrip() + "\n\n" + oc.group(1)
        target.write_text(merged, encoding="utf-8")
        prop.unlink()
        proj.log("제안 승인·반영 (review apply)",
                 [f"{prop.name} → {target.relative_to(proj.root)} (백업 {rid})"])
        print(f"✓ 반영 완료: {target.relative_to(proj.root)} (status {old_fm.get('status')} 유지)")
        print(f"  확인: llm-wiki diff {rid} / 되돌리기: llm-wiki rollback {rid}")
    finally:
        proj.release_lock()


# ---------------------------------------------------------------- status
def cmd_status(args) -> None:
    proj = require_project()
    m = proj.manifest()
    unprocessed = [s for s in m["sources"] if not s.get("processed")]
    counts: dict = {}
    for p in proj.wiki_docs():
        s = frontmatter(p.read_text(encoding="utf-8")).get("status", "?")
        counts[s] = counts.get(s, 0) + 1
    cfg = proj.config()
    print(f"프로젝트: {cfg.get('project')} (root: {proj.root})")
    print(f"원자료: {len(m['sources'])}건 (미처리 {len(unprocessed)}건)")
    print(f"Wiki: " + ", ".join(f"{k} {v}" for k, v in sorted(counts.items())) or "없음")
    print(f"제안 대기: {len(proj.proposals())}건 / 백업: {len(proj.list_backups())}회분")
    if unprocessed:
        print("미처리 자료: " + ", ".join(Path(s["path"]).name for s in unprocessed[:5]))


# ---------------------------------------------------------------- rollback / diff (F3.2~F3.3)
def cmd_rollback(args) -> None:
    proj = require_project()
    backups = proj.list_backups()
    rid = args.run_id or (backups[-1] if backups else None)
    if not rid:
        raise SystemExit("백업이 없습니다.")
    proj.acquire_lock("rollback")
    try:
        proj.backup(run_id() + "-pre-rollback")  # 롤백 자체도 되돌릴 수 있게
        proj.rollback(rid)
        proj.log("rollback (CLI)", [f"{rid} 시점으로 30_Wiki·manifest 복원"])
        print(f"✓ {rid} 시점으로 복원 완료 (직전 상태도 백업해 두었습니다)")
    finally:
        proj.release_lock()


def cmd_diff(args) -> None:
    proj = require_project()
    backups = proj.list_backups()
    if not backups:
        raise SystemExit("백업이 없습니다 — 아직 compile 실행 전입니다.")
    rid = args.run_id or backups[-1]
    base = proj.meta / "backups" / rid / "30_Wiki"
    cur = proj.root / "30_Wiki"
    old = {p.relative_to(base): p for p in base.rglob("*.md")} if base.exists() else {}
    new = {p.relative_to(cur): p for p in cur.rglob("*.md")}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(r for r in set(new) & set(old)
                     if new[r].read_bytes() != old[r].read_bytes())
    print(f"기준: 백업 {rid}")
    for label, items in (("추가", added), ("삭제", removed), ("변경", changed)):
        for r in items:
            print(f"  {label}: {r}")
    if args.verbose and changed:
        for r in changed:
            diff = difflib.unified_diff(
                old[r].read_text(encoding="utf-8").splitlines(),
                new[r].read_text(encoding="utf-8").splitlines(),
                lineterm="", n=1)
            print(f"\n--- {r}")
            print("\n".join(list(diff)[2:20]))
    if not (added or removed or changed):
        print("  변경 없음")


# ---------------------------------------------------------------- setup-agent
def cmd_setup_agent(args) -> None:
    """전역 에이전트 어댑터 설치 — 경로 걱정 없이 어디서든 실행 가능.

    Claude Code: 전역 /wiki-init 스킬 (~/.claude/skills/) — 프로젝트 스킬은 init이 설치.
    Codex: /wiki-init·ingest·compile·audit 프롬프트 (~/.codex/prompts/) — Codex는
    프로젝트 프롬프트를 자동 인식하지 않으므로 전역 1회 설치가 4개 명령 전부를 커버.
    """
    import shutil as _sh

    src = Path(__file__).parent / "templates" / "agents"
    tool = args.tool
    done = []
    if tool in ("claude", "all"):
        dst = Path.home() / ".claude" / "skills"
        dst.mkdir(parents=True, exist_ok=True)
        _sh.copytree(src / "claude" / "wiki-init", dst / "wiki-init", dirs_exist_ok=True)
        done.append(f"Claude Code: 전역 /wiki-init 스킬 → {dst / 'wiki-init'}")
    if tool in ("codex", "all"):
        dst = Path.home() / ".codex" / "prompts"
        dst.mkdir(parents=True, exist_ok=True)
        names = []
        for f in sorted((src / "codex").glob("*.md")):
            _sh.copy2(f, dst / f.name)
            names.append(f"/{f.stem}")
        done.append(f"Codex: {' '.join(names)} 프롬프트 → {dst}")
    if tool in ("agy", "all"):
        # Antigravity CLI 전역 스킬 디렉터리 (프로젝트 스킬은 init이 .agents/skills/ 에 설치)
        dst = Path.home() / ".gemini" / "antigravity-cli" / "skills"
        dst.mkdir(parents=True, exist_ok=True)
        names = []
        for f in sorted((src / "agy").glob("*.md")):
            _sh.copy2(f, dst / f.name)
            names.append(f"/{f.stem}")
        done.append(f"Antigravity(agy): {' '.join(names)} 스킬 → {dst}")
    for d in done:
        print(f"✓ {d}")
    print("설치는 컴퓨터당 1회면 충분합니다. 업데이트 후에는 다시 실행하면 갱신됩니다.")


# ---------------------------------------------------------------- models (F8.4)
def _save_registry(reg: dict) -> None:
    REGISTRY.parent.mkdir(parents=True, exist_ok=True)
    REGISTRY.write_text(dump_yamlish({k: v for k, v in reg.items()}), encoding="utf-8")


def _scope_path(use_global: bool):
    """설정을 어디에 쓸지 — 전역(모든 프로젝트 기본값) 또는 현재 프로젝트."""
    from .core import GLOBAL_CONFIG, find_project_root
    if use_global:
        return GLOBAL_CONFIG, "전역 기본값"
    root = find_project_root()
    if root is None:
        raise SystemExit("프로젝트 폴더가 아닙니다. 전역 기본값을 바꾸려면 --global 을 쓰세요.")
    return root / ".llm-wiki" / "config.yaml", f"프로젝트({root.name})"


def _effective_cfg() -> tuple[dict, str]:
    """현재 위치 기준 유효 설정 — 프로젝트 안이면 병합 결과, 밖이면 전역 기본값."""
    from .core import find_project_root, global_config
    root = find_project_root()
    if root is None:
        return global_config(), "전역 기본값"
    return Project(root).config(), f"프로젝트({root.name})"


def _print_status(cfg: dict, where: str) -> None:
    from . import backends
    print(f"현재 유효 설정 — {where}")
    external = cfg.get("external_llm_allowed", True)
    models = cfg.get("model") or {}
    order = (cfg.get("llm") or {}).get("auth_order") or ["oauth", "api_key", "ollama"]
    if not external:
        print("  ! external_llm_allowed: false — 민감 프로젝트라 설정 모델과 무관하게 "
              "로컬(Ollama)만 사용합니다 (N7)")
    for role in backends.ROLES:
        mark = "" if models.get(role) or role == "compile" else "  (compile 값 상속)"
        try:
            model, prov = backends.effective(cfg, role)
            cands, blocked = backends.plan(cfg, role)
            route = " → ".join(c.name for c in cands) or "없음"
            note = f"  (막힘: {', '.join(blocked)})" if blocked else ""
            print(f"  {role:9} {model:<26} [{backends.PROVIDER_LABEL.get(prov, prov)}] "
                  f"{route}{note}{mark}")
        except backends.BackendError as e:
            print(f"  {role:9} {backends.model_for(cfg, role):<26} ! {e}")
    print(f"  {'local':9} {models.get('fallback_local') or backends.DEFAULT_LOCAL}")
    print(f"  인증 순서   {', '.join(order) if external else 'ollama (강제)'}")
    print("\n공급자별 사용 가능 경로")
    for prov in backends.PROVIDERS:
        st = backends.auth_status(prov, cfg)
        if prov == "ollama":
            print(f"  {backends.PROVIDER_LABEL[prov]:<16} "
                  f"{'○ 실행 중' if st['ollama'] else '× 미실행'}")
            continue
        print(f"  {backends.PROVIDER_LABEL[prov]:<16} "
              f"OAuth {'○' if st['oauth'] else '×'} ({st['oauth_hint']})   "
              f"API key {'○' if st['api_key'] else '×'} ({st['api_key_hint']})")


def _pick_model(reg: dict) -> str | None:
    """공급자 → 모델 대화형 선택. 목록에 없는 이름을 직접 입력하면 레지스트리에 등록."""
    from . import backends
    provs = list(backends.PROVIDERS)
    print("\n공급자를 고르세요:")
    for i, p in enumerate(provs, 1):
        st = backends.auth_status(p)   # 대화형 선택 — 유효 설정 없이 전역 기준
        avail = ("실행 중" if st.get("ollama") else "미실행") if p == "ollama" else \
            " ".join(x for x in [("OAuth" if st["oauth"] else ""),
                                 ("API key" if st["api_key"] else "")] if x) or "사용 가능 경로 없음"
        print(f"  {i}) {backends.PROVIDER_LABEL[p]:<16} {avail}")
    ans = input("번호 또는 이름: ").strip()
    prov = provs[int(ans) - 1] if ans.isdigit() and 1 <= int(ans) <= len(provs) \
        else backends.canon_provider(ans)
    if prov not in backends.PROVIDERS:
        print("알 수 없는 공급자입니다.")
        return None

    models = reg.get(prov, [])
    print(f"\n{backends.PROVIDER_LABEL[prov]} 등록 모델:")
    for i, m in enumerate(models, 1):
        print(f"  {i}) {m}")
    print("  (목록에 없으면 모델명을 직접 입력 — 레지스트리에 자동 등록됩니다)")
    ans = input("번호 또는 모델명: ").strip()
    if not ans:
        return None
    if ans.isdigit() and 1 <= int(ans) <= len(models):
        return models[int(ans) - 1]
    reg.setdefault(prov, [])
    if ans not in reg[prov]:
        reg[prov].append(ans)
        _save_registry(reg)
        print(f"✓ 레지스트리 등록: {prov}/{ans}")
    return ans


def cmd_models(args) -> None:
    from . import backends
    from .core import update_yamlish
    action = args.action or "list"
    reg = backends.registry()

    if action == "list":
        for prov in backends.PROVIDERS:
            models = reg.get(prov, [])
            print(f"{prov}: {', '.join(models) if models else '(없음)'}")
        for prov, models in reg.items():   # 표준 4종 밖에 사용자가 넣은 것도 보여준다
            if prov not in backends.PROVIDERS:
                print(f"{prov}: {', '.join(models) if models else '(없음)'}")
        return

    if action == "show":
        cfg, where = _effective_cfg()
        _print_status(cfg, where)
        return

    if action in ("add", "remove"):
        if not (args.provider and args.model_id):
            raise SystemExit(f"사용법: llm-wiki models {action} <provider> <model-id>")
        prov = backends.canon_provider(args.provider)
        if action == "add":
            reg.setdefault(prov, [])
            if args.model_id not in reg[prov]:
                reg[prov].append(args.model_id)
            print(f"✓ 등록: {prov}/{args.model_id}")
        else:
            if args.model_id in reg.get(prov, []):
                reg[prov].remove(args.model_id)
                print(f"✓ 제거: {prov}/{args.model_id}")
            else:
                print(f"레지스트리에 없습니다: {prov}/{args.model_id}")
        _save_registry(reg)
        return

    if action == "use":
        # `models use <model>` 또는 인자 없이 대화형. provider 자리에 모델명을 써도 받아준다.
        model = args.model_id or args.provider
        interactive = not model
        if interactive:
            cfg, where = _effective_cfg()
            _print_status(cfg, where)
            model = _pick_model(reg)
            if not model:
                print("변경하지 않았습니다.")
                return
        roles = ([args.role] if args.role and args.role != "all"
                 else list(backends.ROLES))
        prov = backends.provider_of(model, reg)   # 알 수 없는 모델이면 여기서 안내하며 중단
        if prov not in reg or model not in reg.get(prov, []):
            reg.setdefault(prov, [])
            reg[prov].append(model)
            _save_registry(reg)

        use_global = args.glob
        if interactive and not use_global:
            ans = input("\n저장 위치 — 1) 이 프로젝트  2) 전역 기본값 [1]: ").strip()
            use_global = ans == "2"
        path, where = _scope_path(use_global)
        update_yamlish(path, {"model": {r: model for r in roles}})
        print(f"\n✓ {where} 설정: {', '.join(roles)} → {model} "
              f"[{backends.PROVIDER_LABEL.get(prov, prov)}]")
        print(f"  {path}")
        cfg, where2 = _effective_cfg()
        cands, blocked = backends.plan(cfg, roles[0])
        if cands:
            print(f"  호출 경로: {' → '.join(c.name for c in cands)}"
                  + (f"  (막힘: {', '.join(blocked)})" if blocked else ""))
        else:
            print(f"  ! 아직 쓸 수 있는 인증 경로가 없습니다 — {', '.join(blocked) or '확인 필요'}")
        return

    if action == "auth":
        if not args.provider:
            raise SystemExit("사용법: llm-wiki models auth <oauth,api_key,ollama> [--global]")
        order = [o.strip() for o in args.provider.replace(",", " ").split() if o.strip()]
        bad = [o for o in order if o not in ("oauth", "api_key", "ollama")]
        if bad:
            raise SystemExit(f"알 수 없는 인증 방식: {', '.join(bad)} "
                             "(사용 가능: oauth, api_key, ollama)")
        path, where = _scope_path(args.glob)
        update_yamlish(path, {"llm": {"auth_order": order}})
        print(f"✓ {where} 인증 순서: {', '.join(order)}\n  {path}")


