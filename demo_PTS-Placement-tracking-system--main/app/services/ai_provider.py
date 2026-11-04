import os
import requests


class AIProviderError(Exception):
    pass


def resolve_ai_config(org):
    """Org ki apni key (agar plan allow kare), warna super admin ki platform key."""
    if org and getattr(org, "ai_api_key", None) and getattr(getattr(org, "plan", None), "allow_own_ai_key", False):
        return {
            "provider": getattr(org, "ai_provider", None) or "ollama",
            "api_key": org.ai_api_key,
            "model": getattr(org, "ai_model", None),
        }
    return {
        "provider": (os.getenv("AI_PROVIDER") or "ollama"),
        "api_key": (os.getenv("AI_API_KEY") or ""),
        "model": (os.getenv("AI_MODEL") or ""),
    }


def _ollama(prompt, cfg):
    url = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434") + "/api/generate"
    r = requests.post(url, json={
        "model": cfg["model"] or "llama3",
        "prompt": prompt,
        "stream": False,
    }, timeout=60)
    r.raise_for_status()
    return r.json()["response"]


def _openai(prompt, cfg):
    r = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {cfg['api_key']}"},
        json={
            "model": cfg["model"] or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["choices"][0]["message"]["content"]


def _gemini(prompt, cfg):
    model = cfg["model"] or "gemini-1.5-flash"
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    r = requests.post(
        url,
        params={"key": cfg["api_key"]},
        json={"contents": [{"parts": [{"text": prompt}]}]},
        timeout=60,
    )
    r.raise_for_status()
    return r.json()["candidates"][0]["content"]["parts"][0]["text"]


PROVIDERS = {"ollama": _ollama, "openai": _openai, "gemini": _gemini}


def ask_ai(prompt, org=None):
    cfg = resolve_ai_config(org)
    fn = PROVIDERS.get(cfg["provider"])
    if not fn:
        raise AIProviderError(f"Unknown provider: {cfg['provider']}")
    if cfg["provider"] != "ollama" and not cfg["api_key"]:
        raise AIProviderError("AI API key not configured")
    return fn(prompt, cfg)

