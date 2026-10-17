"""
The team's shared Claude API key, so every group member can use the Claude provider without setting anything.
`ANTHROPIC_API_KEY`, when set, wins over this one.

The repository is private (checked 2026-10-16). Remove this key, and revoke it in the Anthropic console, before
the repository is made public or shared outside the team (teachers, future students): anyone who has this file can
spend the team's credit.
"""
from __future__ import annotations
import os
from typing import Optional

TEAM_API_KEY = "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"


def api_key() -> Optional[str]:
    """The key to use: the environment's if set, otherwise the team's."""
    return os.environ.get("ANTHROPIC_API_KEY") or TEAM_API_KEY or None
