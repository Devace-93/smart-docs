"""Markdown to sanitized HTML, YAML front matter and llms.txt generation."""

from __future__ import annotations

import re
from datetime import datetime

import nh3
from markdown_it import MarkdownIt

_md = (
    MarkdownIt("commonmark", {"html": True, "linkify": False, "typographer": False})
    .enable("table")
    .enable("strikethrough")
)

_ALLOWED_TAGS = nh3.ALLOWED_TAGS | {
    "table",
    "thead",
    "tbody",
    "tr",
    "th",
    "td",
    "input",
    "details",
    "summary",
    "img",
    "pre",
    "code",
    "del",
}
_ALLOWED_ATTRS = {
    **{k: set(v) for k, v in nh3.ALLOWED_ATTRIBUTES.items()},
    "a": {"href", "title"},
    "img": {"src", "alt", "title", "width", "height"},
    "input": {"type", "checked", "disabled"},
    "th": {"align"},
    "td": {"align"},
    "code": {"class"},
}


def render_html(markdown: str) -> str:
    """Render CommonMark and strip anything that could run script on a public page."""
    raw = _md.render(markdown or "")
    return nh3.clean(
        raw,
        tags=_ALLOWED_TAGS,
        attributes=_ALLOWED_ATTRS,
        url_schemes={"http", "https", "mailto"},
        link_rel="noopener noreferrer",
    )


_heading = re.compile(r"^\s{0,3}#{1,6}\s+(.+?)\s*#*\s*$", re.MULTILINE)


def first_heading(markdown: str) -> str | None:
    m = _heading.search(markdown or "")
    return m.group(1).strip() if m else None


def plain_excerpt(markdown: str, limit: int = 200) -> str:
    text = re.sub(r"```.*?```", " ", markdown or "", flags=re.DOTALL)
    text = re.sub(r"[#>*_`\[\]()!-]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:limit].rstrip() + ("…" if len(text) > limit else "")


def _yaml_str(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ") + '"'


def front_matter(*, title: str, summary: str, tags: list[str], updated: datetime, canonical: str) -> str:
    lines = [
        "---",
        f"title: {_yaml_str(title)}",
        f"summary: {_yaml_str(summary)}",
        "tags: [" + ", ".join(_yaml_str(t) for t in tags) + "]",
        f"updated: {updated.strftime('%Y-%m-%dT%H:%M:%SZ')}",
        f"canonical: {canonical}",
        "---",
        "",
    ]
    return "\n".join(lines)


def markdown_with_front_matter(markdown: str, **meta) -> str:
    return front_matter(**meta) + (markdown or "")


def llms_txt(*, project_name: str, description: str, base_url: str, pages: list[dict]) -> str:
    """The llms.txt convention: H1, blockquote description, then one link line per page."""
    out = [f"# {project_name}", ""]
    if description:
        out += [f"> {description}", ""]
    out.append("## Pages")
    out.append("")
    for p in pages:
        summary = p.get("summary") or ""
        line = f"- [{p['title']}]({base_url}/{p['path']}.md)"
        if summary:
            line += f": {summary}"
        out.append(line)
    out.append("")
    return "\n".join(out)


def llms_full_txt(*, project_name: str, description: str, base_url: str, pages: list[dict]) -> str:
    out = [f"# {project_name}", ""]
    if description:
        out += [f"> {description}", ""]
    for p in pages:
        out.append(f"<!-- {base_url}/{p['path']}.md -->")
        out.append(p["body"])
        out.append("")
    return "\n".join(out)
