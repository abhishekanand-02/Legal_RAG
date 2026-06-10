import base64
import io
import logging
import re

from langchain_core.messages import HumanMessage
from pypdf import PdfReader

import config
from rag.llm import get_llm

logger = logging.getLogger("legal_rag.pdf")

PAGE_MARKER = re.compile(r"---\s*PAGE\s+(\d+)\s*---", re.IGNORECASE)

OCR_PROMPT = """Extract all readable text from this PDF.

Rules:
- Preserve the original reading order.
- Mark each page with exactly: --- PAGE N --- (N starts at 1).
- Include all visible text, labels, numbers, and dates.
- Return only extracted text, no commentary."""


def _content_to_str(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict) and "text" in item:
                parts.append(str(item["text"]))
            else:
                parts.append(str(item))
        return "\n".join(parts)
    return str(content)


def _extract_with_pypdf(pdf_bytes: bytes) -> list[tuple[int, str]]:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    pages: list[tuple[int, str]] = []

    for page_number, page in enumerate(reader.pages, start=1):
        text = (page.extract_text() or "").strip()
        if text:
            pages.append((page_number, text))

    return pages


def _parse_ocr_pages(text: str) -> list[tuple[int, str]]:
    matches = list(PAGE_MARKER.finditer(text))
    if not matches:
        cleaned = text.strip()
        return [(1, cleaned)] if cleaned else []

    pages: list[tuple[int, str]] = []
    for index, match in enumerate(matches):
        page_number = int(match.group(1))
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[start:end].strip()
        if content:
            pages.append((page_number, content))

    return pages


def _extract_with_gemini_ocr(pdf_bytes: bytes) -> list[tuple[int, str]]:
    llm = get_llm()
    response = llm.invoke(
        [
            HumanMessage(
                content=[
                    {
                        "type": "media",
                        "mime_type": "application/pdf",
                        "data": base64.b64encode(pdf_bytes).decode("ascii"),
                    },
                    {"type": "text", "text": OCR_PROMPT},
                ]
            )
        ]
    )
    return _parse_ocr_pages(_content_to_str(response.content))


def extract_pdf_pages(pdf_bytes: bytes) -> list[tuple[int, str]]:
    """Extract text per page, using Gemini OCR when the PDF has no embedded text."""
    pages = _extract_with_pypdf(pdf_bytes)
    if pages:
        return pages

    if not config.OCR_ENABLED:
        return []

    logger.info(
        "No embedded PDF text found (%d bytes); using Gemini OCR fallback",
        len(pdf_bytes),
    )
    try:
        return _extract_with_gemini_ocr(pdf_bytes)
    except Exception:
        logger.exception("Gemini OCR fallback failed")
        return []


def extract_text_sample(pdf_bytes: bytes) -> str:
    """Read the first few pages of a PDF and return a text sample for validation."""
    pages = extract_pdf_pages(pdf_bytes)
    if not pages:
        return ""

    parts = [text for _, text in pages[: config.VALIDATION_MAX_PAGES]]
    sample = "\n\n".join(parts)
    return sample[: config.VALIDATION_MAX_CHARS]
