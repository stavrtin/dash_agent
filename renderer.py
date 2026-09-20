# renderer.py
from __future__ import annotations
from pathlib import Path
import re

from jinja2 import Environment, FileSystemLoader, select_autoescape

from schemas import Report


class DashboardRenderer:
    # Эмодзи → класс Font Awesome
    FA_MAP = {
        "🌐": "fas fa-globe",
        "📞": "fas fa-phone-alt",
        "🚨": "fas fa-bell",
        "📊": "fas fa-chart-bar",
        "🌳": "fas fa-tree",
        "🌲": "fas fa-tree",
        "🔴": "fas fa-exclamation-circle",
        "🟡": "fas fa-exclamation-triangle",
        "🟢": "fas fa-check-circle",
        "💧": "fas fa-water",
        "🌊": "fas fa-water",
        "🌫️": "fas fa-smog",
        "💨": "fas fa-wind",
        "🔥": "fas fa-fire",
        "🗑️": "fas fa-trash-alt",
        "🔊": "fas fa-volume-up",
        "🐾": "fas fa-paw",
        "🦜": "fas fa-dove",
        "🐦": "fas fa-dove",
        "⚖️": "fas fa-gavel",
        "👥": "fas fa-user-cog",
        "📰": "fas fa-newspaper",
        "📅": "fas fa-calendar-alt",
        "📩": "fas fa-envelope",
        "🏭": "fas fa-industry",
        "📉": "fas fa-chart-line",
        "📈": "fas fa-chart-line",
        "🌍": "fas fa-globe",
        "🪓": "fas fa-tree",
        "🪵": "fas fa-tree",
        "🚰": "fas fa-water",
        "🌡️": "fas fa-thermometer-half",
        "🦊": "fas fa-paw",
    }

    def __init__(self, templates_dir: str | Path = "templates"):
        templates_dir = Path(templates_dir).resolve()
        if not templates_dir.exists():
            raise FileNotFoundError(
                f"Папка шаблонов не найдена: {templates_dir}"
            )
        self.env = Environment(
            loader=FileSystemLoader(str(templates_dir)),
            autoescape=select_autoescape(["html", "xml"]),
            trim_blocks=True,
            lstrip_blocks=True,
        )
        # Регистрируем фильтр
        self.env.filters["fa_class"] = self._fa_class
        self.env.filters["dmy"] = self._dmy

    @classmethod
    def _fa_class(cls, emoji: str | None) -> str:
        """Эмодзи → класс Font Awesome. Фолбэк — fa-circle."""
        if not emoji:
            return "fas fa-circle"
        return cls.FA_MAP.get(emoji.strip(), "fas fa-circle")

    def render(self, report: Report, out_path: str | Path) -> Path:
        tpl = self.env.get_template("dashboard.html.j2")
        html = tpl.render(report=report)
        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out

    @staticmethod
    def _dmy(iso_date: str | None) -> str:
        """'2026-09-14' → '14.09.26'. Если формат другой — вернуть как есть."""
        if not iso_date:
            return ""
        s = str(iso_date).strip()
        # ISO YYYY-MM-DD
        m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
        if m:
            y, mo, d = m.group(1), m.group(2), m.group(3)
            return f"{d}.{mo}.{y[2:]}"
        # уже dd.mm.yy или dd.mm.yyyy — оставить как есть
        return s