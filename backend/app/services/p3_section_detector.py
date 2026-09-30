"""Deterministic Summary/Highlights detection with conservative page bounds."""
import re


SECTION_ALIASES = {
    "executive_summary": "executive summary",
    "key_results": "key results",
    "highlights": "key highlights",
    "summary": "summary",
    "highlights_plain": "highlights",
}


def detect_sections(pages: list[str]) -> list[dict]:
    sections: list[dict] = []
    for page_no, page in enumerate(pages, 1):
        lines = [line.strip() for line in page.splitlines() if line.strip()]
        found_on_page = False
        for index, line in enumerate(lines):
            normalized = re.sub(r"[^a-z ]", " ", line.casefold())
            normalized = re.sub(r"\s+", " ", normalized).strip()
            match = next(((name, alias) for name, alias in SECTION_ALIASES.items() if normalized == alias or normalized.startswith(alias + " ") or (len(line) > 200 and f" {alias} " in f" {normalized} ")), None)
            if not match:
                continue
            name, alias = match
            canonical = "highlights" if name in {"highlights", "highlights_plain"} else name
            # Some ASX PDFs flatten the heading and bullets onto one line.
            inline = re.split(alias, line, flags=re.I, maxsplit=1)[1].strip(" :-") if re.search(alias, line, re.I) else ""
            body_lines = ([inline] if inline else []) + lines[index + 1:]
            body = _bounded_body(body_lines)
            if body:
                sections.append({"name": canonical, "page": page_no, "text": body})
                found_on_page = True
        if not found_on_page and page_no == 1:
            heuristic = _bullet_summary(lines)
            if heuristic:
                sections.append({"name": "summary", "page": page_no, "text": heuristic})
    return sections


def _bounded_body(lines: list[str]) -> str:
    kept: list[str] = []
    for line in lines:
        if kept and _is_boundary(line):
            break
        kept.append(line)
    body = "\n".join(kept).strip()
    # Layout extraction can flatten the whole first page into one line.
    body = re.split(r"\b[A-Z][A-Za-z ]+ Limited.{0,120}?\bis pleased to\b", body, maxsplit=1, flags=re.I)[0]
    return body.strip()


def _is_boundary(line: str) -> bool:
    value = line.casefold().strip()
    return bool(
        re.fullmatch(r"[_\-=]{12,}", line.strip())
        or re.search(r"managing director.{0,80}\bsaid\b", value)
        or re.search(r"\blimited .{0,50}\bis pleased to\b", value)
        or value == "asx announcement"
        or value == "for personal use only"
    )


def _bullet_summary(lines: list[str]) -> str | None:
    starts = [index for index, line in enumerate(lines) if line.lstrip().startswith(("•", "o ", "▪"))]
    if len(starts) < 2:
        return None
    start = starts[0]
    return _bounded_body(lines[start:])
