"""One OpenAI-compatible client for every tier, plus local embeddings through Ollama."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

import httpx
from openai import AsyncOpenAI

from smart_docs.config import get_settings
from smart_docs.models import Account
from smart_docs.security import decrypt_secret


@dataclass
class Provider:
    tier: str
    base_url: str
    api_key: str
    model: str


def provider_for(account: Account) -> Provider | None:
    """The chat provider for the account's tier, or None for agent mode / unconfigured."""
    s = get_settings()
    tier = account.tier
    if tier == "hosted" and s.hosted_enabled and s.hosted_api_key:
        return Provider("hosted", s.hosted_base_url.rstrip("/"), s.hosted_api_key, s.hosted_model)
    if tier == "local" and s.local_enabled:
        return Provider("local", s.ollama_url.rstrip("/") + "/v1", "ollama", s.local_model)
    if tier == "byok" and s.byok_enabled and account.byok_key_enc and account.byok_base_url:
        key = decrypt_secret(account.byok_key_enc)
        if key:
            return Provider("byok", account.byok_base_url.rstrip("/"), key, account.byok_model or "gpt-4o-mini")
    return None


SYSTEM_PROMPT = (
    "You write metadata for knowledge-base pages. Reply with JSON only: "
    '{"summary": "<one sentence, at most 40 words, names the subject, no numbers that are not in the text>", '
    '"tags": ["<3 to 5 short lowercase tags>"]}'
)


async def summarize(provider: Provider, title: str, markdown: str) -> tuple[str, list[str]]:
    s = get_settings()
    client = AsyncOpenAI(base_url=provider.base_url, api_key=provider.api_key, timeout=s.model_timeout_seconds)
    body = markdown[:12000]
    resp = await client.chat.completions.create(
        model=provider.model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"Title: {title}\n\n{body}"},
        ],
        temperature=0.2,
        max_tokens=200,
    )
    text = (resp.choices[0].message.content or "").strip()
    return parse_metadata(text)


def parse_metadata(text: str) -> tuple[str, list[str]]:
    """Small models wrap JSON in prose or code fences; dig the object out."""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return text[:300], []
    try:
        data = json.loads(m.group(0))
    except json.JSONDecodeError:
        return text[:300], []
    summary = str(data.get("summary", "")).strip()
    tags = data.get("tags") or []
    if isinstance(tags, str):
        tags = [t.strip() for t in tags.split(",")]
    return summary[:600], [str(t) for t in tags][:10]


async def embed(texts: list[str]) -> list[list[float]]:
    """Embeddings always come from the local Ollama model so every tier shares one vector space."""
    s = get_settings()
    async with httpx.AsyncClient(timeout=s.model_timeout_seconds) as client:
        r = await client.post(
            s.ollama_url.rstrip("/") + "/api/embed",
            json={"model": s.embed_model, "input": [t[:8000] for t in texts]},
        )
        r.raise_for_status()
        data = r.json()
    return data["embeddings"]


async def ollama_status() -> dict:
    s = get_settings()
    try:
        async with httpx.AsyncClient(timeout=3) as client:
            r = await client.get(s.ollama_url.rstrip("/") + "/api/tags")
            r.raise_for_status()
            models = [m["name"] for m in r.json().get("models", [])]
    except Exception as e:  # noqa: BLE001
        return {"reachable": False, "error": str(e)[:200]}
    return {
        "reachable": True,
        "chat_model": s.local_model,
        "chat_model_pulled": any(m.split(":")[0] == s.local_model.split(":")[0] for m in models),
        "embed_model": s.embed_model,
        "embed_model_pulled": any(m.split(":")[0] == s.embed_model.split(":")[0] for m in models),
    }
