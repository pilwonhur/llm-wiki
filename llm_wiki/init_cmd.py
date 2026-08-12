"""`llm-wiki init` — 폴더 하나에서 프로젝트 완성 (F0.1~F0.5).

기존 파일은 절대 건드리지 않는다 (F0.4, 멱등). 대화형 온보딩은 폴더명 외에
정보가 없을 때 최소 정보를 수집한다 (F0.2). --yes 는 전부 기본값 (F0.3).
"""
from __future__ import annotations

import shutil
from pathlib import Path

from .core import LANG_NAME, LANGUAGES, Project, heading, today

TEMPLATE = Path(__file__).parent / "templates" / "project"


def _ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else " (건너뛰기: Enter)"
    try:
        val = input(f"  {prompt}{suffix}: ").strip()
    except EOFError:
        val = ""
    return val or default


def _ask_lang() -> str:
    """출력 언어 — 문서 섹션 제목까지 이 언어로 고정된다 (나중에 바꾸면 문서가 섞인다)."""
    opts = " / ".join(f"{c}={LANG_NAME[c]}" for c in LANGUAGES)
    ans = _ask(f"Wiki 출력 언어 ({opts})", "ko").strip().lower()
    if ans in LANGUAGES:
        return ans
    for code, name in LANG_NAME.items():          # "한국어"·"English" 로 답해도 받아준다
        if ans in (name.lower(), code):
            return code
    print(f"    (알 수 없는 언어 '{ans}' — 기본값 ko 사용)")
    return "ko"


def _default_model() -> str:
    """전역 기본값(~/.llm-wiki/config.yaml)이 있으면 그것을 — 한 번 정하면 다음 프로젝트도 그대로."""
    from . import backends
    from .core import global_config
    return backends.model_for(global_config(), "compile")


def _global_local() -> str:
    from . import backends
    from .core import global_config
    return (global_config().get("model") or {}).get("fallback_local") or backends.DEFAULT_LOCAL


def _global_auth_order() -> list:
    from .core import global_config
    return ((global_config().get("llm") or {}).get("auth_order")
            or ["oauth", "api_key", "ollama"])


def _ask_model(default: str) -> str:
    """등록된 모델을 공급자별로 보여주고 고르게 한다. 새 이름을 쓰면 레지스트리에 등록."""
    from . import backends
    from .misc_cmd import _save_registry
    reg = backends.registry()
    print("\n  등록된 모델 (공급자별 — 사용 가능한 인증 경로 표시):")
    for prov in backends.PROVIDERS:
        models = reg.get(prov, [])
        if not models:
            continue
        st = backends.auth_status(prov)
        avail = ("실행 중" if st.get("ollama") else "미실행") if prov == "ollama" else \
            (" · ".join(x for x in [("OAuth" if st["oauth"] else ""),
                                    ("API key" if st["api_key"] else "")] if x) or "설정 필요")
        print(f"    {backends.PROVIDER_LABEL[prov]:<16} [{avail}] {', '.join(models)}")
    print("    (새 모델명을 직접 입력하면 레지스트리에 저장됩니다. 나중에 "
          "`llm-wiki models use` 로 언제든 변경 가능)")
    model = _ask("편찬 모델", default)
    try:
        prov = backends.provider_of(model, reg)
    except backends.BackendError as e:
        print(f"    ! {e}")
        return model
    if model not in reg.get(prov, []):
        reg.setdefault(prov, []).append(model)
        _save_registry(reg)
    return model


def _install_lang_files(root: Path, lang: str) -> None:
    """언어별 산출물 확정: 문서 템플릿 선택 설치 + AGENTS.md 출력 언어 줄 치환.

    섹션 제목이 코드가 파싱하는 스키마라, 템플릿과 core.HEADINGS 가 같은 값을 써야 한다.
    """
    tdir = root / ".llm-wiki" / "templates"
    src = tdir / f"wiki-doc.{lang}.md"
    if src.exists():
        (tdir / "wiki-doc.md").write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    _fill(root / "AGENTS.md", {
        "- 출력 언어: **한국어** (전문 용어는 첫 등장 시 원문 병기).":
            f"- 출력 언어: **{LANG_NAME[lang]}** (전문 용어는 첫 등장 시 원문 병기). "
            f"섹션 제목은 템플릿 그대로 — 코드가 파싱한다 "
            f"(코멘트 섹션 = `## {heading(lang, 'comments')}`).",
    })


