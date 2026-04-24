"""
ai_responder.py — AI-powered responses and content safety validation.

Replicates the following n8n nodes:
  - "Get Knowledge Docs1" (fetch Google Doc content)
  - "AI Assistant Response1" (GPT-based response with session context + knowledge)
  - "AI Agent1" (Content Safety Validator)
  - "If" (safe/unsafe routing)

All LLM calls use OpenRouter (openai/gpt-4o-mini).
"""

import os
import json
import base64
import logging
from typing import Optional, Dict

from openai import OpenAI
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

KNOWLEDGE_DOC_ID = "14NkKSq8IvsMtgEy0gsJ6nvwelkPuOKupB2Oeq7kwIks"

# Google API scopes
_SCOPES = [
    "https://www.googleapis.com/auth/documents.readonly",
    "https://www.googleapis.com/auth/drive.readonly",
]

# Cache the knowledge doc content (it doesn't change frequently)
_knowledge_doc_cache: Optional[str] = None


def _get_openrouter_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def fetch_knowledge_doc() -> str:
    """
    Fetch the knowledge document content from Google Docs.
    Replicates the "Get Knowledge Docs1" node.
    Caches the result for the process lifetime.
    """
    global _knowledge_doc_cache
    if _knowledge_doc_cache is not None:
        return _knowledge_doc_cache

    doc_id = os.environ.get("PACKAGING_KNOWLEDGE_DOC_ID", KNOWLEDGE_DOC_ID)

    try:
        creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
        if not creds_b64:
            raise ValueError("GOOGLE_CREDENTIALS_BASE64 env var is not set")

        creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
        credentials = Credentials.from_service_account_info(creds_json, scopes=_SCOPES)
        service = build("docs", "v1", credentials=credentials)

        doc = service.documents().get(documentId=doc_id).execute()

        # Extract text content from the document
        content_parts = []
        for element in doc.get("body", {}).get("content", []):
            if "paragraph" in element:
                for elem in element["paragraph"].get("elements", []):
                    text_run = elem.get("textRun", {})
                    content = text_run.get("content", "")
                    if content.strip():
                        content_parts.append(content)

        full_content = "".join(content_parts)
        _knowledge_doc_cache = full_content
        logger.info(f"✅ Knowledge doc fetched ({len(full_content)} chars)")
        return full_content

    except Exception as e:
        logger.error(f"❌ Failed to fetch knowledge doc: {e}", exc_info=True)
        return ""


def get_ai_response(
    user_message: str,
    conversation_history: str,
    knowledge_doc_content: str,
) -> Optional[str]:
    """
    Generate an AI response using the packaging knowledge doc and conversation context.
    Replicates the "AI Assistant Response1" n8n node.
    """
    try:
        client = _get_openrouter_client()

        prompt = (
            f"You are packaging assistant with session memory.\n"
            f"Session Context: {conversation_history}\n\n"
            f'Question of user: "{user_message}"\n\n'
            f"Knowledge Base: {knowledge_doc_content[:8000]}\n"
            f"Instructions:\n"
            f"- Use conversation history for context-aware responses\n"
            f"- Reference previous questions if relevant\n"
            f"- Answer clearly in 2-4 lines\n"
            f"- If this is a follow-up, connect to previous discussion\n"
            f'- End with: "Would you like more details?"\n'
            f'- If unknown: "I don\'t have that information. Contact: info@packaging.com"'
        )

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": "You are a helpful packaging industry assistant."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.7,
            max_tokens=500,
        )

        ai_response = response.choices[0].message.content.strip()
        logger.info(f"✅ AI response generated ({len(ai_response)} chars)")
        return ai_response

    except Exception as e:
        logger.error(f"❌ AI response generation failed: {e}", exc_info=True)
        return None


def validate_content_safety(user_question: str, ai_response: str) -> Dict:
    """
    Validate an AI response for content safety.
    Replicates the "AI Agent1" Content Safety Validator node.

    Returns:
    {
        "is_safe": bool,
        "action": "approve" | "flag_for_review" | "reject",
        "reason": str,
    }
    """
    try:
        client = _get_openrouter_client()

        system_prompt = """You are a Content Safety Validator AI. Your role is to analyze AI-generated responses and detect problematic content that could be fraudulent, misleading, defamatory, or misuse celebrity/company names.

STRICT VALIDATION CRITERIA:

1. CELEBRITY/PUBLIC FIGURE MISUSE:
   - Reject any unauthorized use of real celebrity names
   - Reject claims like "X celebrity uses/endorses/recommends this"
   - Educational or factual mentions are acceptable

2. COMPANY NAME MISUSE:
   - Reject unauthorized endorsements using company names
   - Reject false affiliations or partnerships

3. FRAUDULENT CLAIMS:
   - Guaranteed returns/results
   - "Get rich quick" schemes
   - "100% success rate" promises
   - Miracle cures or unverified health claims

4. MISLEADING TACTICS:
   - "As seen on TV" (without proof)
   - False urgency
   - Unverifiable statistics

5. DEFAMATORY & POLITICAL CONTENT:
   - REJECT any response that validates defamatory claims about ANY public figure
   - REJECT political accusations without credible sources

OUTPUT FORMAT:
Always respond with valid JSON only:
{
  "is_safe": boolean,
  "severity": "none|low|medium|high|critical",
  "reason": "detailed explanation",
  "action": "approve|flag_for_review|reject"
}"""

        user_prompt = (
            f"Analyze the following AI-generated response for safety issues:\n\n"
            f"**Original User Question:**\n{user_question}\n\n"
            f"**AI Generated Output:**\n{ai_response}\n\n"
            f"Return your analysis in JSON format as specified."
        )

        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            response_format={"type": "json_object"},
            temperature=0,
        )

        raw = response.choices[0].message.content.strip()
        result = json.loads(raw)

        is_safe = result.get("is_safe", True)
        action = result.get("action", "approve")
        reason = result.get("reason", "")

        logger.info(f"🛡️ Safety check: safe={is_safe}, action={action}")
        return {"is_safe": is_safe, "action": action, "reason": reason}

    except Exception as e:
        logger.error(f"❌ Safety validation failed: {e}", exc_info=True)
        # Default to safe on error (don't block responses)
        return {"is_safe": True, "action": "approve", "reason": f"Validation error: {e}"}
