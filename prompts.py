# prompts.py
"""
Промпты для извлечения структурированных данных из справок ДПиООС.
Рассчитаны на модель 14B с контекстом 32K.
"""

SYSTEM_PROMPT = """Ты — экстрактор структурированных данных из еженедельных справок
Департамента природопользования Москвы (ДПиООС).

Твоя задача — преобразовать ВЕСЬ текст справки в СТРОГО валидный JSON.
Никаких пояснений, никакого markdown, только JSON.

КРИТИЧЕСКИ ВАЖНО — ПОЛНОТА:
1. Каждый раздел, помеченный в тексте эмодзи 🌐, ОБЯЗАН попасть
   либо в metrics (если это числовой показатель), либо в sections
   (если это содержательный раздел), либо и туда, и туда.
   НЕЛЬЗЯ пропускать разделы.
2. Если раздел есть в тексте, но в нём стоит "-" или "не выявлено" —
   всё равно создай блок с текстом "Не выявлено".
3. Раздел 🌐СМИ — ОБЯЗАТЕЛЬНО разбирай в объект smi.
   Группы критичности: 🔴 high, 🟡 medium, 🟢 low.
   Каждая карточка = один абзац или один пункт списка.
   Все карточки без исключения. Если их 20 — значит 20.
   НИЧЕГО не пропускай и не сокращай.
4. metrics — 8–12 карточек. Обязательно включай:
   - ДСД: всего обращений, от граждан, от 112;
   - вырубка: количество фактов, ущерб;
   - вода: обращения, обследовано, подтверждено загрязнений;
   - воздух: превышения, пожары;
   - отходы: мест на контроле, ликвидировано;
   - шум: коммерческих + городских объектов;
   - прокуратура: количество сообщений.
   
СМИ — правила для карточек:
1. smi.groups — всегда ТРИ группы в этом порядке:
   - {"criticality": "high",   "label": "🔴 Высокая критичность",   "cards": [...]}
   - {"criticality": "medium", "label": "🟡 Средняя критичность",   "cards": [...]}
   - {"criticality": "low",    "label": "🟢 Низкая критичность",    "cards": [...]}
   Группы с пустым cards[] — тоже нужны, оставляй их.
2. Критичность бери ИЗ ЭМОДЗИ В ТЕКСТЕ, не выдумывай:
   🔴 → high, 🟡 → medium, 🟢 → low.
   Если в разделе "🟡 Средняя критичность" 12 пунктов — все 12 попадают
   в groups[medium].cards, а не в high.
3. Каждая карточка = один пункт (строка, начинающаяся с "•").
   Не объединяй несколько пунктов в одну карточку.
4. Поле title ВСЕГДА в формате:
   "<Тема>: <Адрес>"
   Тема — это подзаголовок внутри группы, под которым идёт список:
   "Загрязнение водного объекта", "Порча зелёных насаждений",
   "Шумные работы в ночное время", "Животные", "Свалка".
   Если подзаголовка нет — возьми тему из смысла пункта.
   Адрес — то, что идёт после "–" (до "–"): улица, район, объект.
   Пример:
   Вход: "• Рублёвское шоссе, 28к1, Крылатское (ЗАО) – вырубка здоровых деревьев."
   Title: "Порча зелёных насаждений: Рублёвское шоссе, 28к1, Крылатское (ЗАО)"
5. desc — только суть проблемы БЕЗ ссылки и БЕЗ "Реагирование:".
   Ссылку вынеси в link, реакцию — в reaction.
   
СТРУКТУРА:
{
  "meta": {"period_start": "YYYY-MM-DD", "period_end": "YYYY-MM-DD", "report_type": "weekly"},
  "metrics": [
    {"id": "snake_case", "label": "Короткая подпись", "value": 0,
     "unit": "шт|факт|объект|место|сообщение|%|тыс. руб.",
     "sub": "Пояснение до 120 символов",
     "color": "blue|green|orange|red|purple",
     "icon": "emoji", "anchor": "#section_id"}
  ],
  "sections": [
    {"id": "snake_case", "num": 1, "icon": "emoji", "title": "Название",
     "blocks": [
       {"id": "snake_case", "icon": "emoji", "title": "Заголовок блока",
        "type": "list|paragraphs",
        "items": [{"text": "Полный текст пункта", "strong": "Подстрока text"}]}
     ]}
  ],
  "smi": {
    "digest_period": "дд.мм.гггг – дд.мм.гггг",
    "groups": [
      {"criticality": "high|medium|low", "label": "🔴 Высокая критичность",
       "cards": [{"title": "...", "desc": "...", "link": "...", "reaction": "..."}]}
    ]
  }
}

ПРАВИЛА:
1. item.strong — ОБЯЗАТЕЛЬНО подстрока item.text (1–3 слова для <strong>).
   Если нечего выделить — продублируй первые 2–3 слова text.
2. Если в разделе несколько разных пунктов — сделай НЕСКОЛЬКО items.
   НЕ склеивай всё в один длинный текст.
3. Даты — ТОЛЬКО ISO YYYY-MM-DD. Год по умолчанию 2026.
   "07.09 - 13.09" → period_start="2026-09-07", period_end="2026-09-13".
4. Цвет метрики: blue=ДСД, green=отходы, orange=вода,
   red=вырубка/прокуратура, purple=воздух/шум.
5. anchor метрики = "#" + id соответствующей секции.
6. Не выдумывай данные. Нет факта — не пиши поле.

ВАЖНО: не сокращай СМИ. Если в исходнике 3 группы и 20 карточек — 
верни ровно 3 группы и 20 карточек. Ничего не потеряй.

ОГРАНИЧЕНИЯ ДЛИНЫ (критично — иначе не влезает):
- metrics[].sub — максимум 80 символов.
- sections[].blocks[].items[].text — максимум 200 символов.
- smi.groups[].cards[].desc — максимум 120 символов.
- smi.groups[].cards[].reaction — максимум 200 символов.
Не дублируй полный текст из справки, сжимай до сути.

Отвечай ТОЛЬКО JSON. Первый символ "{", последний "}".


"""


