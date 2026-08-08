"""Full-text acquisition and section chunking (SPEC §4: HTML-first, never redistributed).

Fetch order per paper: arxiv.org/html/{id} (native, post-2023-12 TeX submissions),
then ar5iv (LaTeXML back-catalog). Papers with no HTML rendering are skipped and
counted — PDF parsing is deliberately out of the v1 path. arXiv politeness applies:
one request every 3+ seconds, single connection.
"""

import time
from dataclasses import dataclass

import httpx
from bs4 import BeautifulSoup

REQUEST_DELAY_S = 3.1
USER_AGENT = "PaperTrace-ingest/0.1 (+https://github.com/mr-j90/PaperTrace)"
CHUNK_CHARS = 2000  # ~512 tokens
CHUNK_OVERLAP = 200
MIN_SECTION_CHARS = 120  # drop boilerplate stubs (acknowledgments one-liners etc.)


@dataclass
class Chunk:
    section: str
    text: str  # embedded text: title — heading + the passage


def fetch_html(client: httpx.Client, arxiv_id: str) -> str | None:
    for url in (
        f"https://arxiv.org/html/{arxiv_id}",
        f"https://ar5iv.labs.arxiv.org/html/{arxiv_id}",
    ):
        time.sleep(REQUEST_DELAY_S)
        try:
            response = client.get(url, follow_redirects=True)
        except httpx.HTTPError:
            continue
        if response.status_code == 200 and "<html" in response.text[:500].lower():
            return response.text
    return None


def parse_sections(html: str) -> list[tuple[str, str]]:
    """(heading, text) per LaTeXML section; whole document as one section if none found."""
    soup = BeautifulSoup(html, "lxml")
    for junk in soup.select("math, .ltx_bibliography, .ltx_appendix, .ltx_listing, figure"):
        junk.decompose()
    sections: list[tuple[str, str]] = []
    for node in soup.select("section.ltx_section"):
        title_node = node.select_one(".ltx_title")
        heading = " ".join(title_node.get_text(" ", strip=True).split()) if title_node else ""
        if title_node is not None:
            title_node.decompose()  # keep subsection text + headings inline in the body
        text = " ".join(node.get_text(" ", strip=True).split())
        if len(text) >= MIN_SECTION_CHARS:
            sections.append((heading or "Section", text))
    if not sections:
        body = soup.body
        text = " ".join(body.get_text(" ", strip=True).split()) if body else ""
        if len(text) >= MIN_SECTION_CHARS:
            sections.append(("Full text", text))
    return sections


def chunk_sections(title: str, sections: list[tuple[str, str]]) -> list[Chunk]:
    """Split each section into ~CHUNK_CHARS pieces with overlap; title + heading prepended."""
    chunks: list[Chunk] = []
    for heading, text in sections:
        start = 0
        while start < len(text):
            piece = text[start : start + CHUNK_CHARS]
            chunks.append(Chunk(section=heading, text=f"{title} — {heading}\n\n{piece}"))
            if start + CHUNK_CHARS >= len(text):
                break
            start += CHUNK_CHARS - CHUNK_OVERLAP
    return chunks
