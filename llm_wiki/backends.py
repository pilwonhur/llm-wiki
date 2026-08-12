"""LLM 백엔드 추상화 (§3.3): 공급자(Anthropic·OpenAI·Gemini) × 인증(OAuth·API key) × 로컬(Ollama).

- 모델명이 공급자를 결정한다: 레지스트리(~/.llm-wiki/models.yaml) 조회 → 접두사 추정.
- 인증 방식은 config `llm.auth_order` 순서로 시도한다 (기본: oauth → api_key → ollama).
  OAuth는 각 공급자의 구독형 CLI(claude·codex·gemini)를, API key는 공식 SDK를 쓴다.
- 사용 가능한 경로가 여럿이면 순서대로 묶어 두고 (FallbackBackend) 실행 중 실패 시 다음으로 넘어간다.
- 민감 프로젝트(external_llm_allowed: false)는 Ollama만 허용 — 코드 수준 강제 (N7).
- 모든 호출의 토큰·비용을 반환해 CLI가 기록한다 (N3, 기준 ⑤ 이행).
- 테스트 훅: 환경변수 LLM_WIKI_FAKE=<응답파일> 이면 파일 내용을 그대로 반환.
"""
from __future__ import annotations

import importlib.util
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path

from .core import GLOBAL_REGISTRY, load_yamlish

DEFAULT_MODEL = "claude-fable-5"
DEFAULT_LOCAL = "qwen3:32b"
ROLES = ("compile", "audit", "metadata")

PROVIDERS = ("anthropic", "openai", "gemini", "antigravity", "ollama")
# 사용자가 어떻게 쓰든 하나로 모은다 (레지스트리의 기존 `claude:` 키도 그대로 인식).
PROVIDER_ALIASES = {
    "anthropic": "anthropic", "claude": "anthropic",
    "openai": "openai", "gpt": "openai", "chatgpt": "openai", "codex": "openai",
    "gemini": "gemini", "google": "gemini",
    "antigravity": "antigravity", "agy": "antigravity",
    "ollama": "ollama", "local": "ollama",
}
PROVIDER_LABEL = {"anthropic": "Anthropic", "openai": "OpenAI",
                  "gemini": "Google Gemini", "antigravity": "Antigravity (agy)",
                  "ollama": "Ollama (로컬)"}
# 새 모델이 출시돼도 코드 수정이 필요 없도록 — 레지스트리에 등록하면 즉시 쓸 수 있다.
# antigravity는 모델 ID가 자체 체계(-high/-low 접미사)라 공급자 판별이 레지스트리에 의존한다.
DEFAULT_MODELS = {
    "anthropic": ["claude-fable-5", "claude-opus-5", "claude-sonnet-5", "claude-haiku-4-5"],
    "openai": ["gpt-5.6-sol", "gpt-5.6-terra", "gpt-5.6-luna"],
    "gemini": ["gemini-3.6-flash", "gemini-3.1-pro-preview"],
    "antigravity": ["gemini-3.6-flash-high", "gemini-3.6-flash-medium",
                    "gemini-3.6-flash-low", "gemini-3.1-pro-high", "gemini-3.1-pro-low",
                    "claude-sonnet-4-6", "claude-opus-4-6-thinking", "gpt-oss-120b-medium"],
    "ollama": [],
}
# antigravity는 구독 CLI 전용 — API key 경로가 없다.
API_ENV = {"anthropic": ("ANTHROPIC_API_KEY",), "openai": ("OPENAI_API_KEY",),
           "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY")}
API_PACKAGE = {"anthropic": ("anthropic", "anthropic"), "openai": ("openai", "openai"),
               "gemini": ("google.genai", "google-genai")}


class BackendError(RuntimeError):
    """CLI가 사용자 메시지로 바꿔 출력한다 (cli.main). 파일 단위 실패 격리도 가능."""


