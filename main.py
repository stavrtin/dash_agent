# main.py
from __future__ import annotations
import argparse
import json
import logging
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
    data = client.extract_report(raw)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        log.info("Промежуточный JSON сохранён: %s", json_out)

    try:
        report = Report.model_validate(data)
    except ValidationError as e:
        log.error("JSON не прошёл валидацию Pydantic:\n%s", e)
        return 2

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
                   help="Адрес Ollama (через SSH-туннель = 127.0.0.1:11434)")
    p.add_argument("--model", default="qwen2.5:14b-instruct-q4_K_M",
                   help="Имя модели в Ollama")
    args = p.parse_args()

    return run(args.input, args.output, args.json, args.base_url, args.model)


if __name__ == "__main__":
    sys.exit(main())