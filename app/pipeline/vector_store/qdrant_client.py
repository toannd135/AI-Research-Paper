"""Abstraction Qdrant: insert/delete/update vectors."""

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels

from app.core.config import get_settings
from app.core.schemas import Chunk

_client: QdrantClient | None = None


def get_client() -> QdrantClient:
    global _client
    if _client is None:
        _client = QdrantClient(url=get_settings().qdrant_url)
    return _client


def ensure_collection(vector_size: int, collection: str | None = None) -> None:
    client = get_client()
    name = collection or get_settings().qdrant_collection
    if not client.collection_exists(name):
        client.create_collection(
            collection_name=name,
            vectors_config=qmodels.VectorParams(size=vector_size, distance=qmodels.Distance.COSINE),
        )


def upsert_chunks(chunks: list[Chunk], vectors: list[list[float]], collection: str | None = None) -> None:
    if len(chunks) != len(vectors):
        raise ValueError("chunks và vectors phải cùng độ dài")
    client = get_client()
    name = collection or get_settings().qdrant_collection
    points = [
        qmodels.PointStruct(
            id=chunk.id,
            vector=vector,
            payload={
                "paper_id": chunk.paper_id,
                "text": chunk.text,
                "chunk_index": chunk.chunk_index,
                "page": chunk.page,
                "section": chunk.section,
            },
        )
        for chunk, vector in zip(chunks, vectors, strict=True)
    ]
    client.upsert(collection_name=name, points=points)


def delete_paper(paper_id: str, collection: str | None = None) -> None:
    client = get_client()
    name = collection or get_settings().qdrant_collection
    client.delete(
        collection_name=name,
        points_selector=qmodels.FilterSelector(
            filter=qmodels.Filter(
                must=[qmodels.FieldCondition(key="paper_id", match=qmodels.MatchValue(value=paper_id))]
            )
        ),
    )


def search(
    query_vector: list[float],
    top_k: int = 10,
    paper_id: str | None = None,
    collection: str | None = None,
) -> list[qmodels.ScoredPoint]:
    client = get_client()
    name = collection or get_settings().qdrant_collection
    query_filter = None
    if paper_id:
        query_filter = qmodels.Filter(
            must=[qmodels.FieldCondition(key="paper_id", match=qmodels.MatchValue(value=paper_id))]
        )
    result = client.query_points(
        collection_name=name,
        query=query_vector,
        limit=top_k,
        query_filter=query_filter,
    )
    return result.points
