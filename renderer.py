# renderer.py
from __future__ import annotations
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from schemas import Report


class DashboardRenderer:
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

    def render(self, report: Report, out_path: str | Path) -> Path:
        tpl = self.env.get_template("dashboard.html.j2")
        html = tpl.render(report=report)

        out = Path(out_path)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(html, encoding="utf-8")
        return out