# ---------------------------------------------------------------- 레지스트리·공급자
def registry() -> dict:
    """모델 레지스트리 — 공급자별 등록 모델. 파일이 없으면 기본 목록.

    파일에 **없는 공급자**만 기본값으로 채운다 — 업그레이드로 새 공급자가 추가돼도
    기존 사용자가 다시 등록할 필요가 없고, 사용자가 직접 손댄 공급자 목록은 건드리지 않는다.
    """
    out: dict[str, list] = {}
    for prov, models in (load_yamlish(GLOBAL_REGISTRY) or {}).items():
        canon = canon_provider(prov)
        out.setdefault(canon, [])
        out[canon] += [m for m in (models if isinstance(models, list) else [models]) if m]
    for prov, models in DEFAULT_MODELS.items():
        if prov not in out:
            out[prov] = list(models)
    return out


def canon_provider(name: str) -> str:
    key = (name or "").strip().lower()
    return PROVIDER_ALIASES.get(key, key)


def provider_of(model: str, reg: dict | None = None) -> str:
    """모델명 → 공급자. `openai/gpt-5.6-sol` 처럼 앞에 붙여 강제할 수도 있다."""
    model = (model or "").strip()
    if "/" in model and canon_provider(model.split("/", 1)[0]) in PROVIDERS:
        return canon_provider(model.split("/", 1)[0])
    for prov, models in (reg if reg is not None else registry()).items():
        if model in models:
            return canon_provider(prov)
    low = model.lower()
    if low.startswith("claude"):
        return "anthropic"
    if low.startswith(("gpt", "chatgpt", "o1", "o3", "o4", "codex")):
        return "openai"
    if low.startswith("gemini"):
        return "gemini"
    if ":" in low or low.startswith(("llama", "qwen", "mistral", "gemma", "deepseek", "phi")):
        return "ollama"
    raise BackendError(
        f"모델 '{model}' 의 공급자를 알 수 없습니다. "
        f"`llm-wiki models add <{'|'.join(PROVIDERS)}> {model}` 로 등록하거나 "
        f"`openai/{model}` 처럼 공급자를 앞에 붙이세요.")


def bare_model(model: str) -> str:
    """`openai/gpt-5.6-sol` → `gpt-5.6-sol` (공급자 접두사는 우리 표기일 뿐이라 벗겨서 넘긴다)."""
    if "/" in model and canon_provider(model.split("/", 1)[0]) in PROVIDERS:
        return model.split("/", 1)[1]
    return model


# ---------------------------------------------------------------- 백엔드
class Backend:
    name = "base"
    provider = ""
    agentic = False   # 프로젝트 파일을 스스로 읽는가 (에이전트형 CLI)

    def __init__(self, model: str, cfg: dict | None = None):
        self.model = bare_model(model)
        self.cfg = cfg or {}

    def _extra_args(self) -> list[str]:
        """config `llm.cli_args_<provider>` 로 CLI 인자를 덧붙일 수 있다."""
        v = (self.cfg.get("llm") or {}).get(f"cli_args_{self.provider}")
        return list(v) if isinstance(v, list) else ([v] if v else [])

    def describe(self) -> str:
        return f"{self.name}/{self.model}"

    def complete(self, prompt: str, cwd: Path | None = None) -> tuple[str, dict]:
        """(응답 텍스트, usage) 반환. usage: {input,output,cost_usd} (가능한 범위)."""
        raise NotImplementedError


class FakeBackend(Backend):
    """테스트 전용 — LLM_WIKI_FAKE 파일 내용을 응답으로 사용."""
    name = "fake"

    def complete(self, prompt, cwd=None):
        return Path(os.environ["LLM_WIKI_FAKE"]).read_text(encoding="utf-8"), {}


