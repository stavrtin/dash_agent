# llm_client.py
"""
Универсальный клиент для OpenAI-совместимых API и Ollama.
Использует официальный SDK openai (>=1.40).
Ремонт JSON: json-repair → escape control chars → repair truncated.
"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from openai import OpenAI
from openai import APIError, APITimeoutError

from config import LLMConfig
from prompts import JSON_SCHEMA, SYSTEM_PROMPT, USER_PROMPT_TEMPLATE

try:
    from json_repair import repair_json
    HAS_JSON_REPAIR = True
except ImportError:
    HAS_JSON_REPAIR = False
    repair_json = None

log = logging.getLogger(__name__)


class LLMClient:
    def __init__(self, config: LLMConfig):
        self.config = config

        # OpenAI SDK: для Ollama ключ можно любой, но не пустой
        api_key = config.api_key or ("ollama" if config.is_ollama else "")
        if not api_key:
            raise ValueError(
                "Не задан OPENAI_API_KEY. Укажите его в .env или через переменную окружения."
            )

        self.client = OpenAI(
            api_key=api_key,
            base_url=config.base_url,
            timeout=config.timeout,
            max_retries=1,
        )

        log.info(
            "LLMClient: base_url=%s, model=%s, json_repair=%s",
            config.base_url, config.model, HAS_JSON_REPAIR,
        )

    # ------------------------------------------------------------------ public
    def extract_report(self, raw_text: str) -> dict[str, Any]:
        user_prompt = USER_PROMPT_TEMPLATE.format(text=raw_text)
        return self._call(SYSTEM_PROMPT, user_prompt)

    # ----------------------------------------------------------------- private
    def _call(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        log.info("Запрос к LLM: model=%s", self.config.model)

        # Формируем response_format.
        # Для OpenAI json_schema работает стабильно; для Ollama / DeepSeek
        # достаточно {"type": "json_object"} — schema иногда ломает совместимость.
        response_format: dict[str, Any]
        if self.config.is_ollama:
            # Ollama /v1 понимает json_object, но не json_schema
            response_format = {"type": "json_object"}
        else:
            response_format = {
                "type": "json_schema",
                "json_schema": {
                    "name": JSON_SCHEMA["name"],
                    "strict": JSON_SCHEMA["strict"],
                    "schema": JSON_SCHEMA["schema"],
                },
            }

        try:
            resp = self.client.chat.completions.create(
                model=self.config.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user",   "content": user_prompt},
                ],
                temperature=self.config.temperature,
                top_p=self.config.top_p,
                max_tokens=self.config.max_tokens,
                response_format=response_format,
            )
        except APITimeoutError as e:
            log.error("Таймаут LLM: %s", e)
            raise
        except APIError as e:
            log.error("Ошибка API LLM: %s", e)
            raise

        content = (resp.choices[0].message.content or "").strip()
        content = self._strip_code_fence(content)

        usage = getattr(resp, "usage", None)
        if usage:
            log.info(
                "Токены: prompt=%s, completion=%s, total=%s",
                getattr(usage, "prompt_tokens", "?"),
                getattr(usage, "completion_tokens", "?"),
                getattr(usage, "total_tokens", "?"),
            )

        # =====================  ЦЕПОЧКА РЕМОНТА JSON  =====================
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            log.warning("json.loads упал: %s. Пробую json-repair...", e)

        if HAS_JSON_REPAIR:
            try:
                data2 = repair_json(content, return_objects=True)
                if isinstance(data2, dict) and data2:
                    log.info("JSON успешно отремонтирован через json-repair.")
                    return data2
                log.warning("json-repair вернул не-словарь: %r", type(data2))
            except Exception as e:
                log.warning("json-repair не справился: %s", e)

        escaped = self._escape_control_chars(content)
        repaired = self._repair_truncated_json(escaped)
        if repaired is not None:
            try:
                result = json.loads(repaired)
                log.info("JSON успешно отремонтирован (escape + repair).")
                return result
            except json.JSONDecodeError as e:
                log.warning("После escape + repair всё ещё невалидный: %s", e)

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
        out = []
        in_string = False
        escape = False
        for ch in s:
            if escape:
                out.append(ch); escape = False; continue
            if ch == "\\" and in_string:
                out.append(ch); escape = True; continue
            if ch == '"':
                in_string = not in_string; out.append(ch); continue
            if in_string:
                if ch == "\n":   out.append("\\n")
                elif ch == "\r": out.append("\\r")
                elif ch == "\t": out.append("\\t")
                else:            out.append(ch)
            else:
                out.append(ch)
        return "".join(out)

    @staticmethod
    def _repair_truncated_json(s: str) -> str | None:
        s = s.strip()
        if not s or s[0] != "{":
            return None
        in_string = False
        escape = False
        stack: list[str] = []
        for ch in s:
            if escape:
                escape = False; continue
            if ch == "\\" and in_string:
                escape = True; continue
            if ch == '"':
                in_string = not in_string; continue
            if in_string:
                continue
            if ch == "{":   stack.append("}")
            elif ch == "[": stack.append("]")
            elif ch in "}]":
                if stack and stack[-1] == ch:
                    stack.pop()
        fixed = s
        if in_string:
            fixed += '"'
        fixed = re.sub(r"[,:]\s*$", "", fixed)
        fixed += "".join(reversed(stack))
        return fixed