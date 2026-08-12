"""결정적 뼈대: 경로·정규화·해시·설정·manifest·lock·백업.

외부 의존성 없음 (N8). 정본은 항상 Markdown/JSON 파일 — 이 모듈이 깨져도
프로젝트 폴더만으로 상태를 재구축할 수 있어야 한다 (N2).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import unicodedata
from datetime import datetime, date
from pathlib import Path

SOURCE_TYPES = {
    "paper": "Papers",
    "meeting": "Meeting-Notes",
    "experiment": "Experiments",
    "dataset": "Datasets",
    "webclip": "Web-Clips",
    "qa": "QA-Sessions",
    "proposal": "Proposals",
}
STATUS_VALUES = {"draft", "reviewed", "approved", "deprecated", "disputed"}
# AI(편찬기)가 쓸 수 있는 경로 화이트리스트 (프로젝트 루트 기준 접두사)
AI_WRITABLE = ("30_Wiki", ".llm-wiki")
UNSAFE_CHARS = re.compile(r"[\[\]#^|]")  # Obsidian wikilink 충돌 문자 (F1.7)
# 전역 사용자 설정 — 모델·인증 기본값과 모델 레지스트리를 컴퓨터 단위로 보관한다.
GLOBAL_DIR = Path.home() / ".llm-wiki"
GLOBAL_CONFIG = GLOBAL_DIR / "config.yaml"
GLOBAL_REGISTRY = GLOBAL_DIR / "models.yaml"


def nfc(s: str) -> str:
    return unicodedata.normalize("NFC", s)


def today() -> str:
    return date.today().isoformat()


def run_id() -> str:
    return datetime.now().strftime("%Y%m%d-%H%M%S")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_name(name: str) -> str:
    """wikilink와 충돌하는 문자를 제거한 안전한 파일명 (F1.7). 원명은 manifest에 보존."""
    cleaned = UNSAFE_CHARS.sub("", nfc(name))
    cleaned = re.sub(r"\s{2,}", " ", cleaned).strip()
    return cleaned or "unnamed"


def find_project_root(start: Path | None = None) -> Path | None:
    """`.llm-wiki`를 가진 가장 가까운 상위 폴더.

    홈 디렉터리는 제외한다 — `~/.llm-wiki`는 전역 설정·레지스트리 보관소라서
    그대로 두면 홈 아래 아무 곳에서나 홈이 프로젝트로 잡힌다.
    """
    cur = (start or Path.cwd()).resolve()
    home = Path.home().resolve()
    for p in [cur, *cur.parents]:
        if p == home:
            continue
        if (p / ".llm-wiki").is_dir():
            return p
    return None


# ---------------------------------------------------------------- config
# 의존성 없이 동작하는 2단 YAML 부분 파서 (우리 스키마 전용: 스칼라, 1단 중첩, 인라인 리스트)

def _parse_scalar(v: str):
    v = v.strip()
    if v.startswith("[") and v.endswith("]"):
        inner = v[1:-1].strip()
        return [x.strip().strip('"\'') for x in inner.split(",")] if inner else []
    if v.startswith('"') and v.endswith('"') or v.startswith("'") and v.endswith("'"):
        return v[1:-1]
    if v.lower() in ("true", "yes"):
        return True
    if v.lower() in ("false", "no"):
        return False
    if v.isdigit():
        return int(v)
    return v


def load_yamlish(path: Path) -> dict:
    data: dict = {}
    section = None
    if not path.exists():
        return data
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].rstrip() if not raw.strip().startswith("#") else ""
        if not line.strip():
            continue
        indent = len(line) - len(line.lstrip())
        key, _, val = line.strip().partition(":")
        if indent == 0:
            if val.strip():
                data[key] = _parse_scalar(val)
                section = None
            else:
                data[key] = {}
                section = key
        elif section is not None:
            data[section][key] = _parse_scalar(val)
    return data


def update_yamlish(path: Path, updates: dict) -> None:
    """yamlish 파일 부분 갱신 — 기존 줄·주석·순서를 보존하고 지정 키만 교체/추가한다.

    updates 예: {"model": {"compile": "claude-opus-5"}, "external_llm_allowed": False}
    save_config는 전체를 다시 쓰므로 주석이 사라진다. 설정 한 항목만 바꿀 때는 이쪽을 쓴다.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    pending = {k: (dict(v) if isinstance(v, dict) else v) for k, v in updates.items()}

    out: list[str] = []
    section_end: dict[str, int] = {}   # 섹션명 → 그 블록의 마지막 줄 인덱스(out 기준)
    section = None
    for raw in lines:
        stripped = raw.strip()
        code = "" if stripped.startswith("#") else raw.split("#", 1)[0].rstrip()
        if not code.strip():
            out.append(raw)
            continue
        indent = len(code) - len(code.lstrip())
        key, _, val = code.strip().partition(":")
        if indent == 0:
            section = key if not val.strip() else None
            if key in pending and not isinstance(pending[key], dict):
                out.append(f"{key}: {_fmt(pending.pop(key))}")
            elif section is not None:
                out.append(raw)
                section_end[section] = len(out) - 1
            else:
                out.append(raw)
            continue
        if section is not None and isinstance(pending.get(section), dict) and key in pending[section]:
            out.append(f"  {key}: {_fmt(pending[section].pop(key))}")
        else:
            out.append(raw)
        if section is not None:
            section_end[section] = len(out) - 1

    # 기존 섹션에 남은 신규 키를 그 블록 끝에 삽입 (뒤에서부터 — 인덱스 보존)
    existing = [s for s, kv in pending.items() if isinstance(kv, dict) and s in section_end]
    for s in sorted(existing, key=lambda s: section_end[s], reverse=True):
        at = section_end[s]
        out[at + 1:at + 1] = [f"  {k}: {_fmt(v)}" for k, v in pending.pop(s).items()]

    # 파일에 아예 없던 키·섹션은 끝에 추가
    for k, v in pending.items():
        if isinstance(v, dict):
            if not v:
                continue
            out.append(f"{k}:")
            out.extend(f"  {k2}: {_fmt(v2)}" for k2, v2 in v.items())
        else:
            out.append(f"{k}: {_fmt(v)}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")