class FallbackBackend(Backend):
    """auth_order로 만든 후보들을 순서대로 시도 — 앞이 실패하면 다음으로 자동 전환.

    OAuth CLI가 설치돼 있어도 로그인 만료·구독 등급 문제로 실패할 수 있어,
    '설치 여부' 판정만으로는 부족하다. 실제 호출이 깨질 때 API key 경로로 넘어간다.
    """

    def __init__(self, candidates: list[Backend]):
        self.candidates = candidates
        self.active = candidates[0]
        self.cfg = candidates[0].cfg

    @property
    def name(self) -> str:
        return self.active.name

    @property
    def model(self) -> str:
        return self.active.model

    @property
    def provider(self) -> str:
        return self.active.provider

    @property
    def agentic(self) -> bool:
        # 하나라도 비에이전트형이면 본문을 프롬프트에 넣어야 어느 쪽으로 넘어가도 동작한다.
        return all(c.agentic for c in self.candidates)

    def describe(self) -> str:
        return " → ".join(c.describe() for c in self.candidates)

    def complete(self, prompt, cwd=None):
        errors = []
        for i, c in enumerate(self.candidates):
            self.active = c
            try:
                return c.complete(prompt, cwd=cwd)
            except Exception as e:
                errors.append(f"{c.name}: {str(e).strip()[:200]}")
                if i + 1 < len(self.candidates):
                    print(f"    ! {c.name} 실패 → {self.candidates[i + 1].name} 로 전환")
        raise BackendError("사용 가능한 백엔드를 모두 시도했으나 실패했습니다 — "
                           + " | ".join(errors))


# ---- OAuth (구독형 CLI) ------------------------------------------------------
class CLIBackend(Backend):
    """구독 로그인 상태의 공급자 CLI를 헤드리스로 호출."""
    cli = ""
    agentic = True
    timeout = 1800

    @classmethod
    def locate(cls, cfg: dict | None = None) -> str | None:
        """실행 파일 경로. config `llm.cli_path_<provider>` 로 강제 지정할 수 있다."""
        override = ((cfg or {}).get("llm") or {}).get(f"cli_path_{cls.provider}")
        if override:
            p = os.path.expanduser(str(override))
            return p if os.access(p, os.X_OK) else None
        return shutil.which(cls.cli)

    def _bin(self) -> str:
        return type(self).locate(self.cfg) or self.cli

    def _run(self, cmd: list[str], cwd: Path | None):
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd,
                           stdin=subprocess.DEVNULL, timeout=self.timeout)
        if r.returncode != 0:
            msg = (r.stderr or r.stdout).strip()[:300]
            raise BackendError(f"{self.cli} CLI 실패: {msg}")
        return r


