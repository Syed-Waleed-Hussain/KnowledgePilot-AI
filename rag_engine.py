"""Embedding and vector search helpers for the document assistant."""

import hashlib
import re
from typing import Any

import chromadb
from sentence_transformers import SentenceTransformer


EMBEDDING_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
MINIMUM_SIMILARITY = 0.25


def create_vector_store(session_id: str) -> tuple[Any, Any]:
    """Create an in-memory Chroma collection for one browser session."""
    safe_session_id = re.sub(r"[^a-zA-Z0-9_-]", "", session_id)[:40]
    client = chromadb.Client()
    collection = client.create_collection(
        name=f"knowledgepilot_{safe_session_id}",
        metadata={"hnsw:space": "cosine"},
    )
    return client, collection


def load_embedding_model() -> SentenceTransformer:
    """Load the small Sentence-Transformers model used by this prototype."""
    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def add_document_chunks(
    collection: Any,
    chunks: list[dict[str, int | str]],
    filename: str,
    file_hash: str,
    embedding_model: Any,
    document_id: str | None = None,
    course_id: str | None = None,
) -> None:
    """Embed document chunks and save them with their source details."""
    texts = [str(chunk["text"]) for chunk in chunks]
    encoded_embeddings = embedding_model.encode(
        texts,
        normalize_embeddings=True,
    )
    embeddings = [
        vector.tolist() if hasattr(vector, "tolist") else list(vector)
        for vector in encoded_embeddings
    ]
    id_prefix = document_id or file_hash
    ids = [f"{id_prefix}_{index}" for index in range(len(chunks))]
    metadata = [
        {
            "source": filename,
            "page": int(chunk["page"]),
            "chunk_index": index,
            "file_hash": file_hash,
        }
        for index, chunk in enumerate(chunks)
    ]
    if document_id:
        for item in metadata:
            item["document_id"] = document_id
    if course_id:
        for item in metadata:
            item["course_id"] = course_id

    collection.add(
        ids=ids,
        documents=texts,
        embeddings=embeddings,
        metadatas=metadata,
    )


def search_relevant_chunks(
    collection: Any,
    question: str,
    embedding_model: Any,
    top_k: int = 4,
    minimum_similarity: float = MINIMUM_SIMILARITY,
    where: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """Find the closest document chunks and discard weak matches."""
    if collection.count() == 0:
        return []

    question_embedding = embedding_model.encode(
        [question],
        normalize_embeddings=True,
    )[0]
    question_vector = (
        question_embedding.tolist()
        if hasattr(question_embedding, "tolist")
        else list(question_embedding)
    )
    query_options = {
        "query_embeddings": [question_vector],
        "n_results": min(top_k, collection.count()),
        "include": ["documents", "metadatas", "distances"],
    }
    if where:
        query_options["where"] = where
    result = collection.query(**query_options)

    matches = []
    documents = result["documents"][0]
    metadatas = result["metadatas"][0]
    distances = result["distances"][0]

    for text, metadata, distance in zip(documents, metadatas, distances):
        similarity = 1 - float(distance)
        if similarity >= minimum_similarity:
            matches.append(
                {
                    "text": text,
                    "source": metadata["source"],
                    "page": int(metadata["page"]),
                    "similarity": similarity,
                }
            )

    return matches


def get_file_hash(file_bytes: bytes) -> str:
    """Return a stable ID used to skip duplicate uploads."""
    return hashlib.sha256(file_bytes).hexdigest()
