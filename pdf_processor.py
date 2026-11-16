"""PDF text extraction and chunking helpers."""

import re

import fitz


def extract_pdf_pages(pdf_bytes: bytes) -> list[dict[str, int | str]]:
    """Extract selectable text from a PDF and keep its page numbers."""
    try:
        pdf = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception as error:
        raise ValueError(f"This file is not a readable PDF: {error}") from error

    if pdf.page_count == 0:
        pdf.close()
        raise ValueError("This PDF has no pages.")

    pages = []
    for page_number, page in enumerate(pdf, start=1):
        text = re.sub(r"\s+", " ", page.get_text("text")).strip()
        if text:
            pages.append({"page": page_number, "text": text})
    pdf.close()

    if not pages:
        raise ValueError(
            "No selectable text was found. This may be a scanned PDF; "
            "OCR is not included in this version."
        )

    return pages


def split_text_into_chunks(
    pages: list[dict[str, int | str]],
    chunk_size: int = 1000,
    overlap: int = 150,
) -> list[dict[str, int | str]]:
    """Split each page into overlapping text chunks."""
    if chunk_size <= 0 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk size must be positive and overlap must be smaller.")

    chunks = []
    for page in pages:
        text = str(page["text"])
        start = 0

        while start < len(text):
            end = min(start + chunk_size, len(text))
            if end < len(text):
                last_space = text.rfind(" ", start, end)
                if last_space > start:
                    end = last_space

            chunk_text = text[start:end].strip()
            if chunk_text:
                chunks.append({"page": int(page["page"]), "text": chunk_text})

            if end >= len(text):
                break
            start = max(start + 1, end - overlap)

    return chunks