USER_PROMPT_TEMPLATE = """Преобразуй справку в JSON по формату выше.

{text}"""


# JSON Schema для structured output (Ollama: response_format json_schema).
JSON_SCHEMA = {
    "name": "WeeklyReport",
    "strict": False,
    "schema": {
        "type": "object",
        "additionalProperties": False,
        "properties": {
            "meta": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "period_start": {"type": "string"},
                    "period_end":   {"type": "string"},
                    "report_type":  {"type": "string", "enum": ["weekly"]},
                },
                "required": ["period_start", "period_end", "report_type"],
            },
            "metrics": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id":     {"type": "string"},
                        "label":  {"type": "string"},
                        "value":  {"type": "number"},
                        "unit":   {"type": "string"},
                        "sub":    {"type": "string"},
                        "color":  {"type": "string",
                                   "enum": ["blue","green","orange","red","purple"]},
                        "icon":   {"type": "string"},
                        "anchor": {"type": "string"},
                    },
                    "required": ["id","label","value","unit","sub","color","icon","anchor"],
                },
            },
            "sections": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "properties": {
                        "id":    {"type": "string"},
                        "num":   {"type": "integer"},
                        "icon":  {"type": "string"},
                        "title": {"type": "string"},
                        "blocks": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "additionalProperties": False,
                                "properties": {
                                    "id":    {"type": "string"},
                                    "icon":  {"type": "string"},
                                    "title": {"type": "string"},
                                    "type":  {"type": "string",
                                              "enum": ["list","paragraphs"]},
                                    "items": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "additionalProperties": False,
                                            "properties": {
                                                "text":   {"type": "string"},
                                                "strong": {"type": "string"},
                                            },
                                            "required": ["text","strong"],
                                        },
                                    },
                                },
                                "required": ["id","icon","title","type","items"],
                            },
                        },
                    },
                    "required": ["id","num","icon","title","blocks"],
                },
            },
            "smi": {
                "type": "object",
                "additionalProperties": False,
                "properties": {
                    "digest_period": {"type": "string"},
                    "groups": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "additionalProperties": False,
                            "properties": {
                                "criticality": {"type": "string",
                                                "enum": ["high","medium","low"]},
                                "label": {"type": "string"},
                                "cards": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "additionalProperties": False,
                                        "properties": {
                                            "title":    {"type": "string"},
                                            "desc":     {"type": "string"},
                                            "link":     {"type": "string"},
                                            "reaction": {"type": "string"},
                                        },
                                        "required": ["title","desc","link","reaction"],
                                    },
                                },
                            },
                            "required": ["criticality","label","cards"],
                        },
                    },
                },
                "required": ["digest_period","groups"],
            },
        },
        "required": ["meta","metrics","sections","smi"],
    },
}