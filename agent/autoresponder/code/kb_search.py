"""
kb_search.py — Supabase vector store search for the 'documents 2' table.

Replicates:
  - AI Agent 1 (knowledge base search using 'documents' tool)
  - Supabase Vector Store1 / Supabase Vector Store2 nodes
  - Embeddings OpenAI nodes (replaced with OpenRouter embeddings)

The Supabase 'documents 2' table has columns:
  id, content, metadata (jsonb with Answer, Category, Content, blobType), embedding (vector)

We call the match_documents RPC function directly via the Supabase REST API.
"""
import os
import json
import logging
import httpx
from typing import List, Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

SUPABASE_URL = "https://umbxdmxpjbgabrhquafe.supabase.co"
TABLE_NAME = "documents 2"
MATCH_FUNCTION = "match_documents"


def _get_supabase_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY not set in environment")
    return key


def _generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate a text embedding via OpenRouter.
    Uses text-embedding-3-small (1536 dims) — compatible with the Supabase table.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("❌ OPENROUTER_API_KEY not set")
        return None

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    try:
        response = client.embeddings.create(
            model="openai/text-embedding-3-small",
            input=text,
        )
        embedding = response.data[0].embedding
        logger.info(f"✅ Embedding generated ({len(embedding)} dims) for: {text[:60]}")
        return embedding
    except Exception as e:
        logger.error(f"❌ Embedding generation failed: {e}", exc_info=True)
        return None


def search_knowledge_base(
    query: str,
    top_k: int = 10,
    similarity_threshold: float = 0.5,
) -> Dict:
    """
    Search the Supabase 'documents 2' vector store for content matching the query.

    Returns dict:
    {
        "data_found": bool,
        "matched_rows": [{"content": str, "answer": str, "category": str, "similarity": float}],
        "query_used": str,
        "match_count": int,
    }
    """
    embedding = _generate_embedding(query)
    if embedding is None:
        return {
            "data_found": False,
            "matched_rows": [],
            "query_used": query,
            "match_count": 0,
        }

    supabase_key = _get_supabase_key()
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    # Call the match_documents RPC function
    payload = {
        "query_embedding": embedding,
        "match_threshold": similarity_threshold,
        "match_count": top_k,
    }

    rpc_url = f"{SUPABASE_URL}/rest/v1/rpc/{MATCH_FUNCTION}"

    try:
        response = httpx.post(rpc_url, headers=headers, json=payload, timeout=30.0)
        response.raise_for_status()
        rows = response.json()

        if not rows:
            logger.info("📭 No KB matches found")
            return {
                "data_found": False,
                "matched_rows": [],
                "query_used": query,
                "match_count": 0,
            }

        matched_rows = []
        for row in rows:
            # Parse metadata JSON if it's a string
            meta = row.get("metadata", {})
            if isinstance(meta, str):
                try:
                    meta = json.loads(meta)
                except Exception:
                    meta = {}

            answer = meta.get("Answer", "")
            category = meta.get("Category", "")
            content_text = meta.get("Content", row.get("content", ""))
            similarity = row.get("similarity", 0.0)

            if answer:
                matched_rows.append(
                    {
                        "content": content_text,
                        "answer": answer,
                        "category": category,
                        "similarity": round(float(similarity), 4),
                    }
                )

        logger.info(f"✅ KB search: {len(matched_rows)} match(es) found")
        return {
            "data_found": len(matched_rows) > 0,
            "matched_rows": matched_rows,
            "query_used": query,
            "match_count": len(matched_rows),
        }

    except httpx.HTTPStatusError as e:
        logger.error(f"❌ Supabase RPC HTTP error {e.response.status_code}: {e.response.text}")
    except Exception as e:
        logger.error(f"❌ Supabase KB search failed: {e}", exc_info=True)

    return {
        "data_found": False,
        "matched_rows": [],
        "query_used": query,
        "match_count": 0,
    }
