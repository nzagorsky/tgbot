from typing import Any


EMBEDDING_DIMENSIONS = 1536


def message_mapping() -> dict[str, Any]:
    return {
        "dynamic": "strict",
        "properties": {
            "schema_version": {"type": "integer"},
            "chat_id": {"type": "long"},
            "chat_type": {"type": "keyword"},
            "chat_title": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "user_id": {"type": "long"},
            "username": {"type": "keyword"},
            "first_name": {"type": "text", "fields": {"keyword": {"type": "keyword"}}},
            "message_id": {"type": "long"},
            "reply_to_message_id": {"type": "long"},
            "timestamp": {"type": "date"},
            "text": {"type": "text"},
            "embedding_model": {"type": "keyword"},
            "text_embedding": {
                "type": "knn_vector",
                "dimension": EMBEDDING_DIMENSIONS,
                "method": {
                    "name": "hnsw",
                    "space_type": "cosinesimil",
                    "engine": "lucene",
                },
            },
        },
    }
