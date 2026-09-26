# llm_client.py
"""
Клиент для Ollama через нативный /api/chat.
Работает с моделью 14B на удалённом сервере через SSH-туннель.
Ремонт JSON: json-repair → escape control chars → repair truncated.
"""
from __future__ import annotations
import json
import logging
import re
from typing import Any

import requests
from prompts import JSON_SCHEMA

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    repair_json = None

from prompts import SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(
        self,
        base_url: str = "http://127.0.0.1:11434",
        model: str = "qwen2.5:14b-instruct-q4_K_M",
        temperature: float = 0.1,
        top_p: float = 0.95,
        max_tokens: int = 16000,
        num_ctx: int = 16384,
        timeout: float = 900.0,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_tokens = max_tokens
        self.num_ctx = num_ctx
        self.timeout = timeout
        log.info(
            "LLMClient: base_url=%s, model=%s, num_ctx=%d, max_tokens=%d, json_repair=%s",
            self.base_url, self.model, self.num_ctx, self.max_tokens, HAS_JSON_REPAIR,
        )

    # ------------------------------------------------------------------ public
    def extract_report(self, raw_text: str) -> dict[str, Any]:
        user_prompt = USER_PROMPT_TEMPLATE.format(text=raw_text)
        return self._call(SYSTEM_PROMPT, user_prompt)

    # ----------------------------------------------------------------- private
    def _call(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        url = f"{self.base_url}/api/chat"

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_prompt},
            ],
            "stream": False,
            # "format": "json",   # ← грамматика Ollama: только валидный JSON
            "format": JSON_SCHEMA["schema"],
            "options": {
                "temperature": self.temperature,
                "top_p": self.top_p,
                "num_predict": self.max_tokens,
                "num_ctx": self.num_ctx,
            },
        }

        log.info("POST %s, payload=%d байт",
                 url, len(json.dumps(payload, ensure_ascii=False)))
        r = requests.post(url, json=payload, timeout=self.timeout)
        log.info("HTTP %s, ответ %d байт", r.status_code, len(r.content))
        r.raise_for_status()

        data = r.json()
        content = data.get("message", {}).get("content", "")
        content = self._strip_code_fence(content)

        if "eval_count" in data:
            log.info(
                "Токены: prompt=%s, eval=%s, done=%s, done_reason=%s",
                data.get("prompt_eval_count"),
                data.get("eval_count"),
                data.get("done"),
                data.get("done_reason"),
            )

        # =====================  ЦЕПОЧКА РЕМОНТА JSON  =====================

        # Шаг 0: обычный json.loads — как есть
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning("json.loads упал: %s. Пробую json-repair...", e)

        # Шаг 1: json-repair — самый мощный ремонт
        if HAS_JSON_REPAIR:
            try:
                data2 = repair_json(content, return_objects=True)
                if isinstance(data2, dict) and data2:
                    log.info("JSON успешно отремонтирован через json-repair.")
                    return data2
                log.warning("json-repair вернул не-словарь: %r", type(data2))
            except Exception as e:
                log.warning("json-repair не справился: %s", e)

        # Шаг 2: escape control chars + repair truncated
        escaped = self._escape_control_chars(content)
        repaired = self._repair_truncated_json(escaped)
        if repaired is not None:
            try:
                result = json.loads(repaired)
                log.info("JSON успешно отремонтирован (escape + repair).")
                return result
            except json.JSONDecodeError as e:
                log.warning("После escape + repair всё ещё невалидный: %s", e)

        # Шаг 3: сдаёмся
        log.error("Невалидный JSON. Первые 800 символов:\n%s", content[:800])
        raise RuntimeError("Невалидный JSON от LLM")

    # ---------------------------------------------------------------- helpers
    @staticmethod
    def _strip_code_fence(s: str) -> str:
        s = s.strip()
        if s.startswith("```"):
            s = s.split("\n", 1)[1] if "\n" in s else s
            if s.endswith("```"):
                s = s[:-3]
        return s.strip()

    @staticmethod
    def _escape_control_chars(s: str) -> str:
        """
        Заменяет сырые управляющие символы (\\n, \\r, \\t) внутри JSON-строк
        на их escape-последовательности. Символы ВНЕ строк не трогает.
        """
        out = []
        in_string = False
        escape = False

        for ch in s:
            if escape:
                out.append(ch)
                escape = False
                continue

            if ch == "\\" and in_string:
                out.append(ch)
                escape = True
                continue

            if ch == '"':
                in_string = not in_string
                out.append(ch)
                continue

            if in_string:
                if ch == "\n":
                    out.append("\\n")
                elif ch == "\r":
                    out.append("\\r")
                elif ch == "\t":
                    out.append("\\t")
                else:
                    out.append(ch)
            else:
                out.append(ch)

        return "".join(out)

    @staticmethod
    def _repair_truncated_json(s: str) -> str | None:
        """Закрывает обрыв JSON: кавычку, скобки, висячие запятые."""
        s = s.strip()
        if not s or s[0] != "{":
            return None

        in_string = False
        escape = False
        stack: list[str] = []

        for ch in s:
            if escape:
                escape = False
                continue
            if ch == "\\" and in_string:
                escape = True
                continue
            if ch == '"':
                in_string = not in_string
                continue
            if in_string:
                continue
            if ch == "{":
                stack.append("}")
            elif ch == "[":
                stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()

        fixed = s
        if in_string:
            fixed += '"'
        fixed = re.sub(r"[,:]\s*$", "", fixed)
        fixed += "".join(reversed(stack))
        return fixed