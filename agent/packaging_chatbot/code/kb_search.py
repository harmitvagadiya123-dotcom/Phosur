"""
kb_search.py — Supabase knowledge base search with smart context matching.

Replicates the following n8n nodes:
  - "Generate Embedding" (OpenAI embeddings via OpenRouter)
  - "Get Knowledge Base1" (Supabase fetch from 'packaging' table)
  - "Smart Context Matching1" (cosine similarity + keyword overlap + fuzzy matching)

Supabase table 'packaging' has columns:
  id, Questions, Answers, embedding
"""

import os
import re
import math
import json
import logging
from typing import List, Dict, Optional, Tuple

import httpx
from openai import OpenAI

logger = logging.getLogger(__name__)

SUPABASE_URL = "https://umbxdmxpjbgabrhquafe.supabase.co"
TABLE_NAME = "packaging"


# ============================================
# CONFIGURATION (matches n8n Smart Context Matching1)
# ============================================
CONFIG = {
    "EXACT_MATCH_THRESHOLD": 0.95,
    "HIGH_FUZZY_THRESHOLD": 0.80,
    "MEDIUM_FUZZY_THRESHOLD": 0.65,
    "SEMANTIC_BASE_THRESHOLD": 0.50,
    "SEMANTIC_WEIGHT": 0.50,
    "KEYWORD_WEIGHT": 0.30,
    "FUZZY_WEIGHT": 0.20,
    "MIN_KEYWORD_OVERLAP": 0.4,
    "RETURNING_USER_THRESHOLD_REDUCTION": 0.05,
    "FOLLOW_UP_BOOST": 0.10,
}


def _get_supabase_key() -> str:
    key = os.environ.get("SUPABASE_SERVICE_KEY", "")
    if not key:
        raise ValueError("SUPABASE_SERVICE_KEY not set in environment")
    return key