def cmd_init(args) -> None:
    root = Path(args.path).resolve() if args.path else Path.cwd()
    root.mkdir(parents=True, exist_ok=True)
    fresh = not (root / ".llm-wiki").exists()
    existing = [p.name for p in root.iterdir()
                if not p.name.startswith(".") and p.name not in
                {"00_Project", "10_Inbox", "20_Sources", "30_Wiki", "40_Decisions",
                 "50_Outputs", "90_Archive", "adapters", "AGENTS.md", "CLAUDE.md"}]

    # 1) 구조 보충 복사 — 기존 파일은 절대 덮어쓰지 않음 (멱등)
    copied = 0
    for src in TEMPLATE.rglob("*"):
        rel = src.relative_to(TEMPLATE)
        dst = root / rel
        if src.is_dir():
            dst.mkdir(parents=True, exist_ok=True)
        elif not dst.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
            copied += 1

    proj = Project(root)

    # 2) 온보딩 (신규 + 대화형일 때만)
    answers = {}
    if fresh and not args.yes:
        print("\n프로젝트를 설정합니다. Enter로 기본값 사용.\n")
        answers["name"] = _ask("프로젝트 정식 명칭", root.name)
        answers["purpose"] = _ask("한 줄 목적")
        answers["members"] = _ask("구성원 (쉼표 구분)")
        answers["reviewer"] = _ask("Wiki reviewer 실명")
        answers["language"] = _ask_lang()
        sens = _ask("외부 LLM 전송 허용? (IRB·산학 등 민감 자료면 n)", "y")
        answers["external"] = sens.lower() not in ("n", "no", "아니오")
        answers["model"] = _ask_model(_default_model())
    else:
        answers = {"name": root.name, "purpose": "", "members": "", "reviewer": "",
                   "language": "ko", "external": True, "model": _default_model()}

    # 3) config 작성 (신규일 때만 — 재실행 시 기존 설정 보존)
    if fresh:
        proj.save_config({
            "project": answers["name"],
            "language": answers["language"],
            "external_llm_allowed": answers["external"],
            "model": {"compile": answers["model"], "audit": answers["model"],
                      "metadata": answers["model"],
                      "fallback_local": _global_local()},
            # 인증 경로 우선순위 — `llm-wiki models auth` 로 변경
            "llm": {"auth_order": _global_auth_order()},
            "review": {"reviewer": answers["reviewer"] or "<TODO>",
                       "stale_draft_days": 14},
            "snapshot": {"backup_keep": 10},
            "git": {"enabled": False},
        })
        _install_lang_files(root, answers["language"])
        # 4) 00_Project 초안 반영 (템플릿의 TODO 치환 — 답이 있을 때만)
        _fill(root / "00_Project" / "README.md", {
            "# <TODO: 프로젝트 정식 명칭>": f"# {answers['name']}",
            "<!-- TODO: 한 줄 목적 -->": answers["purpose"] or "<!-- TODO: 한 줄 목적 -->",
            "- 시작일:": f"- 시작일: {today()}",
            "- Wiki reviewer: <!-- TODO -->":
                f"- Wiki reviewer: {answers['reviewer']}" if answers["reviewer"]
                else "- Wiki reviewer: <!-- TODO -->",
        })
        if answers["members"]:
            rows = "\n".join(f"| {m.strip()} |  | |" for m in answers["members"].split(","))
            _fill(root / "00_Project" / "members.md",
                  {"| <!-- TODO --> | 책임교수 | |\n| <!-- TODO --> | reviewer | Wiki 검토 담당 |": rows})
            for m in answers["members"].split(","):
                (root / "10_Inbox" / m.strip()).mkdir(exist_ok=True)  # 업로드 귀속 폴더 (F13.1)

    # 5) 보고
    print(f"\n✓ 구조 {'생성' if fresh else '보충'} 완료 ({copied}개 파일)")
    if fresh:
        print("✓ .llm-wiki/config.yaml 생성 (스냅샷: 내장 백업, Git 사용 안 함)")
        print("✓ AGENTS.md·CLAUDE.md·workflows·스킬 어댑터 설치")
    if existing:
        print(f"주의: 기존 파일 {len(existing)}건은 건드리지 않았습니다. "
              f"원자료라면 10_Inbox/<이름>/ 으로 옮긴 뒤 ingest 하세요: {', '.join(existing[:5])}")
    todo = []
    if not answers.get("purpose"):
        todo.append("00_Project/README.md·scope.md의 TODO")
    if not answers.get("reviewer"):
        todo.append("config의 reviewer")
    if todo:
        print(f"남은 입력: {', '.join(todo)} — 채우면 편찬 품질이 좋아집니다.")


def _fill(path: Path, repl: dict) -> None:
    if not path.exists():
        return
    t = path.read_text(encoding="utf-8")
    for a, b in repl.items():
        t = t.replace(a, b)
    path.write_text(t, encoding="utf-8")
