# main.py
from __future__ import annotations
import argparse
import json
import logging
import re
import sys
from pathlib import Path

from pydantic import ValidationError

from llm_client import LLMClient
from renderer import DashboardRenderer
from schemas import Report

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("agent")


# ---------- Защита от «мусорного» ответа модели ----------

def _has_chinese(text: str) -> bool:
    """Проверяет, есть ли в тексте китайские иероглифы."""
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _validate_json_structure(data: dict) -> list[str]:
    """
    Проверяет, что JSON содержит все необходимые ключи и они непустые.
    Возвращает список проблем (пустой = всё ок).
    """
    problems: list[str] = []

    required_keys = {"meta", "metrics", "sections", "smi"}
    missing = required_keys - set(data.keys())
    if missing:
        problems.append(f"отсутствуют ключи: {sorted(missing)}")

    if not data.get("metrics"):
        problems.append("пустой metrics")
    if not data.get("sections"):
        problems.append("пустой sections")

    # Китайский текст внутри JSON
    json_str = json.dumps(data, ensure_ascii=False)
    if _has_chinese(json_str):
        problems.append("обнаружен китайский текст")

    return problems


def _safe_extract(client: LLMClient, raw: str, max_attempts: int = 2) -> dict | None:
    """
    Вызывает LLM до max_attempts раз, пока не получит корректный JSON
    со всеми нужными ключами и без китайских иероглифов.
    """
    for attempt in range(1, max_attempts + 1):
        log.info("Запрос к LLM, попытка %d/%d", attempt, max_attempts)
        try:
            data = client.extract_report(raw)
        except Exception as e:
            log.error("Ошибка запроса к LLM: %s", e)
            continue

        problems = _validate_json_structure(data)
        if not problems:
            log.info("JSON прошёл проверку структуры.")
            return data

        log.warning("Проблемы с JSON: %s", "; ".join(problems))

    log.error("Не удалось получить корректный JSON за %d попыток.", max_attempts)
    return None


# ---------- Основной пайплайн ----------

def run(
    input_path: Path,
    html_out: Path,
    json_out: Path | None,
    base_url: str,
    model: str,
) -> int:
    raw = input_path.read_text(encoding="utf-8")
    log.info("Прочитан файл %s (%d символов)", input_path, len(raw))

    client = LLMClient(base_url=base_url, model=model)
    data = _safe_extract(client, raw, max_attempts=2)

    if data is None:
        log.error("Агент не смог получить валидный JSON. Дашборд не создан.")
        return 3

    # Сохраняем промежуточный JSON
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("Промежуточный JSON сохранён: %s", json_out)

    # Валидация Pydantic
    try:
        report = Report.model_validate(data)
    except ValidationError as e:
        log.error("JSON не прошёл валидацию Pydantic:\n%s", e)
        return 2

    # Рендер
    renderer = DashboardRenderer(templates_dir=Path(__file__).parent / "templates")
    out = renderer.render(report, html_out)
    log.info("Дашборд готов: %s", out)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="TXT-справка → JSON → HTML-дашборд (Ollama + 14B)"
    )
    p.add_argument("-i", "--input",  type=Path,
                   default=Path("input/итоги_24_30.txt"))
    p.add_argument("-o", "--output", type=Path,
                   default=Path("out/dashboard.html"))
    p.add_argument("-j", "--json",   type=Path,
                   default=Path("out/report.json"))
    p.add_argument("--base-url", default="http://127.0.0.1:11434",
                   help="Ollama через SSH-туннель (локальный порт)")
    p.add_argument("--model", default="qwen2.5:14b-instruct-q4_K_M",
                   help="Имя модели в Ollama")
    args = p.parse_args()

    return run(args.input, args.output, args.json, args.base_url, args.model)


if __name__ == "__main__":
    sys.exit(main())