class ClaudeCLIBackend(CLIBackend):
    """Anthropic OAuth 경로 — Claude Code 헤드리스."""
    name = "oauth-anthropic"
    provider = "anthropic"
    cli = "claude"

    def complete(self, prompt, cwd=None):
        cmd = [self._bin(), "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        r = self._run(cmd + self._extra_args(), cwd)
        try:
            data = json.loads(r.stdout)
        except json.JSONDecodeError:
            return r.stdout, {}
        usage = data.get("usage", {}) or {}
        return data.get("result", ""), {
            "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
            "cost_usd": data.get("total_cost_usd")}


class CodexCLIBackend(CLIBackend):
    """OpenAI OAuth 경로 — Codex CLI 헤드리스 (`codex exec`).

    최종 답변은 `-o <file>` 로 받고, 토큰 사용량은 `--json` 이벤트 스트림에서 집계한다.
    """
    name = "oauth-openai"
    provider = "openai"
    cli = "codex"

    def complete(self, prompt, cwd=None):
        fd, out_path = tempfile.mkstemp(prefix="llm-wiki-codex-", suffix=".txt")
        os.close(fd)
        try:
            cmd = [self._bin(), "exec", "--json", "--skip-git-repo-check",
                   "-s", "read-only", "-o", out_path]
            if self.model:
                cmd += ["-m", self.model]
            r = self._run(cmd + self._extra_args() + [prompt], cwd)
            text = Path(out_path).read_text(encoding="utf-8").strip()
        finally:
            Path(out_path).unlink(missing_ok=True)
        usage = {}
        for line in r.stdout.splitlines():
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                ev = json.loads(line)
            except json.JSONDecodeError:
                continue
            u = ev.get("usage") or (ev.get("msg") or {}).get("usage")
            if isinstance(u, dict) and ("input_tokens" in u or "output_tokens" in u):
                usage = {"input": u.get("input_tokens"), "output": u.get("output_tokens")}
        if not text:
            raise BackendError("codex CLI 가 최종 응답을 반환하지 않았습니다.")
        return text, usage


class GeminiCLIBackend(CLIBackend):
    """Gemini OAuth 경로 — Gemini CLI 헤드리스 (`gemini -p`)."""
    name = "oauth-gemini"
    provider = "gemini"
    cli = "gemini"

    def complete(self, prompt, cwd=None):
        cmd = [self._bin(), "-p", prompt, "-o", "json"]
        if self.model:
            cmd += ["-m", self.model]
        r = self._run(cmd + self._extra_args(), cwd)
        raw = r.stdout.strip()
        try:  # {"response": "...", "stats": {...}} 형태 — 버전에 따라 달라 방어적으로 읽는다
            data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            return raw, {}
        text = data.get("response") or data.get("text") or raw
        tok = ((data.get("stats") or {}).get("tokens")
               or (data.get("usage") or {}) or {})
        return text, {"input": tok.get("prompt") or tok.get("input"),
                      "output": tok.get("candidates") or tok.get("output")}


class AntigravityCLIBackend(CLIBackend):
    """Antigravity OAuth 경로 — Antigravity CLI 헤드리스 (`agy -p`).

    다른 CLI와 달리 **에이전트형이 아니다** (agentic=False): 헤드리스에서는 파일 읽기 같은
    도구 권한을 물어볼 수 없어 자동 거부되고, 그때 status는 SUCCESS인데 response만 비어
    돌아온다. 그래서 원자료 본문을 프롬프트에 넣어 도구 없이 답하게 하고,
    빈 응답은 오류로 올려 다음 백엔드로 넘긴다.
    파일을 직접 읽게 하려면 Antigravity settings.json의 permissions.allow에 규칙을 넣고
    config `llm.cli_args_antigravity` 로 필요한 인자를 덧붙인다.
    """
    name = "oauth-antigravity"
    provider = "antigravity"
    cli = "agy"
    agentic = False

    @classmethod
    def locate(cls, cfg=None):
        """PATH의 `agy`는 IDE 런처(Electron)일 수 있다 — 그건 -p를 무시하고 창을 띄운다.

        설치 관리자가 놓는 실제 CLI(~/.local/bin/agy)를 우선하고, .app 번들 안으로
        연결되는 경로는 걸러낸다.
        """
        override = ((cfg or {}).get("llm") or {}).get("cli_path_antigravity")
        if override:
            p = os.path.expanduser(str(override))
            return p if os.access(p, os.X_OK) else None
        candidates = [str(Path.home() / ".local" / "bin" / "agy")]
        found = shutil.which("agy")
        if found:
            candidates.append(found)
        for c in candidates:
            if not os.access(c, os.X_OK):
                continue
            if ".app/" in str(Path(c).resolve()):   # IDE 런처
                continue
            return c
        return None

    def complete(self, prompt, cwd=None):
        cmd = [self._bin(), "-p", prompt, "--output-format", "json",
               "--print-timeout", "30m"]
        if self.model:
            cmd += ["--model", self.model]
        r = self._run(cmd + self._extra_args(), cwd)
        raw = r.stdout.strip()
        try:
            data = json.loads(raw[raw.index("{"):raw.rindex("}") + 1])
        except (ValueError, json.JSONDecodeError):
            if not raw:
                raise BackendError("agy CLI 가 빈 응답을 반환했습니다.")
            return raw, {}
        text = (data.get("response") or "").strip()
        if not text:
            # status=SUCCESS 인데 응답이 비는 대표 원인: 도구 권한 자동 거부
            hint = (r.stderr or "").strip()[:200]
            raise BackendError(
                "agy CLI 가 빈 응답을 반환했습니다 (status="
                f"{data.get('status')}). {hint or '헤드리스에서 도구 권한이 자동 거부됐을 수 있습니다.'}")
        u = data.get("usage") or {}
        return text, {"input": u.get("input_tokens"), "output": u.get("output_tokens")}


# ---- API key (공식 SDK) ------------------------------------------------------
class AnthropicAPIBackend(Backend):
    """API key 경로 (선택 의존성 `anthropic`)."""
    name = "api-anthropic"
    provider = "anthropic"

    def complete(self, prompt, cwd=None):
        import anthropic  # 지연 import — extras [anthropic]
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model, max_tokens=8192,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text, {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}


class OpenAIAPIBackend(Backend):
    """API key 경로 (선택 의존성 `openai`)."""
    name = "api-openai"
    provider = "openai"

    def complete(self, prompt, cwd=None):
        from openai import OpenAI  # 지연 import — extras [openai]
        client = OpenAI()
        try:
            r = client.responses.create(model=self.model, input=prompt)
            text = r.output_text
            u = getattr(r, "usage", None)
            return text, {"input": getattr(u, "input_tokens", None),
                          "output": getattr(u, "output_tokens", None)}
        except (AttributeError, TypeError):  # 구버전 SDK — Chat Completions로
            r = client.chat.completions.create(
                model=self.model, messages=[{"role": "user", "content": prompt}])
            u = getattr(r, "usage", None)
            return r.choices[0].message.content or "", {
                "input": getattr(u, "prompt_tokens", None),
                "output": getattr(u, "completion_tokens", None)}


class GeminiAPIBackend(Backend):
    """API key 경로 (선택 의존성 `google-genai`). GEMINI_API_KEY 또는 GOOGLE_API_KEY."""
    name = "api-gemini"
    provider = "gemini"

    def complete(self, prompt, cwd=None):
        from google import genai  # 지연 import — extras [gemini]
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        client = genai.Client(api_key=key)   # 지역 변수로 붙잡아 둔다 — 임시 객체면 요청 전에 닫힌다
        r = client.models.generate_content(model=self.model, contents=prompt)
        u = getattr(r, "usage_metadata", None)
        return (r.text or ""), {"input": getattr(u, "prompt_token_count", None),
                                "output": getattr(u, "candidates_token_count", None)}


class OllamaBackend(Backend):
    """로컬 경로 — 표준 라이브러리 HTTP만 사용."""
    name = "ollama"
    provider = "ollama"
    host = "http://localhost:11434"

    def complete(self, prompt, cwd=None):
        req = urllib.request.Request(
            f"{self.host}/api/generate",
            data=json.dumps({"model": self.model, "prompt": prompt,
                             "stream": False}).encode(),
            headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=1800) as resp:
            data = json.loads(resp.read())
        return data.get("response", ""), {"input": data.get("prompt_eval_count"),
                                          "output": data.get("eval_count")}


OAUTH_BACKENDS = {"anthropic": ClaudeCLIBackend, "openai": CodexCLIBackend,
                  "gemini": GeminiCLIBackend, "antigravity": AntigravityCLIBackend}
API_BACKENDS = {"anthropic": AnthropicAPIBackend, "openai": OpenAIAPIBackend,
                "gemini": GeminiAPIBackend}


# ---------------------------------------------------------------- 가용성·해석
def _ollama_alive(host: str = "http://localhost:11434") -> bool:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2):
            return True
    except Exception:
        return False


