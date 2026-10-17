"""
Which LLM to use: "ollama" (local, free) or "claude" (Claude API: ANTHROPIC_API_KEY, else the team key in team_key.py).

    from src.ai.llm.providers import get_llm, available
    available()          # {"ollama": True, "claude": False}
    llm = get_llm()      # first available, in PREFERENCE order (or LABX_LLM=ollama|claude); None = rules + templates
"""
from __future__ import annotations
import os
from typing import Optional

from .team_key import api_key

PREFERENCE = ("ollama", "claude")


def available() -> dict[str, bool]:
    from .ollama_client import is_available
    return {"ollama": is_available(),
            "claude": bool(api_key() or os.environ.get("ANTHROPIC_AUTH_TOKEN"))}


def get_llm(name: Optional[str] = None):
    """A client for `name` (or LABX_LLM, or the first available provider), or None if none is available."""
    status = available()
    name = name or os.environ.get("LABX_LLM") or next((p for p in PREFERENCE if status[p]), None)
    if name is None or not status.get(name):
        return None
    if name == "ollama":
        from .ollama_client import OllamaClient
        return OllamaClient()
    from .anthropic_client import AnthropicClient
    return AnthropicClient()
