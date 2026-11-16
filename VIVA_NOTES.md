# KnowledgePilot AI — Viva Notes

## What is RAG?

RAG means Retrieval-Augmented Generation. The app first searches the student's
documents for useful passages. It then gives those passages to a language
model to help answer the question.

## What are embeddings?

An embedding is a list of numbers that represents the meaning of text. Similar
pieces of text have similar lists of numbers, even when they use different
words.

## What is chunking?

Chunking divides a long document into smaller pieces. Smaller pieces are easier
to search and give the language model focused evidence. This app keeps a page
number on every piece and uses a small overlap so nearby text is not lost at a
chunk boundary.

## What is a vector database?

A vector database stores embeddings and searches for vectors close to a
question's vector. The matching text and its source details are stored with
each vector.

## Why did we choose ChromaDB?

ChromaDB is a Python vector database that is straightforward to use locally.
It stores the passage text, its embedding, and its PDF source details together.
This prototype uses an in-memory collection for each browser session.

## What is semantic search?

Semantic search compares meaning rather than only matching exact words. For
example, a question about how plants make food can find a passage that mentions
photosynthesis.

## RAG versus model training

RAG looks up information when a question is asked and provides it as context.
Model training changes the model's learned parameters using training data.
This app does not train or fine-tune its language model.

## How does a PDF become an answer?

1. The student uploads a text-based PDF.
2. PyMuPDF extracts text and the page number from each page.
3. The app splits each page into small, overlapping chunks.
4. Sentence-Transformers converts chunks into embeddings.
5. ChromaDB stores the embeddings with the filename and page.
6. The app converts a question into an embedding and searches for close chunks.
7. If a Groq API key is configured, the app sends the question and retrieved
   evidence to the language model.
8. The app shows the answer, source passages, filenames, and page numbers.

If there is no API key, step 7 is skipped and retrieved passages can still be
inspected.

## Purpose of each Python file

- `app.py`: Streamlit page, upload flow, session state, and chat history.
- `pdf_processor.py`: PDF text extraction and chunking.
- `rag_engine.py`: embedding model, ChromaDB storage, and semantic retrieval.
- `llm_service.py`: optional Groq answer generation.
- `tests/test_basic.py`: small automated tests for PDF processing and search.

## Important functions

- `extract_pdf_pages`: reads selectable text and page numbers from a PDF.
- `split_text_into_chunks`: creates smaller overlapping pieces.
- `add_document_chunks`: embeds and stores document passages.
- `search_relevant_chunks`: finds relevant passages for a question.
- `generate_answer`: asks the hosted model to answer from retrieved evidence.

## Current limitations

- The app is a local prototype, not a deployed website.
- There are no student accounts or multi-user security controls.
- Documents and vectors exist only in the current browser session.
- Scanned PDFs need OCR, which is not included.
- Generated answers need a working Groq API key and internet access.
- The model is instructed to use the retrieved evidence, but an LLM can still
  make mistakes. Check the displayed passages and page references.
- LangGraph, MCP, agent harness features, research search, and reinforcement
  learning are future work, not Phase 1 features.
