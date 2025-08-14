from django import template
import re

register = template.Library()

HEADING_HASHES_RE = re.compile(r"^(\s{0,3})#{1,6}(\s+)")

@register.filter(name='md_sanitize_headings')
def md_sanitize_headings(value: str) -> str:
    """
    Sanitize markdown-ish headings by stripping leading '#' in heading lines.
    This prevents '### ' appearing in rendered content from AI-generated text.
    Works line-by-line; leaves normal text intact.
    """
    if not value:
        return value
    lines = str(value).splitlines()
    cleaned = []
    for ln in lines:
        cleaned.append(HEADING_HASHES_RE.sub(r"\1\2", ln))
    return "\n".join(cleaned)
