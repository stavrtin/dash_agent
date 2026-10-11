# config.py
"""
Загрузка конфигурации из .env / переменных окружения.
"""
from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

log = logging.getLogger(__name__)


def _load_env() -> None:
    """Ищет .env рядом с проектом (в порядке приоритета)."""
    candidates = [
        Path.cwd() / ".env",
        Path(__file__).parent / ".env",
    ]
    for p in candidates:
        if p.exists():
            load_dotenv(p, override=False)
            log.info("Загружен .env: %s", p)
            return
    log.info(".env не найден — работаем на переменных окружения")


@dataclass
class LLMConfig:
    api_key: str
    base_url: str
    model: str
    temperature: float = 0.1
    top_p: float = 0.95
    max_tokens: int = 16000
    timeout: float = 900.0

    @property
    def is_ollama(self) -> bool:
        """Ollama определяется по порту/хосту и/или dummy-ключу."""
        u = self.base_url.lower()
        return (
            "11434" in u
            or "ollama" in u
            or self.api_key.strip().lower() in {"ollama", "", "none"}
        )


def load_llm_config(
    *,
    api_key: str | None = None,
    base_url: str | None = None,
    model: str | None = None,
) -> LLMConfig:
    """
    Приоритет: аргумент CLI → переменная окружения → дефолт.
    """
    _load_env()

    api_key = (
        api_key
        or os.getenv("OPENAI_API_KEY")
        or os.getenv("LLM_API_KEY")
        or ""
    ).strip()

    base_url = (
        base_url
        or os.getenv("OPENAI_BASE_URL")
        or os.getenv("LLM_BASE_URL")
        or "https://api.openai.com/v1"
    ).strip().rstrip("/")

    model = (
        model
        or os.getenv("LLM_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "gpt-4o-mini"
    ).strip()

    cfg = LLMConfig(api_key=api_key, base_url=base_url, model=model)

    log.info(
        "LLM-конфиг: base_url=%s, model=%s, api_key=%s, provider=%s",
        cfg.base_url,
        cfg.model,
        ("***" + cfg.api_key[-4:]) if cfg.api_key else "<empty>",
        "ollama" if cfg.is_ollama else "openai-compatible",
    )
    return cfg