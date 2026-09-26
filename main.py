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


# ============================================================================
# Защита от «мусорного» ответа модели
# ============================================================================
REQUIRED_SECTIONS = {
    "prosecutor",   # Прокуратура
    "experts",      # Привлечение специалистов
    "air",          # Воздух
    "water",        # Вода
    "land_pollution",  # Отходы
}

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

    # Проверка обязательных секций
    present_sections = {s.get("id", "") for s in data.get("sections", [])}
    missing_sections = REQUIRED_SECTIONS - present_sections
    if missing_sections:
        problems.append(f"отсутствуют секции: {sorted(missing_sections)}")

    return problems

    return problems


# ============================================================================
# Санитайзер метрик: подстановка осмысленных label
# ============================================================================

# Соответствие «id метрики» → «человекочитаемый label».
# Срабатывает, если модель вернула label, совпадающий с названием раздела.
_LABEL_FIXES = {
    # --- ДСД / Обращения ---
    "dsd":                     "Всего обращений",
    "dsd_total":               "Всего обращений",
    "dsd_citizens":            "От граждан",
    "dsd_citizen_calls":       "От граждан",
    "dsd_112":                 "От 112",
    "dsd_from_112":            "От 112",
    "calls":                   "Обращений",
    "calls_total":             "Обращений",
    "calls_weekly_change":     "Изменение к прошлой неделе",
    "calls_yearly_change":     "Изменение к прошлому году",

    # --- Незаконная вырубка ---
    "illegal_felling":         "Фактов незаконной вырубки",
    "illegal_felling_count":   "Фактов незаконной вырубки",
    "illegal_felling_fact":    "Фактов незаконной вырубки",
    "illegal_felling_damage":  "Ущерб от незаконной вырубки",
    "vyrubka":                 "Фактов незаконной вырубки",

    # --- Падение деревьев ---
    "falling_trees":           "Фактов падения деревьев",
    "fallen_trees":            "Фактов падения деревьев",
    "tree_fall":               "Фактов падения деревьев",

    # --- Вода ---
    "water_complaints":        "Обращений по воде",
    "water_investigated":      "Обследовано водных объектов",
    "water_surveyed":          "Обследовано водных объектов",
    "water_pollution":         "Загрязнений подтверждено",
    "water":                   "Обращений по воде",

    # --- Воздух ---
    "air_exceedances":         "Превышений по воздуху",
    "air_pollution":           "Превышений по воздуху",
    "air_fires":               "Природных пожаров",
    "air_fire":                "Природных пожаров",
    "air_smell":               "Жалоб на запах",
    "air":                     "Превышений по воздуху",

    # --- Отходы / почвы ---
    "waste_control":           "Мест на контроле",
    "waste_places":            "Мест на контроле",
    "waste_removed":           "Ликвидировано",
    "waste_liquidated":        "Ликвидировано",
    "waste":                   "Мест на контроле",
    "zahlamleniya":            "Мест на контроле",

    # --- Шум ---
    "noise_commercial":        "Превышений: коммерческие объекты",
    "noise_city":              "Превышений: городские объекты",
    "noise_total":             "Превышений по шуму",
    "noise":                   "Превышений по шуму",
    "shum":                    "Превышений по шуму",

    # --- Животные ---
    "animals_incidents":       "Происшествий с животными",
    "animals":                 "Происшествий с животными",

    # --- Прокуратура ---
    "prosecutor_reports":      "Сообщений из прокуратуры",
    "prosecutor_week":         "Изменение к прошлой неделе",
    "prosecutor_year":         "Изменение к прошлому году",
    "prosecutor":              "Сообщений из прокуратуры",
    "prosecutor_total":        "Сообщений из прокуратуры",

    # --- Специалисты ---
    "experts":                 "Проверок с привлечением специалистов",
    "experts_gek":             "Проверок УГЭК",
    "experts_mem":             "Проверок МЭМ",
}

# Названия разделов, которые модель иногда кладёт в label.
# Если label совпадает с одним из них — заменяем на осмысленный.
_GENERIC_LABELS = {
    "воздух", "вода", "отходы", "шум", "прокуратура", "дсд",
    "вырубка", "незаконная вырубка", "животные", "падение деревьев",
    "загрязнение почв", "загрязнение почв и сброс отходов",
    "привлечение специалистов", "привлечение специалистов/экспертов",
    "обращения", "дата",
}


def _fix_metric_labels(data: dict) -> dict:
    """
    Подставляет осмысленные label для известных id метрик,
    если модель вернула слишком короткое название или название раздела.
    """
    for m in data.get("metrics", []):
        mid = (m.get("id") or "").strip()
        current = (m.get("label") or "").strip()
        current_low = current.lower()

        # Подставляем, если:
        #   1) id известен, И
        #   2) label пустой ИЛИ label совпадает с названием раздела
        if mid in _LABEL_FIXES and (
            not current or current_low in _GENERIC_LABELS
        ):
            m["label"] = _LABEL_FIXES[mid]
            log.info(
                "Заменён label метрики '%s': '%s' → '%s'",
                mid, current, m["label"],
            )

    return data


# ============================================================================
# Безопасный вызов LLM с проверкой структуры
# ============================================================================

def _safe_extract(client: LLMClient, raw: str, max_attempts: int = 3) -> dict | None:
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
            data = _fix_metric_labels(data)
            return data

        log.warning("Проблемы с JSON: %s", "; ".join(problems))

    log.error("Не удалось получить корректный JSON за %d попыток.", max_attempts)
    return None


# ============================================================================
# Основной пайплайн
# ============================================================================

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
    data = _safe_extract(client, raw, max_attempts=3)

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