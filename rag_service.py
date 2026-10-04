"""Semantic RAG pipeline for MaintainIQ knowledge documents."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any

import chromadb
from dotenv import load_dotenv
from langchain_text_splitters import RecursiveCharacterTextSplitter
from sentence_transformers import SentenceTransformer


load_dotenv()


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parent

DOCUMENTS_DIR = BASE_DIR / os.getenv(
    "RAG_DOCUMENTS_DIR",
    "data/manuals",
)

CHROMA_DIR = BASE_DIR / os.getenv(
    "RAG_CHROMA_DIR",
    "data/chroma",
)

MANIFEST_PATH = BASE_DIR / os.getenv(
    "RAG_MANIFEST_PATH",
    "data/rag_manifest.json",
)

EMBEDDING_MODEL_NAME = os.getenv(
    "RAG_EMBEDDING_MODEL",
    "sentence-transformers/all-MiniLM-L6-v2",
)

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "900"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "150"))

TOP_K = int(os.getenv("RAG_TOP_K", "5"))
MIN_RELEVANCE = float(os.getenv("RAG_MIN_RELEVANCE", "0.20"))


SUPPORTED_EXTENSIONS = {".pdf", ".txt", ".md"}

COLLECTION_NAME = "maintainiq_knowledge"


# ---------------------------------------------------------------------------
# Initialization
# ---------------------------------------------------------------------------

def _ensure_directories() -> None:
    """Create RAG directories if they don't exist."""

    DOCUMENTS_DIR.mkdir(parents=True, exist_ok=True)
    CHROMA_DIR.mkdir(parents=True, exist_ok=True)

    MANIFEST_PATH.parent.mkdir(parents=True, exist_ok=True)


def _get_embedding_model() -> SentenceTransformer:
    """Load the configured sentence-transformer embedding model."""

    return SentenceTransformer(EMBEDDING_MODEL_NAME)


def _get_collection():
    """Return the persistent ChromaDB collection."""

    _ensure_directories()

    client = chromadb.PersistentClient(
        path=str(CHROMA_DIR)
    )

    return client.get_or_create_collection(
        name=COLLECTION_NAME,
        metadata={
            "description": "MaintainIQ maintenance knowledge base",
            "hnsw:space": "cosine",
        },
    )


# ---------------------------------------------------------------------------
# Document extraction
# ---------------------------------------------------------------------------

def extract_text(file_path: Path) -> str:
    """Extract text from PDF, TXT, or Markdown."""

    suffix = file_path.suffix.lower()

    if suffix == ".pdf":
        import pymupdf

        with pymupdf.open(file_path) as pdf:
            pages = [
                page.get_text("text")
                for page in pdf
            ]

        return "\n\n".join(pages).strip()

    if suffix in {".txt", ".md"}:
        return file_path.read_text(
            encoding="utf-8",
            errors="replace",
        ).strip()

    raise ValueError(
        f"Unsupported document type: {file_path.suffix}"
    )


# ---------------------------------------------------------------------------
# Chunking
# ---------------------------------------------------------------------------

def _create_splitter() -> RecursiveCharacterTextSplitter:
    """Create the configured recursive text splitter."""

    return RecursiveCharacterTextSplitter(
        chunk_size=CHUNK_SIZE,
        chunk_overlap=CHUNK_OVERLAP,
        separators=[
            "\n\n",
            "\n",
            ". ",
            "! ",
            "? ",
            "; ",
            ", ",
            " ",
            "",
        ],
        length_function=len,
    )


def chunk_document(
    text: str,
) -> list[str]:
    """Split document text into overlapping semantic chunks."""

    if not text.strip():
        return []

    splitter = _create_splitter()

    return [
        chunk.strip()
        for chunk in splitter.split_text(text)
        if chunk.strip()
    ]


# ---------------------------------------------------------------------------
# Document identity
# ---------------------------------------------------------------------------

def calculate_file_hash(
    file_path: Path,
) -> str:
    """Calculate SHA-256 hash for a document."""

    sha256 = hashlib.sha256()

    with file_path.open("rb") as file:
        for block in iter(
            lambda: file.read(1024 * 1024),
            b"",
        ):
            sha256.update(block)

    return sha256.hexdigest()


# ---------------------------------------------------------------------------
# Manifest
# ---------------------------------------------------------------------------

def _load_manifest() -> dict[str, Any]:
    """Load the indexing manifest."""

    if not MANIFEST_PATH.exists():
        return {}

    try:
        data = json.loads(
            MANIFEST_PATH.read_text(
                encoding="utf-8"
            )
        )

        return data if isinstance(data, dict) else {}

    except (OSError, json.JSONDecodeError):
        return {}


