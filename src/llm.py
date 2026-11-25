"""Minimal Ollama chat client built on urllib, so the repo has no HTTP dependency."""
import json
import time
import urllib.error
import urllib.request

from . import config


class LLMError(Exception):
    """The model endpoint failed; the caller decides whether to retry."""


def chat(messages, *, model=None, json_mode=None, temperature=None, timeout=None):
    """One blocking turn. Returns {'text', 'seconds', 'prompt_tokens', 'gen_tokens'}."""
    payload = {
        "model": model or config.MODEL,
        "messages": messages,
        "stream": False,
        "options": {"temperature": config.TEMPERATURE if temperature is None else temperature},
    }
    if config.JSON_MODE if json_mode is None else json_mode:
        payload["format"] = "json"
    data = json.dumps(payload).encode("utf-8")
    request = urllib.request.Request(
        config.OLLAMA_URL,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=timeout or config.TIMEOUT) as response:
            body = json.loads(response.read().decode("utf-8"))
    except urllib.error.URLError as exc:
        raise LLMError(f"cannot reach Ollama at {config.OLLAMA_URL}: {exc}") from None
    except json.JSONDecodeError as exc:
        raise LLMError(f"Ollama returned malformed JSON: {exc}") from None
    seconds = round(time.perf_counter() - started, 2)
    message = body.get("message") or {}
    return {
        "text": (message.get("content") or "").strip(),
        "seconds": seconds,
        "prompt_tokens": body.get("prompt_eval_count"),
        "gen_tokens": body.get("eval_count"),
    }
