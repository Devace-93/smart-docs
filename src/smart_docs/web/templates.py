"""Jinja2 environment shared by the public pages and the editor shell."""

from __future__ import annotations

from pathlib import Path

from fastapi.templating import Jinja2Templates

from smart_docs.config import get_settings

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _globals() -> dict:
    s = get_settings()
    return {
        "instance_name": s.instance_name,
        "footer_text": s.footer_text,
        "footer_url": s.footer_url,
        "info_url": s.info_url,
        "public_base_url": s.public_base_url.rstrip("/"),
        "accounts_url": s.accounts_url.rstrip("/"),
        "signups_open": s.signups_open,
        "retro_project_key": s.retro_project_key,
        "retro_widget_url": s.retro_widget_url,
        "metrics_project_key": s.metrics_project_key,
        "metrics_tracker_url": s.metrics_tracker_url,
    }


templates.env.globals.update(_globals())