def generate_embedding(text: str) -> Optional[List[float]]:
    """
    Generate a text embedding via OpenRouter using text-embedding-3-small.
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


def fetch_all_kb_entries() -> List[Dict]:
    """
    Fetch all rows from the Supabase 'packaging' table.
    Equivalent to the "Get Knowledge Base1" Supabase node.
    """
    supabase_key = _get_supabase_key()
    headers = {
        "apikey": supabase_key,
        "Authorization": f"Bearer {supabase_key}",
        "Content-Type": "application/json",
    }

    url = f"{SUPABASE_URL}/rest/v1/{TABLE_NAME}?select=*"

    try:
        response = httpx.get(url, headers=headers, timeout=30.0)
        response.raise_for_status()
        rows = response.json()
        logger.info(f"✅ Fetched {len(rows)} KB entries from '{TABLE_NAME}'")
        return rows
    except Exception as e:
        logger.error(f"❌ Failed to fetch KB entries: {e}", exc_info=True)
        return []


# ============================================
# TEXT PROCESSING UTILITIES
# ============================================

def normalize_text(text: str) -> str:
    """Normalize text for matching (lowercase, remove stop words, etc.)."""
    if not text:
        return ""
    result = text.lower().strip()
    result = re.sub(r'\s+', ' ', result)
    result = re.sub(r'[^a-z0-9\s?!.,\'-]', '', result)
    result = re.sub(r'(\.)\1{2,}', r'\1\1', result)
    # Remove filler phrases
    for filler in ['please', 'kindly', 'could you', 'can you', 'would you', 'tell me', 'show me', 'let me know']:
        result = re.sub(rf'\b{filler}\b', '', result, flags=re.IGNORECASE)
    result = re.sub(r'^[.,?!\s]+|[.,?!\s]+$', '', result).strip()
    return result


def extract_keywords(text: str) -> List[str]:
    """Extract meaningful keywords from text (remove stop words, stem)."""
    if not text:
        return []

    stop_words = {
        'a', 'an', 'the', 'is', 'are', 'was', 'were', 'be', 'been', 'being',
        'have', 'has', 'had', 'do', 'does', 'did', 'will', 'would', 'should',
        'could', 'may', 'might', 'must', 'can', 'of', 'in', 'on', 'at', 'to',
        'for', 'with', 'by', 'from', 'about', 'as', 'into', 'through', 'during',
        'what', 'when', 'where', 'who', 'why', 'how', 'hi', 'hello', 'hey', 'hii',
    }

    words = text.lower().split()
    words = [w for w in words if len(w) > 2 and w not in stop_words and re.search(r'[a-z]', w)]

    # Simple stemming
    stemmed = []
    for word in words:
        w = word
        if w.endswith('ing'):
            w = w[:-3]
        elif w.endswith('ed'):
            w = w[:-2]
        elif w.endswith('es'):
            w = w[:-2]
        elif w.endswith('s') and not w.endswith('ss'):
            w = w[:-1]
        elif w.endswith('ly'):
            w = w[:-2]
        if w:
            stemmed.append(w)
    return stemmed


# ============================================
# SIMILARITY FUNCTIONS
# ============================================

def cosine_similarity(vec_a: List[float], vec_b: List[float]) -> float:
    """Compute cosine similarity between two vectors."""
    if not vec_a or not vec_b or len(vec_a) != len(vec_b):
        return 0.0

    dot_product = sum(a * b for a, b in zip(vec_a, vec_b))
    norm_a = math.sqrt(sum(a * a for a in vec_a))
    norm_b = math.sqrt(sum(b * b for b in vec_b))

    if norm_a == 0 or norm_b == 0:
        return 0.0
    return dot_product / (norm_a * norm_b)


def keyword_overlap_score(keywords1: List[str], keywords2: List[str]) -> float:
    """Calculate keyword overlap using Jaccard + recall + F1."""
    if not keywords1 or not keywords2:
        return 0.0

    intersection = [k for k in keywords1 if k in keywords2]
    unique = list(set(keywords1 + keywords2))

    jaccard = len(intersection) / len(unique) if unique else 0
    recall = len(intersection) / len(keywords1) if keywords1 else 0
    precision = len(intersection) / len(keywords2) if keywords2 else 0

    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0

    return (jaccard * 0.3) + (recall * 0.4) + (f1 * 0.3)


def levenshtein_similarity(str1: str, str2: str) -> float:
    """Calculate Levenshtein similarity (1 - normalized distance)."""
    len1, len2 = len(str1), len(str2)
    if max(len1, len2) == 0:
        return 1.0

    matrix = [[0] * (len1 + 1) for _ in range(len2 + 1)]

    for i in range(len2 + 1):
        matrix[i][0] = i
    for j in range(len1 + 1):
        matrix[0][j] = j

    for i in range(1, len2 + 1):
        for j in range(1, len1 + 1):
            cost = 0 if str2[i - 1] == str1[j - 1] else 1
            matrix[i][j] = min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost,
            )

    return 1 - (matrix[len2][len1] / max(len1, len2))


def parse_embedding(embedding) -> Optional[List[float]]:
    """Parse embedding from various formats (list, JSON string, etc.)."""
    if embedding is None:
        return None
    if isinstance(embedding, list):
        return embedding
    if isinstance(embedding, str):
        try:
            parsed = json.loads(embedding)
            return parsed if isinstance(parsed, list) else None
        except (json.JSONDecodeError, ValueError):
            return None
    return None


# ============================================
# CONTEXT-AWARE MATCHING
# ============================================

def check_contextual_relevance(
    db_question: str,
    conversation_history: str,
    context_data: str,
) -> float:
    """Check if DB question is contextually relevant to recent conversation."""
    context_boost = 0.0

    if conversation_history:
        recent_topics = extract_keywords(conversation_history)
        db_keywords = extract_keywords(db_question)
        overlap = [k for k in db_keywords if k in recent_topics]
        if overlap:
            context_boost = 0.08 * (len(overlap) / max(len(db_keywords), 1))

    return min(context_boost, 0.15)


# ============================================
# UNIFIED SCORING FUNCTION
# ============================================

def calculate_match_score(
    user_question: str,
    db_question: str,
    db_embedding,
    user_embedding: List[float],
    user_keywords: List[str],
    db_keywords: List[str],
    conversation_history: str,
    context_data: str,
) -> Dict:
    """Calculate a unified match score combining multiple signals."""
    scores = {
        "exact": 0.0,
        "fuzzy": 0.0,
        "keyword": 0.0,
        "semantic": 0.0,
        "context": 0.0,
        "combined": 0.0,
    }
    match_type = "semantic"
    confidence = "low"

    # Exact match
    if user_question == db_question:
        scores["exact"] = 1.0
        scores["combined"] = 1.0
        return {"scores": scores, "match_type": "exact", "confidence": "high"}

    # Fuzzy match
    scores["fuzzy"] = levenshtein_similarity(user_question, db_question)
    scores["keyword"] = keyword_overlap_score(user_keywords, db_keywords)

    # Semantic match
    parsed_db_embedding = parse_embedding(db_embedding)
    if parsed_db_embedding and len(parsed_db_embedding) == len(user_embedding):
        scores["semantic"] = cosine_similarity(user_embedding, parsed_db_embedding)

    # Context boost
    scores["context"] = check_contextual_relevance(db_question, conversation_history, context_data)

    # Combine scores based on best matching strategy
    if scores["fuzzy"] >= CONFIG["HIGH_FUZZY_THRESHOLD"]:
        scores["combined"] = scores["fuzzy"] + scores["context"]
        match_type = "fuzzy"
        confidence = "high"
    elif scores["fuzzy"] >= CONFIG["MEDIUM_FUZZY_THRESHOLD"] and scores["keyword"] >= CONFIG["MIN_KEYWORD_OVERLAP"]:
        scores["combined"] = (scores["fuzzy"] * 0.6) + (scores["keyword"] * 0.4) + scores["context"]
        match_type = "fuzzy_keyword"
        confidence = "medium"
    elif scores["semantic"] >= 0.60 and scores["keyword"] >= 0.50:
        scores["combined"] = (scores["semantic"] * 0.6) + (scores["keyword"] * 0.4) + scores["context"]
        match_type = "semantic_keyword"
        confidence = "medium"
    elif scores["semantic"] >= CONFIG["SEMANTIC_BASE_THRESHOLD"]:
        keyword_boost = scores["keyword"] * 0.10 if scores["keyword"] > 0.3 else 0
        scores["combined"] = min(scores["semantic"] + keyword_boost + scores["context"], 0.98)
        match_type = "semantic_contextual"
        confidence = "high" if scores["combined"] >= 0.70 else ("medium" if scores["combined"] >= 0.55 else "low")
    else:
        scores["combined"] = (
            scores["semantic"] * CONFIG["SEMANTIC_WEIGHT"]
            + scores["keyword"] * CONFIG["KEYWORD_WEIGHT"]
            + scores["fuzzy"] * CONFIG["FUZZY_WEIGHT"]
            + scores["context"]
        )
        match_type = "hybrid"
        confidence = "low"

    scores["combined"] = min(scores["combined"], 0.99)

    return {"scores": scores, "match_type": match_type, "confidence": confidence}


# ============================================
# ADAPTIVE THRESHOLD
# ============================================

def calculate_threshold(
    normalized_question: str,
    word_count: int,
    is_question: bool,
    is_follow_up: bool,
    message_count: int,
) -> float:
    """Calculate an adaptive matching threshold based on question characteristics."""
    if word_count <= 2:
        threshold = 0.42
    elif word_count <= 4:
        threshold = 0.47
    elif word_count <= 7:
        threshold = 0.50
    elif word_count <= 12:
        threshold = 0.53
    else:
        threshold = 0.56

    if not is_question:
        threshold -= 0.03

    if message_count > 2:
        threshold -= CONFIG["RETURNING_USER_THRESHOLD_REDUCTION"]

    if is_follow_up:
        threshold -= 0.05

    return max(0.35, min(threshold, 0.65))


# ============================================
# MAIN SMART CONTEXT MATCHING
# ============================================

def smart_context_match(
    user_message: str,
    user_embedding: List[float],
    kb_entries: List[Dict],
    conversation_history: str = "",
    context_data: str = "",
    message_count: int = 0,
) -> Dict:
    """
    Full port of the Smart Context Matching1 n8n Code node.
    Searches KB entries using semantic + keyword + fuzzy matching.

    Returns:
    {
        "route": "found" | "not_found",
        "answer": str | None,
        "matched_question": str | None,
        "similarity_score": str,
        "match_type": str,
        "confidence_level": str,
    }
    """
    normalized_question = normalize_text(user_message)
    user_keywords = extract_keywords(normalized_question)
    words = normalized_question.split()
    word_count = len(words)
    is_question = bool(re.search(r'\?', user_message)) or bool(
        re.match(r'^(what|when|where|who|why|how|can|could|would|should|is|are|do|does)', user_message, re.IGNORECASE)
    )
    is_follow_up = message_count > 0 and bool(
        re.search(r'\b(more|also|what about|tell me|continue|explain|elaborate|and|additionally)\b', user_message, re.IGNORECASE)
    )

    matches = []

    for entry in kb_entries:
        db_question = entry.get("Questions", "")
        db_answer = entry.get("Answers", "") or entry.get("answer", "")
        db_embedding = entry.get("embedding")

        if not db_question or not db_answer:
            continue

        normalized_db = normalize_text(db_question)
        db_keywords = extract_keywords(normalized_db)

        result = calculate_match_score(
            normalized_question,
            normalized_db,
            db_embedding,
            user_embedding,
            user_keywords,
            db_keywords,
            conversation_history,
            context_data,
        )

        combined = result["scores"]["combined"]
        if combined > 0.30:
            matches.append({
                "question": db_question,
                "answer": db_answer,
                "similarity": combined,
                "match_type": result["match_type"],
                "confidence": result["confidence"],
                "context_boost": result["scores"]["context"],
            })

    # Sort by similarity descending
    matches.sort(key=lambda x: x["similarity"], reverse=True)

    # Decision logic
    threshold = calculate_threshold(normalized_question, word_count, is_question, is_follow_up, message_count)
    best_match = matches[0] if matches else None
    second_best = matches[1] if len(matches) > 1 else None

    confidence_gap = (best_match["similarity"] - second_best["similarity"]) if (best_match and second_best) else 1.0

    if best_match and best_match["similarity"] >= threshold:
        # Determine final confidence
        if best_match["match_type"] == "exact":
            final_confidence = "high"
        elif best_match["similarity"] >= 0.75 and confidence_gap > 0.15:
            final_confidence = "high"
        elif best_match["similarity"] >= 0.60 and confidence_gap > 0.10:
            final_confidence = "medium"
        else:
            final_confidence = "medium"

        logger.info(
            f"✅ KB match found: '{best_match['question'][:60]}' "
            f"(sim={best_match['similarity']:.2f}, type={best_match['match_type']}, conf={final_confidence})"
        )

        return {
            "route": "found",
            "answer": best_match["answer"],
            "matched_question": best_match["question"],
            "similarity_score": f"{round(best_match['similarity'] * 100)}%",
            "match_type": best_match["match_type"],
            "confidence_level": final_confidence,
            "total_candidates": len(matches),
        }
    else:
        logger.info(
            f"📭 No KB match above threshold ({threshold:.2f}). "
            f"Best: {best_match['similarity']:.2f if best_match else 0} for '{best_match['question'][:40] if best_match else 'none'}'"
        )

        return {
            "route": "not_found",
            "answer": None,
            "matched_question": best_match["question"] if best_match else None,
            "similarity_score": f"{round(best_match['similarity'] * 100)}%" if best_match else "0%",
            "match_type": best_match["match_type"] if best_match else "none",
            "confidence_level": "low",
            "total_candidates": len(matches),
        }