def _have_package(mod: str) -> bool:
    try:
        return importlib.util.find_spec(mod) is not None
    except (ImportError, ValueError):
        return False


def auth_status(provider: str) -> dict:
    """`models show` 용 — 공급자별로 지금 쓸 수 있는 인증 경로."""
    provider = canon_provider(provider)
    if provider == "ollama":
        return {"ollama": _ollama_alive()}
    cls = OAUTH_BACKENDS[provider]
    if provider not in API_ENV:      # 구독 CLI 전용 공급자 (antigravity)
        return {"oauth": bool(cls.locate()), "oauth_hint": f"{cls.cli} CLI",
                "api_key": False, "api_key_hint": "지원 안 함 (구독 CLI 전용)"}
    env_ok = any(os.environ.get(e) for e in API_ENV[provider])
    mod, pkg = API_PACKAGE[provider]
    return {
        "oauth": bool(cls.locate()),
        "oauth_hint": f"{cls.cli} CLI",
        "api_key": bool(env_ok and _have_package(mod)),
        "api_key_hint": ("/".join(API_ENV[provider])
                         + ("" if env_ok else " 미설정")
                         + ("" if _have_package(mod) else f" · {pkg} 미설치")),
    }


def model_for(cfg: dict, role: str = "compile") -> str:
    models = cfg.get("model") or {}
    return models.get(role) or models.get("compile") or DEFAULT_MODEL


