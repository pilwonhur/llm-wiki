"""LLM 백엔드 추상화 (§3.3): OAuth(Claude CLI) → API key → Ollama 로컬.

- 민감 프로젝트(external_llm_allowed: false)는 Ollama만 허용 — 코드 수준 강제 (N7).
- 모든 호출의 토큰·비용을 반환해 CLI가 기록한다 (N3, 기준 ⑤ 이행).
- 테스트 훅: 환경변수 LLM_WIKI_FAKE=<응답파일> 이면 파일 내용을 그대로 반환.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.request
from pathlib import Path


class BackendError(SystemExit):
    pass


class Backend:
    name = "base"

    def __init__(self, model: str):
        self.model = model

    def complete(self, prompt: str, cwd: Path | None = None) -> tuple[str, dict]:
        """(응답 텍스트, usage) 반환. usage: {input,output,cost_usd} (가능한 범위)."""
        raise NotImplementedError


class FakeBackend(Backend):
    """테스트 전용 — LLM_WIKI_FAKE 파일 내용을 응답으로 사용."""
    name = "fake"

    def complete(self, prompt, cwd=None):
        return Path(os.environ["LLM_WIKI_FAKE"]).read_text(encoding="utf-8"), {}


class ClaudeCLIBackend(Backend):
    """OAuth 경로: Claude Code 헤드리스. 에이전트형이라 프로젝트 파일을 직접 읽을 수 있다."""
    name = "oauth-claude"

    def complete(self, prompt, cwd=None):
        cmd = ["claude", "-p", prompt, "--output-format", "json"]
        if self.model:
            cmd += ["--model", self.model]
        r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd, timeout=1800)
        if r.returncode != 0:
            raise BackendError(f"claude CLI 실패: {r.stderr.strip()[:300]}")
        try:
            data = json.loads(r.stdout)
            usage = data.get("usage", {}) or {}
            return data.get("result", ""), {
                "input": usage.get("input_tokens"), "output": usage.get("output_tokens"),
                "cost_usd": data.get("total_cost_usd")}
        except json.JSONDecodeError:
            return r.stdout, {}


class AnthropicAPIBackend(Backend):
    """API key 경로 (선택 의존성 `anthropic`)."""
    name = "api-anthropic"

    def complete(self, prompt, cwd=None):
        import anthropic  # 지연 import — extras [llm]
        client = anthropic.Anthropic()
        msg = client.messages.create(
            model=self.model, max_tokens=8192,
            messages=[{"role": "user", "content": prompt}])
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        return text, {"input": msg.usage.input_tokens, "output": msg.usage.output_tokens}


class OllamaBackend(Backend):
    """로컬 경로 — 표준 라이브러리 HTTP만 사용."""
    name = "ollama"
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


def _ollama_alive(host: str = "http://localhost:11434") -> bool:
    try:
        with urllib.request.urlopen(host + "/api/tags", timeout=2):
            return True
    except Exception:
        return False


def resolve(cfg: dict, role: str = "compile") -> Backend:
    """config의 auth_order·모델 설정으로 사용 가능한 백엔드를 결정한다."""
    if os.environ.get("LLM_WIKI_FAKE"):
        return FakeBackend("fake")

    model = (cfg.get("model") or {}).get(role, "claude-fable-5")
    external_ok = cfg.get("external_llm_allowed", True)
    order = (cfg.get("llm") or {}).get("auth_order", ["oauth", "api_key", "ollama"])
    if not external_ok:
        order = ["ollama"]  # N7: 코드 수준 강제

    tried = []
    for auth in order:
        if auth == "oauth" and shutil.which("claude"):
            return ClaudeCLIBackend(model)
        if auth == "api_key" and os.environ.get("ANTHROPIC_API_KEY"):
            try:
                import anthropic  # noqa: F401
                return AnthropicAPIBackend(model)
            except ImportError:
                tried.append("api_key(anthropic 패키지 없음 — pip install 'llm-wiki[llm]')")
                continue
        if auth == "ollama" and _ollama_alive():
            local_model = (cfg.get("model") or {}).get("fallback_local", "qwen3:32b")
            return OllamaBackend(local_model if external_ok is False or auth == "ollama" else model)
        tried.append(auth)
    hint = ("민감 프로젝트는 Ollama만 허용됩니다 — Ollama를 설치·실행하세요."
            if not external_ok else
            "Claude Code 설치(OAuth), ANTHROPIC_API_KEY 설정, 또는 Ollama 실행 중 하나가 필요합니다.")
    raise BackendError(f"사용 가능한 LLM 백엔드가 없습니다 (시도: {', '.join(tried)}). {hint}")
