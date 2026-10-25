import httpx
from fastapi import HTTPException
from app.config import settings
from app.util import vector_literal


def embed(text: str) -> list[float]:
    cfg = settings()
    try:
        response = httpx.post(
            f"{cfg.ollama_url.rstrip('/')}/api/embed",
            json={"model": cfg.embedding_model, "input": text},
            timeout=90.0,
        )
        response.raise_for_status()
        value = response.json()["embeddings"][0]
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Embedding service unavailable: {exc}") from exc

    if len(value) != cfg.embedding_dimensions:
        raise HTTPException(
            status_code=500,
            detail=f"Embedding dimension mismatch: got {len(value)}, expected {cfg.embedding_dimensions}",
        )
    return value


def embed_literal(text: str) -> str:
    return vector_literal(embed(text))
