"""Small tests for PDF processing and vector retrieval."""

import fitz
import pytest

from pdf_processor import extract_pdf_pages, split_text_into_chunks
from rag_engine import (
    add_document_chunks,
    create_vector_store,
    get_file_hash,
    search_relevant_chunks,
)


class FakeEmbeddingModel:
    """A tiny predictable embedding model used only by the tests."""

    def encode(self, texts, normalize_embeddings=True):
        vectors = []
        for text in texts:
            value = text.lower()
            if "photosynthesis" in value or "plants" in value:
                vectors.append([1.0, 0.0])
            else:
                vectors.append([0.0, 1.0])
        return vectors


def make_pdf(text: str) -> bytes:
    """Create a one-page PDF in memory for the PDF tests."""
    pdf = fitz.open()
    page = pdf.new_page()
    page.insert_text((72, 72), text)
    return pdf.tobytes()


def test_extract_pdf_text_and_page_number():
    pages = extract_pdf_pages(make_pdf("Plants use sunlight for photosynthesis."))

    assert pages == [
        {"page": 1, "text": "Plants use sunlight for photosynthesis."}
    ]


def test_empty_or_scanned_pdf_has_helpful_error():
    with pytest.raises(ValueError, match="No selectable text"):
        extract_pdf_pages(make_pdf(""))


def test_chunking_keeps_page_references_and_overlap():
    pages = [{"page": 3, "text": "one two three four five six seven eight"}]

    chunks = split_text_into_chunks(pages, chunk_size=18, overlap=5)

    assert len(chunks) > 1
    assert all(chunk["page"] == 3 for chunk in chunks)
    assert chunks[0]["text"].split()[-1] in chunks[1]["text"].split()


def test_vector_search_returns_relevant_source_and_page():
    _, collection = create_vector_store("testsession")
    model = FakeEmbeddingModel()
    chunks = [
        {"page": 2, "text": "Plants use sunlight for photosynthesis."},
        {"page": 5, "text": "A cell stores genetic information."},
    ]
    add_document_chunks(
        collection,
        chunks,
        "biology.pdf",
        get_file_hash(b"biology pdf"),
        model,
    )

    results = search_relevant_chunks(
        collection,
        "How do plants make food?",
        model,
    )

    assert len(results) == 1
    assert results[0]["source"] == "biology.pdf"
    assert results[0]["page"] == 2
    assert "photosynthesis" in results[0]["text"]


def test_corrupt_pdf_has_helpful_error():
    with pytest.raises(ValueError, match="not a readable PDF"):
        extract_pdf_pages(b"not a PDF")