def effective(cfg: dict, role: str = "compile") -> tuple[str, str]:
    """실제로 호출될 (모델, 공급자). 민감 프로젝트면 설정 모델 대신 로컬 모델이다 (N7)."""
    if not cfg.get("external_llm_allowed", True):
        return ((cfg.get("model") or {}).get("fallback_local") or DEFAULT_LOCAL, "ollama")
    model = model_for(cfg, role)
    return model, provider_of(model)


def plan(cfg: dict, role: str = "compile") -> tuple[list[Backend], list[str]]:
    """(사용 가능한 백엔드 후보, 못 쓴 이유) — resolve와 `models show`가 공유한다."""
    local = (cfg.get("model") or {}).get("fallback_local") or DEFAULT_LOCAL
    order = (cfg.get("llm") or {}).get("auth_order") or ["oauth", "api_key", "ollama"]
    model, provider = effective(cfg, role)
    if provider == "ollama":   # 로컬 모델(또는 민감 프로젝트)이면 외부 경로는 의미가 없다
        order = ["ollama"]

    candidates, blocked = [], []
    for auth in order:
        if auth == "oauth" and provider in OAUTH_BACKENDS:
            cls = OAUTH_BACKENDS[provider]
            if cls.locate(cfg):
                candidates.append(cls(model, cfg))
            else:
                blocked.append(f"oauth({cls.cli} CLI 미설치)")
        elif auth == "api_key" and provider not in API_BACKENDS:
            blocked.append(f"api_key({PROVIDER_LABEL.get(provider, provider)}는 구독 CLI 전용)")
        elif auth == "api_key" and provider in API_BACKENDS:
            mod, pkg = API_PACKAGE[provider]
            env_ok = any(os.environ.get(e) for e in API_ENV[provider])
            if env_ok and _have_package(mod):
                candidates.append(API_BACKENDS[provider](model, cfg))
            else:
                why = "/".join(API_ENV[provider]) + " 미설정" if not env_ok \
                    else f"{pkg} 미설치 — pipx inject llm-wiki {pkg}"
                blocked.append(f"api_key({why})")
        elif auth == "ollama":
            if _ollama_alive():
                candidates.append(OllamaBackend(local if provider != "ollama" else model, cfg))
            else:
                blocked.append("ollama(localhost:11434 응답 없음)")
    return candidates, blocked


def resolve(cfg: dict, role: str = "compile") -> Backend:
    """config의 모델·auth_order로 사용 가능한 백엔드를 결정한다."""
    if os.environ.get("LLM_WIKI_FAKE"):
        return FakeBackend("fake")

    candidates, blocked = plan(cfg, role)
    if candidates:
        return candidates[0] if len(candidates) == 1 else FallbackBackend(candidates)

    model = model_for(cfg, role)
    if not cfg.get("external_llm_allowed", True):
        hint = "민감 프로젝트는 Ollama만 허용됩니다 — Ollama를 설치·실행하세요."
    else:
        prov = provider_of(model)
        cli = OAUTH_BACKENDS[prov].cli if prov in OAUTH_BACKENDS else "ollama"
        env = "/".join(API_ENV.get(prov, ()))
        need = f"{cli} CLI 로그인(OAuth)" + (f" 또는 {env} 설정" if env else " (API key 경로 없음)")
        hint = (f"{PROVIDER_LABEL.get(prov, prov)} 를 쓰려면 {need}이 필요합니다. "
                "`llm-wiki models show` 로 현황을 보고, "
                "`llm-wiki models use` 로 다른 모델을 고를 수 있습니다.")
    raise BackendError(
        f"'{model}' 을(를) 쓸 수 있는 백엔드가 없습니다 (막힌 경로: {', '.join(blocked) or '없음'}). {hint}")
