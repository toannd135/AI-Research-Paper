"""Nhận diện section/heading trong paper."""

import re
from dataclasses import dataclass

from app.pipeline.parser.pdf_parser import PageText

_COMMON_SECTIONS = {
    "abstract",
    "introduction",
    "related work",
    "background",
    "method",
    "methodology",
    "approach",
    "experiment",
    "experiments",
    "experimental setup",
    "results",
    "evaluation",
    "discussion",
    "conclusion",
    "conclusions",
    "references",
    "acknowledgments",
    "acknowledgements",
    "appendix",
}
_NUMBERED_HEADING = re.compile(r"^\s*\d{1,2}(\.\d{1,2})*[.\s]+[A-Z][A-Za-z ]{2,60}\s*$")


@dataclass
class Section:
    title: str
    page: int
    start_char: int


def is_heading(line: str) -> bool:
    stripped = line.strip()
    if not stripped or len(stripped) > 80:
        return False
    if _NUMBERED_HEADING.match(stripped):
        return True
    return stripped.lower().rstrip(":") in _COMMON_SECTIONS


def detect_sections(pages: list[PageText]) -> list[Section]:
    """Quét từng dòng trong từng trang, thu thập vị trí các heading."""
    sections: list[Section] = []
    for page in pages:
        offset = 0
        for line in page.text.splitlines(keepends=True):
            if is_heading(line):
                sections.append(Section(title=line.strip().rstrip(":"), page=page.page, start_char=offset))
            offset += len(line)
    return sections


def assign_section(page: int, char_offset: int, sections: list[Section]) -> str | None:
    """Trả về title của heading gần nhất trước vị trí (page, char_offset)."""
    current: str | None = None
    for section in sections:
        if (section.page, section.start_char) <= (page, char_offset):
            current = section.title
        else:
            break
    return current
