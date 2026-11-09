from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

import pdfplumber

HEADING_MIN_SIZE = 11.5
CHROME_MAX_SIZE = 9.0  # cabeçalho e rodapé de página (8 pt)
SKIP_PAGES = {1}  # capa: os mesmos dados aparecem na seção 1.2
MAX_CHUNK_CHARS = 1400
LINE_TOLERANCE = 2.5

_HEADING_RE = re.compile(r"^(\d+)(?:\.(\d+))?\.?$")
_LIST_ITEM_RE = re.compile(r"^(•|\d+\.\s)")


@dataclass
class Line:
    page: int
    size: float
    bold: bool
    text: str


@dataclass
class PolicyChunk:
    chunk_id: str
    section: str
    title: str
    level: int
    page: int
    text: str
    parent_section: str | None = None
    parent_title: str | None = None

    def to_dict(self) -> dict:
        return self.__dict__.copy()

    @classmethod
    def from_dict(cls, data: dict) -> "PolicyChunk":
        return cls(**data)


@dataclass
class _Section:
    number: str
    title: str
    level: int
    page: int
    lines: list[Line] = field(default_factory=list)


def file_sha256(path: Path | str) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def extract_lines(pdf_path: Path | str) -> list[Line]:
    """Linhas do PDF com tamanho de fonte e negrito, sem cabeçalho e rodapé."""
    lines: list[Line] = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        for number, page in enumerate(pdf.pages, start=1):
            if number in SKIP_PAGES:
                continue
            words = page.extract_words(
                extra_attrs=["fontname", "size"], x_tolerance=1.5, keep_blank_chars=False
            )
            words.sort(key=lambda w: (round(w["top"], 1), w["x0"]))
            current: list[dict] = []
            current_top = None
            groups: list[list[dict]] = []
            for word in words:
                if current_top is None or abs(word["top"] - current_top) > LINE_TOLERANCE:
                    if current:
                        groups.append(current)
                    current, current_top = [], word["top"]
                current.append(word)
            if current:
                groups.append(current)

            for group in groups:
                group.sort(key=lambda w: w["x0"])
                size = max(w["size"] for w in group)
                if size < CHROME_MAX_SIZE:
                    continue
                text = " ".join(w["text"] for w in group).strip()
                if text:
                    lines.append(Line(number, round(size, 1), "Bold" in group[0]["fontname"], text))
    return lines


def _split_sections(lines: list[Line]) -> list[_Section]:
    sections: list[_Section] = []
    for line in lines:
        words = line.text.split(" ", 1)
        match = _HEADING_RE.match(words[0]) if len(words) == 2 else None
        if match and line.size >= HEADING_MIN_SIZE and line.bold:
            major, minor = match.group(1), match.group(2)
            number = f"{major}.{minor}" if minor else major
            sections.append(_Section(number, words[1].strip(), 2 if minor else 1, line.page))
        elif sections:
            sections[-1].lines.append(line)
    return sections


def _body_paragraphs(lines: list[Line]) -> list[str]:
    """Junta linhas quebradas pelo layout; itens de lista e linhas de tabela ficam separados."""
    paragraphs: list[str] = []
    for line in lines:
        starts_item = bool(_LIST_ITEM_RE.match(line.text)) or line.size < 10
        if paragraphs and not starts_item and not paragraphs[-1].endswith((".", ":", ";")):
            paragraphs[-1] += " " + line.text
        else:
            paragraphs.append(line.text)
    return paragraphs


def _pack(paragraphs: list[str], max_chars: int) -> list[str]:
    parts, current = [], ""
    for paragraph in paragraphs:
        candidate = f"{current}\n{paragraph}" if current else paragraph
        if current and len(candidate) > max_chars:
            parts.append(current)
            current = paragraph
        else:
            current = candidate
    if current:
        parts.append(current)
    return parts


def chunk_policy_pdf(pdf_path: Path | str, max_chars: int = MAX_CHUNK_CHARS) -> list[PolicyChunk]:
    """Extrai o PDF e devolve um chunk por seção (seções longas viram vários)."""
    sections = _split_sections(extract_lines(pdf_path))
    parents: dict[str, _Section] = {s.number: s for s in sections if s.level == 1}

    chunks: list[PolicyChunk] = []
    for section in sections:
        paragraphs = _body_paragraphs(section.lines)
        if not paragraphs:
            continue  # título sem texto próprio (ex.: "5." só tem subseções)
        parent = parents.get(section.number.split(".")[0]) if section.level == 2 else None
        header = (
            f"Seção {section.number} {section.title} (dentro de {parent.number}. {parent.title})"
            if parent
            else f"Seção {section.number}. {section.title}"
        )
        parts = _pack(paragraphs, max_chars)
        for index, body in enumerate(parts):
            suffix = "" if len(parts) == 1 else f"-{chr(ord('a') + index)}"
            chunks.append(
                PolicyChunk(
                    chunk_id=f"s{section.number}{suffix}",
                    section=section.number,
                    title=section.title,
                    level=section.level,
                    page=section.page,
                    text=f"{header}\n{body}",
                    parent_section=parent.number if parent else None,
                    parent_title=parent.title if parent else None,
                )
            )
    return chunks
