"""
intent_classifier.py — Categorises valid emails into one of four buckets.

Replicates AI Agent 1 + Structured Output Parser + Edit Fields + Switch from the n8n workflow.

Categories:
  - Ready to Send Data   → Has genuine packaging inquiry with specific questions
  - More Info Needed     → Too vague, only "Hi" or "Interested" with no questions
  - Not Interested       → Spam/promo/unrelated services
  - Pending              → Ambiguous, cannot decide
"""
import os
import json
import logging
from openai import OpenAI

logger = logging.getLogger(__name__)

CATEGORIES = ["Ready to Send Data", "More Info Needed", "Not Interested", "Pending"]

SYSTEM_PROMPT = """You are an AI assistant for a packaging manufacturing and export company.
The company provides custom packaging, bulk packaging supply, printed & branded packaging, and export services for businesses such as garments, textiles, FMCG, food & beverage, cosmetics, pharmaceuticals, and e-commerce brands.

Your task is to analyze incoming emails and classify them into one of four categories based on business relevance and purchase intent.

📌 Categorization Rules

1️⃣ Ready to Send Data ✅
The email clearly shows business or buying intent.
The sender:
- Asks ANY questions about packaging products or services (pricing, MOQ, materials, lead time, samples, customization)
- Mentions needing packaging for any product category
- Requests information about capabilities or services
- Shows interest in specific packaging types (boxes, bags, eco-friendly, branded, etc.)
- Uses professional language indicating a business inquiry
- Requests quotations, consultations, or information

➡️ CRITICAL: If the email asks specific questions about packaging services, materials, pricing, MOQ, lead time, sustainability, or any product-related queries, it is ALWAYS "Ready to Send Data".

Examples:
- "What is your minimum order quantity?" → Ready to Send Data
- "Can you help with packaging for cosmetics?" → Ready to Send Data
- "Do you offer sustainable packaging?" → Ready to Send Data
- "I need packaging for my products" → Ready to Send Data

2️⃣ More Info Needed 🔄
ONLY use this category when the email is EXTREMELY vague with ZERO specific questions.
Examples:
- "Hi" → More Info Needed
- "Interested" → More Info Needed
- "Tell me more" (no context) → More Info Needed

3️⃣ Not Interested ❌
The email is not relevant to the packaging business.
Examples: SEO services, marketing promo, IT services, recruitment, newsletters.

4️⃣ Pending (Undecidable) ⏳
Might be relevant but intent is completely unclear; doesn't fit any other category.

Return ONLY valid JSON in this exact format:
{
  "category": "Ready to Send Data",
  "reasons": ["reason 1", "reason 2"]
}"""


def classify_intent(cleaned_content: str) -> dict:
    """
    Classify the intent of a cleaned email body.
    Returns dict: {"category": str, "reasons": list[str]}
    Defaults to Pending on error.
    """
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        logger.error("❌ OPENROUTER_API_KEY not set")
        return {"category": "Pending", "reasons": ["API key missing"]}

    client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=api_key,
    )

    user_prompt = (
        f"Analyze the following email and categorize it:\n\n"
        f"**Email Content:**\n{cleaned_content[:3000]}\n\n"
        f"Return ONLY the JSON object as specified."
    )

    try:
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )
        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        category = result.get("category", "Pending")
        # Validate category
        if category not in CATEGORIES:
            logger.warning(f"⚠️ Unknown category '{category}' — defaulting to Pending")
            category = "Pending"

        reasons = result.get("reasons", [])
        logger.info(f"🏷️  Intent category: {category} | Reasons: {reasons}")
        return {"category": category, "reasons": reasons}

    except Exception as e:
        logger.error(f"❌ Intent classification failed: {e}", exc_info=True)
        return {"category": "Pending", "reasons": [str(e)]}
