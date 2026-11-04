import os
import requests


class AIProviderError(Exception):
    pass


def _plan_of(org):
    """Organization has no plan relationship, so look it up by subscription_plan_id."""
    if not org or not getattr(org, "subscription_plan_id", None):
        return None
    from app.extensions import db
    from app.models.plan import Plan
    return db.session.get(Plan, org.subscription_plan_id)


def resolve_ai_config(org):
    """Org ki apni key (agar plan allow kare), warna super admin ki platform key."""
    plan = _plan_of(org)
    if org and getattr(org, "ai_api_key", None) and plan and getattr(plan, "allow_own_ai_key", False):
        return {
            "provider": getattr(org, "ai_provider", None) or "ollama",
            "api_key": org.ai_api_key,
            "model": getattr(org, "ai_model", None),
            "own_key": True,
        }
    return {
        "provider": (os.getenv("AI_PROVIDER") or "ollama"),
        "api_key": (os.getenv("AI_API_KEY") or ""),
        "model": (os.getenv("AI_MODEL") or ""),
        "own_key": False,
    }


def _ollama(prompt, cfg):
    url = (os.getenv("OLLAMA_URL") or "http://127.0.0.1:11434") + "/api/generate"
    model = cfg["model"] or "llama3.2:1b"
    r = requests.post(url, json={
        "model": model,
        "prompt": prompt,
        "stream": False,
    }, timeout=120)
    if r.status_code == 404:
        raise AIProviderError("Ollama model '%s' not found. Run: ollama pull %s" % (model, model))
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


def _call(prompt, cfg):
    fn = PROVIDERS.get(cfg["provider"])
    if not fn:
        raise AIProviderError(f"Unknown provider: {cfg['provider']}")
    if cfg["provider"] != "ollama" and not cfg["api_key"]:
        raise AIProviderError("AI API key not configured")
    return fn(prompt, cfg)


def ask_ai(prompt, org=None):
    """Raw call, no allowance accounting. Features should use run_ai_for_org()."""
    return _call(prompt, resolve_ai_config(org))


def _change_allowance(org_id, delta):
    from app.extensions import db
    from app.models.organization import Organization
    q = db.session.query(Organization).filter(Organization.id == org_id)
    if delta < 0:
        q = q.filter(Organization.ai_call_allowance >= -delta)  # never go below zero
    changed = q.update({Organization.ai_call_allowance: Organization.ai_call_allowance + delta},
                       synchronize_session=False)
    db.session.commit()
    return changed


def run_ai_for_org(org, prompt):
    """Use this from features. Own-key calls are free of allowance; platform calls cost 1.
    The call is reserved first and refunded if the AI call fails."""
    cfg = resolve_ai_config(org)
    if cfg["own_key"]:
        return _call(prompt, cfg)
    if not _change_allowance(org.id, -1):
        raise AIProviderError("AI call allowance finished for this organization")
    try:
        return _call(prompt, cfg)
    except Exception:
        _change_allowance(org.id, +1)
        raise