import json
import logging
import urllib.request
import urllib.error
from agent.adapters.base import Adapter, AdapterResult
from agent.config import OllamaAdapterConfig

log = logging.getLogger(__name__)

OLLAMA_CAPABILITIES = {
    "llm.scene_spec",
    "llm.blender_python",
    "llm.general",
    "vision.image_analysis",
    "vision.render_comparison",
}


class OllamaAdapter(Adapter):
    name = "ollama"

    def __init__(self, cfg: OllamaAdapterConfig):
        self._cfg = cfg

    def can_handle(self, job: dict) -> bool:
        caps = set(job.get("required_capabilities") or [])
        return bool(caps & OLLAMA_CAPABILITIES)

    def execute(self, job: dict) -> AdapterResult:
        payload = job.get("payload", {})
        model = payload.get("model", self._cfg.default_model)
        prompt = payload.get("prompt", "")
        system_prompt = payload.get("system_prompt", "")
        temperature = payload.get("temperature", 0.2)
        max_tokens = payload.get("max_tokens", 4096)

        if not prompt:
            return AdapterResult(success=False, error="payload.prompt is required")

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        request_body = json.dumps({
            "model": model,
            "messages": messages,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
            "stream": False,
        }).encode()

        req = urllib.request.Request(
            f"{self._cfg.base_url}/api/chat",
            data=request_body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=self._cfg.timeout_seconds) as resp:
                body = json.loads(resp.read())
        except urllib.error.URLError as exc:
            return AdapterResult(success=False, error=f"Ollama unreachable: {exc}")

        response_text = body.get("message", {}).get("content", "")
        usage = body.get("usage", {})

        log.info("Ollama (%s) responded with %d chars", model, len(response_text))

        return AdapterResult(
            success=True,
            log_output=f"model={model} prompt_len={len(prompt)}",
            output_summary={
                "model": model,
                "response": response_text,
                "prompt_tokens": usage.get("prompt_tokens"),
                "completion_tokens": usage.get("completion_tokens"),
            },
        )
