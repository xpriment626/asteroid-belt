"""OpenRouter / DeepSeek client for the autoresearch agent.

Single-turn pattern: each call is an independent API request with no
conversation state. Sidesteps the multi-turn `reasoning_content` 400 errors
in DeepSeek V4 thinking mode (history is replayed as plain user text instead).
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _load_env() -> None:
    """Load .env from project root if present. Idempotent."""
    env_path = _project_root() / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=False)


@dataclass(frozen=True)
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    reasoning_effort: str  # "low" | "medium" | "high" | "xhigh"

    @classmethod
    def from_env(cls) -> LLMConfig:
        _load_env()
        api_key = os.environ.get("OPENROUTER_API_KEY", "")
        if not api_key:
            raise RuntimeError("OPENROUTER_API_KEY missing. Set it in .env or environment.")
        return cls(
            api_key=api_key,
            base_url=os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1"),
            model=os.environ.get("OPENROUTER_MODEL", "deepseek/deepseek-v4-pro"),
            reasoning_effort=os.environ.get("OPENROUTER_REASONING_EFFORT", "high"),
        )


class LLMClient:
    """Thin wrapper around OpenAI SDK pointed at OpenRouter."""

    def __init__(self, config: LLMConfig | None = None) -> None:
        self.config = config or LLMConfig.from_env()
        self._client = OpenAI(base_url=self.config.base_url, api_key=self.config.api_key)

    def complete(self, *, system: str, user: str) -> str:
        """One independent completion. Returns the assistant text content.

        Reasoning tokens (if any) are discarded — agent only consumes the
        final answer to keep iterations independent.
        """
        resp = self._client.chat.completions.create(
            model=self.config.model,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            extra_body={"reasoning": {"effort": self.config.reasoning_effort}},
        )
        choice = resp.choices[0]
        return choice.message.content or ""
