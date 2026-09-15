# validator.py
"""
Проверка, что все 🌐-разделы исходного текста попали в JSON.
"""
from __future__ import annotations
import re
from typing import Any

SECTION_RE = re.compile(r"🌐\s*([^\n\r]+)")

SKIP_KEYS = {"дата", "обращения"}

SECTION_ALIASES: dict[str, list[str]] = {
    "дсд":                ["dsd"],
    "незаконная вырубка": ["vyrubka", "вырубк"],
    "падение деревьев":   ["padenie", "падени", "дерев"],
    "вода":               ["voda", "vody", "вод"],
    "воздух":             ["vozdukh", "воздух"],
    "загрязнение почв":   ["zahlamleniya", "zahlam", "отход", "захламл"],
    "шум":                ["shum", "шум"],
    "животные":           ["zhivotnye", "zhivot", "животн"],
    "прокуратура":        ["prokuratura", "прокурат"],
    "привлечение":        ["spetsialist", "эксперт", "привлечен"],
    "сми":                ["smi", "сми"],
}


def _normalize(s: str) -> str:
    return s.strip().lower().replace("ё", "е")


def extract_section_headers(raw_text: str) -> list[str]:
    headers = []
    for m in SECTION_RE.finditer(raw_text):
        title = m.group(1).strip()
        if _normalize(title) in SKIP_KEYS:
            continue
        headers.append(title)
    return headers


def _json_has_section(data: dict[str, Any], header: str) -> bool:
    h = _normalize(header)
    haystack: list[str] = []

    for s in data.get("sections", []):
        haystack.append(_normalize(s.get("id", "")))
        haystack.append(_normalize(s.get("title", "")))
        for b in s.get("blocks", []):
            haystack.append(_normalize(b.get("id", "")))
            haystack.append(_normalize(b.get("title", "")))

    for m in data.get("metrics", []):
        haystack.append(_normalize(m.get("id", "")))
        haystack.append(_normalize(m.get("label", "")))

    smi = data.get("smi") or {}
    if smi.get("groups"):
        haystack.append("сми")
        haystack.append("smi")

    blob = " | ".join(haystack)

    if h in blob:
        return True

    for key, aliases in SECTION_ALIASES.items():
        if key in h:
            if any(a in blob for a in aliases):
                return True

    first_word = h.split()[0] if h.split() else h
    return len(first_word) >= 4 and first_word in blob


def check_completeness(raw_text: str, data: dict[str, Any]) -> list[str]:
    missing: list[str] = []
    for header in extract_section_headers(raw_text):
        if not _json_has_section(data, header):
            missing.append(header)
    return missing