def merge_config(base: dict, over: dict) -> dict:
    """2단 깊이 병합 — over(프로젝트)가 base(전역 기본값)를 항목 단위로 덮어쓴다."""
    merged = {k: (dict(v) if isinstance(v, dict) else v) for k, v in base.items()}
    for k, v in over.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def global_config() -> dict:
    """전역 기본 설정 (~/.llm-wiki/config.yaml) — 프로젝트마다 다시 정하지 않도록."""
    return load_yamlish(GLOBAL_CONFIG)


def dump_yamlish(data: dict) -> str:
    out = []
    for k, v in data.items():
        if isinstance(v, dict):
            out.append(f"{k}:")
            for k2, v2 in v.items():
                out.append(f"  {k2}: {_fmt(v2)}")
        else:
            out.append(f"{k}: {_fmt(v)}")
    return "\n".join(out) + "\n"


def _fmt(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    if isinstance(v, str) and (":" in v or v == ""):
        return f'"{v}"'
    return str(v)


class Project:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.meta = self.root / ".llm-wiki"

    # -- config
    @property
    def config_path(self) -> Path:
        return self.meta / "config.yaml"

    def config(self) -> dict:
        """전역 기본값(~/.llm-wiki/config.yaml) 위에 프로젝트 설정을 덮은 결과.

        프로젝트가 명시한 값이 항상 이긴다 — external_llm_allowed: false 같은
        안전 설정을 전역 기본값이 뒤집을 수 없다 (N7).
        """
        return merge_config(global_config(), load_yamlish(self.config_path))

    def raw_config(self) -> dict:
        """전역 병합 없이 프로젝트 파일에 실제로 쓰인 값만 (설정 출처 표시용)."""
        return load_yamlish(self.config_path)

    def save_config(self, cfg: dict) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)   # 템플릿 복사가 없어도 쓰기는 성공해야 한다
        self.config_path.write_text(dump_yamlish(cfg), encoding="utf-8")

    # -- manifest
    @property
    def manifest_path(self) -> Path:
        return self.meta / "manifest.json"

    def manifest(self) -> dict:
        if self.manifest_path.exists():
            return json.loads(self.manifest_path.read_text(encoding="utf-8"))
        return {"sources": []}

    def save_manifest(self, m: dict) -> None:
        self.meta.mkdir(parents=True, exist_ok=True)
        self.manifest_path.write_text(
            json.dumps(m, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    # -- 처리 로그 (사람이 읽는 이력)
    def log_query(self, q: str, asker: str, hits: int, **extra) -> None:
        """질의를 관심도 로그에 실명과 함께 기록 (F11.1). ask와 MCP가 공유한다."""
        d = self.meta / "metrics"
        d.mkdir(parents=True, exist_ok=True)
        rec = {"at": datetime.now().isoformat(timespec="seconds"),
               "asker": asker or "unknown", "query": q[:200], "hits": hits}
        rec.update({k: v for k, v in extra.items() if v is not None})
        with open(d / "queries.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def log(self, title: str, lines: list[str]) -> None:
        p = self.meta / "processing-log.md"
        entry = [f"\n## {today()} — {title}"] + [f"- {ln}" for ln in lines]
        with open(p, "a", encoding="utf-8") as f:
            f.write("\n".join(entry) + "\n")

    # -- lock (I4: 이중 실행 방지)
    @property
    def lock_path(self) -> Path:
        return self.meta / ".lock"

    def acquire_lock(self, op: str) -> None:
        if self.lock_path.exists():
            try:
                info = json.loads(self.lock_path.read_text())
                pid = int(info.get("pid", 0))
                alive = pid and _pid_alive(pid)
            except Exception:
                alive = False
            if alive:
                raise SystemExit(
                    f"오류: 다른 실행이 진행 중입니다 ({info.get('op')}, pid {pid}). "
                    "종료를 기다리거나, 비정상 종료였다면 .llm-wiki/.lock 을 삭제하세요.")
            self.lock_path.unlink()  # stale lock 자동 해제
        self.lock_path.write_text(json.dumps(
            {"op": op, "pid": os.getpid(), "at": datetime.now().isoformat()}))

    def release_lock(self) -> None:
        self.lock_path.unlink(missing_ok=True)

    # -- 백업 (F3.1) / 롤백 (F3.3)
    def backup(self, rid: str, keep: int = 10) -> Path:
        dst = self.meta / "backups" / rid
        dst.mkdir(parents=True, exist_ok=True)
        wiki = self.root / "30_Wiki"
        if wiki.exists():
            shutil.copytree(wiki, dst / "30_Wiki", dirs_exist_ok=True)
        if self.manifest_path.exists():
            shutil.copy2(self.manifest_path, dst / "manifest.json")
        # 보관 한도 초과분 정리 (오래된 것부터)
        backups = sorted((self.meta / "backups").iterdir())
        for old in backups[:-keep]:
            if old.is_dir():
                shutil.rmtree(old)
        return dst

    def list_backups(self) -> list[str]:
        d = self.meta / "backups"
        return sorted(x.name for x in d.iterdir() if x.is_dir()) if d.exists() else []

    def rollback(self, rid: str) -> None:
        src = self.meta / "backups" / rid
        if not src.is_dir():
            raise SystemExit(f"오류: 백업 {rid} 이(가) 없습니다. 보유: {', '.join(self.list_backups()) or '없음'}\n"
                             "(내장 백업은 최근 실행분만 보관합니다 — 장기 이력은 git enable 권장)")
        wiki = self.root / "30_Wiki"
        if (src / "30_Wiki").exists():
            shutil.rmtree(wiki, ignore_errors=True)
            shutil.copytree(src / "30_Wiki", wiki)
        if (src / "manifest.json").exists():
            shutil.copy2(src / "manifest.json", self.manifest_path)

    # -- wiki 문서 열람
    def wiki_docs(self):
        wiki = self.root / "30_Wiki"
        for p in sorted(wiki.rglob("*.md")):
            if "_Proposals" in p.parts:
                continue
            yield p

    def proposals(self) -> list[Path]:
        d = self.root / "30_Wiki" / "_Proposals"
        return sorted(p for p in d.glob("*.md")) if d.exists() else []


def _pid_alive(pid: int) -> bool:
    if os.name == "nt":
        # Windows에서 os.kill(pid, 0)은 확인이 아니라 프로세스를 종료시킨다 —
        # OpenProcess로 존재만 조회한다.
        import ctypes
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        h = ctypes.windll.kernel32.OpenProcess(  # type: ignore[attr-defined]
            PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
        if h:
            ctypes.windll.kernel32.CloseHandle(h)  # type: ignore[attr-defined]
            return True
        return False
    try:
        os.kill(pid, 0)  # POSIX: 신호 0 = 존재 확인만
        return True
    except (ProcessLookupError, PermissionError):
        return False
    except OSError:
        return False


def frontmatter(text: str) -> dict:
    """문서 frontmatter의 스칼라 필드만 파싱."""
    m = re.match(r"^---\n(.*?)\n---", text, re.S)
    fm: dict = {}
    if m:
        for line in m.group(1).splitlines():
            if ":" in line and not line.startswith(" ") and not line.startswith("-"):
                k, _, v = line.partition(":")
                fm[k.strip()] = _parse_scalar(v)
    return fm


def require_project() -> Project:
    root = find_project_root()
    if not root:
        raise SystemExit("오류: llm-wiki 프로젝트가 아닙니다 (.llm-wiki 없음). "
                         "프로젝트 폴더 안에서 실행하거나 `llm-wiki init` 하세요.")
    return Project(root)
