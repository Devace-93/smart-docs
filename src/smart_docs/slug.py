"""Slugs for handles, projects and node paths."""

from __future__ import annotations

import re
import unicodedata

_non_word = re.compile(r"[^a-z0-9]+")


def slugify(value: str, *, max_length: int = 80) -> str:
    value = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    value = _non_word.sub("-", value.lower()).strip("-")
    value = re.sub(r"-{2,}", "-", value)
    return value[:max_length].strip("-") or "untitled"


def is_valid_slug(value: str) -> bool:
    return bool(re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,78}[a-z0-9])?", value))