def _save_manifest(
    manifest: dict[str, Any],
) -> None:
    """Persist the indexing manifest."""

    MANIFEST_PATH.write_text(
        json.dumps(
            manifest,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


# ---------------------------------------------------------------------------
# Indexing
# ---------------------------------------------------------------------------

def index_document(
    file_path: Path,
    force: bool = False,
) -> dict[str, Any]:
    """
    Extract, chunk, embed and store one document in ChromaDB.

    Returns information about the indexing operation.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Document not found: {file_path}"
        )

    if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported document type: {file_path.suffix}"
        )

    file_hash = calculate_file_hash(file_path)
    text = extract_text(file_path)

    return _index_text(
        file_path.name,
        text,
        file_hash,
        force,
    )


def index_text_document(
    filename: str,
    text: str,
    force: bool = False,
) -> dict[str, Any]:
    """Index extracted text from a document previously stored in SQLite."""

    if Path(filename).name != filename:
        raise ValueError("Document filename must not contain a directory.")

    if Path(filename).suffix.lower() not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported document type: {Path(filename).suffix}"
        )

    file_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return _index_text(filename, text, file_hash, force)


def _index_text(
    filename: str,
    text: str,
    file_hash: str,
    force: bool,
) -> dict[str, Any]:
    _ensure_directories()
    manifest = _load_manifest()
    existing = manifest.get(filename)
    if (
        existing
        and existing.get("hash") == file_hash
        and not force
    ):
        return {
            "filename": filename,
            "status": "already_indexed",
            "chunks": existing.get("chunks", 0),
        }

    if not text:
        _get_collection().delete(where={"filename": filename})
        manifest.pop(filename, None)
        _save_manifest(manifest)
        return {
            "filename": filename,
            "status": "empty",
            "chunks": 0,
        }

    chunks = chunk_document(text)

    if not chunks:
        _get_collection().delete(where={"filename": filename})
        manifest.pop(filename, None)
        _save_manifest(manifest)
        return {
            "filename": filename,
            "status": "empty",
            "chunks": 0,
        }

    collection = _get_collection()
    model = _get_embedding_model()

    # Remove previous version of this document.
    collection.delete(
        where={
            "document_hash": file_hash,
        }
    )

    # Also remove by filename in case the file contents changed.
    collection.delete(
        where={
            "filename": filename,
        }
    )

    embeddings = model.encode(
        chunks,
        normalize_embeddings=True,
        show_progress_bar=False,
    )

    ids = [
        f"{file_hash}:{index}"
        for index in range(len(chunks))
    ]

    metadatas = [
        {
            "filename": filename,
            "document_hash": file_hash,
            "chunk_index": index,
            "total_chunks": len(chunks),
        }
        for index in range(len(chunks))
    ]

    collection.add(
        ids=ids,
        embeddings=embeddings.tolist(),
        documents=chunks,
        metadatas=metadatas,
    )

    manifest[filename] = {
        "hash": file_hash,
        "chunks": len(chunks),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
    }

    _save_manifest(manifest)

    return {
        "filename": filename,
        "status": "indexed",
        "chunks": len(chunks),
    }


def list_indexed_documents() -> list[dict[str, Any]]:
    """Return documents recorded in the RAG indexing manifest."""

    manifest = _load_manifest()
    return [
        {
            "filename": filename,
            "chunks": details.get("chunks", 0),
        }
        for filename, details in sorted(manifest.items())
    ]


def index_all_documents(
    force: bool = False,
) -> list[dict[str, Any]]:
    """Index every supported document inside the manuals directory."""

    _ensure_directories()

    results = []

    for file_path in sorted(DOCUMENTS_DIR.iterdir()):

        if not file_path.is_file():
            continue

        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            continue

        try:
            results.append(
                index_document(
                    file_path,
                    force=force,
                )
            )

        except Exception as exc:
            results.append(
                {
                    "filename": file_path.name,
                    "status": "error",
                    "error": str(exc),
                }
            )

    return results


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

def retrieve(
    question: str,
    top_k: int | None = None,
    min_relevance: float | None = None,
) -> list[dict[str, Any]]:
    """
    Retrieve semantically relevant chunks from ChromaDB.

    Chroma cosine distance is converted into a relevance score:

        relevance = 1 - cosine_distance

    Higher score = more relevant.
    """

    question = question.strip()

    if not question:
        return []

    top_k = top_k or TOP_K
    min_relevance = (
        MIN_RELEVANCE
        if min_relevance is None
        else min_relevance
    )

    collection = _get_collection()

    if collection.count() == 0:
        return []

    model = _get_embedding_model()

    query_embedding = model.encode(
        [question],
        normalize_embeddings=True,
        show_progress_bar=False,
    )[0]

    results = collection.query(
        query_embeddings=[
            query_embedding.tolist()
        ],
        n_results=top_k,
        include=[
            "documents",
            "metadatas",
            "distances",
        ],
    )

    documents = results.get("documents", [[]])[0]
    metadatas = results.get("metadatas", [[]])[0]
    distances = results.get("distances", [[]])[0]

    retrieved = []

    for document, metadata, distance in zip(
        documents,
        metadatas,
        distances,
    ):
        relevance = max(
            0.0,
            min(1.0, 1.0 - float(distance)),
        )

        if relevance < min_relevance:
            continue

        retrieved.append(
            {
                "content": document,
                "filename": metadata.get(
                    "filename",
                    "Unknown source",
                ),
                "chunk_index": metadata.get(
                    "chunk_index"
                ),
                "score": round(
                    relevance,
                    4,
                ),
                "distance": round(
                    float(distance),
                    4,
                ),
            }
        )

    return retrieved


# ---------------------------------------------------------------------------
# RAG context
# ---------------------------------------------------------------------------

def build_context(
    passages: list[dict[str, Any]],
) -> str:
    """Convert retrieved chunks into LLM context."""

    if not passages:
        return ""

    blocks = []

    for index, passage in enumerate(passages, start=1):
        blocks.append(
            f"""[SOURCE {index}]
Filename: {passage["filename"]}
Chunk: {passage["chunk_index"]}
Relevance: {passage["score"]}

{passage["content"]}"""
        )

    return "\n\n---\n\n".join(blocks)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def rag_status() -> dict[str, Any]:
    """Return basic RAG database information."""

    collection = _get_collection()

    return {
        "collection": COLLECTION_NAME,
        "documents": collection.count(),
        "embedding_model": EMBEDDING_MODEL_NAME,
        "chunk_size": CHUNK_SIZE,
        "chunk_overlap": CHUNK_OVERLAP,
        "top_k": TOP_K,
        "min_relevance": MIN_RELEVANCE,
        "chroma_dir": str(CHROMA_DIR),
    }