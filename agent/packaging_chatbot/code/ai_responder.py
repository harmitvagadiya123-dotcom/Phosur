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

import httpx
from openai import OpenAI
from google.oauth2.service_account import Credentials
from google.auth.transport.requests import Request as AuthRequest

logger = logging.getLogger(__name__)

KNOWLEDGE_DOC_ID = "1OS2in1xIy3kOYhl-5XiYILe8dlJmFzL3Efh6U9IaDzE"

# Google API scopes — Drive scope is enough to export docs as text
_SCOPES = [
    "https://www.googleapis.com/auth/drive.readonly",
]

# Cache the knowledge doc content (it doesn't change frequently)
_knowledge_doc_cache: Optional[str] = None


def _get_openrouter_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def _get_google_credentials() -> Credentials:
    """Get Google service account credentials from env."""
    creds_b64 = os.environ.get("GOOGLE_CREDENTIALS_BASE64", "")
    if not creds_b64:
        raise ValueError("GOOGLE_CREDENTIALS_BASE64 env var is not set")
    creds_json = json.loads(base64.b64decode(creds_b64).decode("utf-8"))
    credentials = Credentials.from_service_account_info(creds_json, scopes=_SCOPES)
    credentials.refresh(AuthRequest())
    return credentials


def fetch_knowledge_doc() -> str:
    """
    Fetch the knowledge document content from Google Docs using Drive export API.
    Uses the Drive API to export the doc as plain text — no need for the Docs API.
    Caches the result for the process lifetime.
    """
    global _knowledge_doc_cache
    if _knowledge_doc_cache is not None:
        return _knowledge_doc_cache

    doc_id = os.environ.get("PACKAGING_KNOWLEDGE_DOC_ID", KNOWLEDGE_DOC_ID)

    try:
        # Method 1: Use Google Drive export API (works with Drive scope)
        credentials = _get_google_credentials()
        export_url = f"https://www.googleapis.com/drive/v3/files/{doc_id}/export?mimeType=text/plain"

        response = httpx.get(
            export_url,
            headers={"Authorization": f"Bearer {credentials.token}"},
            timeout=30.0,
        )
        response.raise_for_status()
        full_content = response.text

        if full_content and len(full_content) > 50:
            _knowledge_doc_cache = full_content
            logger.info(f"✅ Knowledge doc fetched via Drive export ({len(full_content)} chars)")
            return full_content

    except Exception as e:
        logger.warning(f"⚠️ Drive export failed: {e}")

    # Method 2: Try fetching as published doc (public URL fallback)
    try:
        published_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        response = httpx.get(published_url, timeout=30.0, follow_redirects=True)
        response.raise_for_status()
        full_content = response.text

        if full_content and len(full_content) > 50:
            _knowledge_doc_cache = full_content
            logger.info(f"✅ Knowledge doc fetched via public export ({len(full_content)} chars)")
            return full_content

    except Exception as e:
        logger.warning(f"⚠️ Public export also failed: {e}")

    logger.error("❌ Could not fetch knowledge doc via any method")
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
