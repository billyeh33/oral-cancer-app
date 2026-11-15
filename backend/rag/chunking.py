"""Turn the source documents into chunks (used only by build_index.py).

Each source is listed in SOURCES. The handbook PDF is split page by page: in its
disease chapter each page describes one condition, so a page is a natural unit
and keeps citations exact. The flowchart PDF is replaced by a hand-transcribed
Markdown file because extracting its text scrambles the boxes and arrows.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from . import config

SOURCES: List[Dict] = [
    {
        "id": "handbook",
        "kind": "pdf",
        "file": "口腔黏膜異常患者之口腔保健指導手冊(民眾版).pdf",
        "title": "口腔黏膜異常患者之口腔保健指導手冊（民眾版）",
        "publisher": "衛生福利部（委託社團法人中華民國牙醫師公會全國聯合會）",
        # Cover, table of contents and colophon.
        "skip_pages": [1, 5, 6, 77],
    },
    {
        "id": "flowchart",
        "kind": "markdown",
        "file": "處置流程_整理.md",
        "original_file": "口腔黏膜檢查陽性個案後續確診及治療處置流程.pdf",
        "title": "口腔黏膜檢查陽性個案後續確診及治療處置流程",
        "publisher": "衛生福利部國民健康署",
        "page": 1,
    },
]

MAX_CHARS = 650
TARGET_CHARS = 450
MIN_CHARS = 40

# The handbook's running header, printed as repeated words on every other page.
_HEADER_LINE = re.compile(r"^(口腔黏膜|異常患者|之口腔保健指導手冊|民眾版|\s)+$")
_RUNNING_HEADERS = {
    "一、口腔黏膜介紹",
    "二、常見病變簡介",
    "三、Q&A 及",
    "三、Q&A 及 常見迷思",
    "常見迷思",
    "四、口腔保健綜合",
    "四、口腔保健綜合 建議事項",
    "建議事項",
    "五、衛教資訊",
    "附錄",
}
_CHAPTER_PAGE = re.compile(r"^第([一二三四五六七八九十]+)章\s*(.+)$")
_SUBSECTION = re.compile(r"^\(\s*([一二三四五六七八九十]+)\s*\)\s*(.+)$")
_ENTRY = re.compile(r"^(\d{1,2})\.\s*(\S.+)$")
_CJK_OR_PUNCT = re.compile(r"[㐀-鿿豈-﫿　-〿＀-￯]")
_SENTENCE_END = re.compile(r"(?<=[。！？；])")


@dataclass
class Chunk:
    chunk_id: str
    source_id: str
    source_title: str
    publisher: str
    file: str
    page: int
    chapter: str
    section: str
    title: str
    text: str
    extra: Dict = field(default_factory=dict)

    def embed_text(self) -> str:
        """Text sent to the embedding model: a short context header plus the chunk.

        The header (document / chapter / topic) lets a chunk such as "不會痛，擦不掉"
        still match questions that name the condition it describes.
        """
        context = "｜".join(part for part in (self.source_title, self.chapter, self.section, self.title) if part)
        return f"{context}\n{self.text}"

    def text_hash(self) -> str:
        return hashlib.sha1(self.embed_text().encode("utf-8")).hexdigest()

    def to_json(self) -> Dict:
        return asdict(self)


def _join_lines(lines: List[str]) -> str:
    text = ""
    for line in lines:
        if not text:
            text = line
        elif _CJK_OR_PUNCT.match(text[-1]) and _CJK_OR_PUNCT.match(line[0]):
            text += line
        else:
            text += " " + line
    return re.sub(r"\s{2,}", " ", text).strip()


def _clean_page_lines(raw: str) -> List[str]:
    lines = []
    for index, line in enumerate(raw.splitlines()):
        line = re.sub(r"\s+", " ", line).strip()
        if not line or _HEADER_LINE.match(line) or line.isdigit():
            continue
        if index < 8 and line in _RUNNING_HEADERS:
            continue
        # Figure captions and photo credits describe pictures we do not index.
        if line.startswith("•") or re.match(r"^\(\s*照片提供", line):
            continue
        if line.lower() == "note":
            continue
        # The Q&A pages print the "迷思N" label to the right of the question;
        # move it to the front so the text reads "迷思1：口腔黏膜破皮……".
        myth = re.match(r"^(.*?)\s*(迷思\d+)$", line)
        if myth and myth.group(1):
            line = f"{myth.group(2)}：{myth.group(1)}"
        lines.append(line)
    return lines


def _split_long(text: str) -> List[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    sentences = [s for s in _SENTENCE_END.split(text) if s.strip()]
    pieces: List[str] = []
    current: List[str] = []
    for sentence in sentences:
        if current and len("".join(current)) + len(sentence) > TARGET_CHARS:
            pieces.append("".join(current))
            # One sentence of overlap keeps context across the cut.
            current = [current[-1]]
        current.append(sentence)
    if current:
        pieces.append("".join(current))
    return pieces


def _pdf_chunks(source: Dict, path: Path) -> Iterator[Chunk]:
    import pymupdf

    chapter = section = ""
    with pymupdf.open(path) as document:
        for page_number, page in enumerate(document, start=1):
            # sort=True follows the visual reading order; the Q&A pages are
            # otherwise extracted with the questions and their labels out of step.
            raw = page.get_text(sort=True)
            # The appendix divider page holds only the word 附錄, which the
            # running-header filter would otherwise remove.
            if re.sub(r"\s", "", raw) == "附錄":
                chapter, section = "附錄", ""
                continue
            lines = _clean_page_lines(raw)
            if not lines:
                continue
            chapter_match = _CHAPTER_PAGE.match(" ".join(lines))
            if chapter_match:
                chapter, section = chapter_match.group(2).strip(), ""
                continue
            if page_number in source.get("skip_pages", []):
                continue

            title = ""
            for line in lines[:6]:
                subsection = _SUBSECTION.match(line)
                if subsection:
                    section = subsection.group(2).strip()
                    continue
                entry = _ENTRY.match(line)
                if entry and not title and chapter == "常見病變簡介":
                    title = entry.group(2).strip()
            text = _join_lines(lines)
            if len(text) < MIN_CHARS:
                continue
            for part_number, part in enumerate(_split_long(text), start=1):
                yield Chunk(
                    chunk_id=f"{source['id']}-p{page_number:02d}-{part_number}",
                    source_id=source["id"],
                    source_title=source["title"],
                    publisher=source["publisher"],
                    file=source["file"],
                    page=page_number,
                    chapter=chapter,
                    section=section if chapter == "常見病變簡介" else "",
                    title=title,
                    text=part,
                )


def _markdown_chunks(source: Dict, path: Path) -> Iterator[Chunk]:
    content = re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.S)
    for number, block in enumerate(re.split(r"^## ", content, flags=re.M)[1:], start=1):
        heading, _, body = block.partition("\n")
        text = re.sub(r"\s*\n\s*", "", body.strip())
        if len(text) < MIN_CHARS:
            continue
        yield Chunk(
            chunk_id=f"{source['id']}-{number}",
            source_id=source["id"],
            source_title=source["title"],
            publisher=source["publisher"],
            file=source.get("original_file", source["file"]),
            page=source.get("page", 1),
            chapter="",
            section="",
            title=heading.strip(),
            text=text,
        )


def build_chunks(sources_dir: Optional[Path] = None) -> List[Chunk]:
    sources_dir = sources_dir or config.SOURCES_DIR
    chunks: List[Chunk] = []
    for source in SOURCES:
        path = sources_dir / source["file"]
        if not path.exists():
            raise FileNotFoundError(f"Source file missing: {path}")
        reader = _pdf_chunks if source["kind"] == "pdf" else _markdown_chunks
        chunks.extend(reader(source, path))
    ids = [chunk.chunk_id for chunk in chunks]
    if len(ids) != len(set(ids)):
        raise ValueError("Duplicate chunk ids; check the chunking rules.")
    return chunks
