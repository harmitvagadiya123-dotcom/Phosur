"""
email_formatter.py — Generates professional HTML email responses via OpenRouter.

Replicates three AI agents from the n8n workflow:
  - AI Agent 2: Format reply from KB answer (data_found=True, Ready to Send Data)
  - AI Agent 3: Generate fallback reply (data_found=False, Ready to Send Data)
  - AI Agent 4: Clarification reply (More Info Needed)

All use openai/gpt-4o-mini via OpenRouter.
"""
import os
import json
import logging
from typing import List, Dict, Optional
from openai import OpenAI

logger = logging.getLogger(__name__)

SIGNATURE = """Pratyush Bajpai
Head of Sales and Marketing
Shubh Packaging
Bespoke Packaging Manufacturer | Corrugated & Mono Carton Specialists | Advanced Print Finishing

+91-8824907351
www.shubhpackaging.in
Udaipur, India
Bulk Production | Global Supplier"""

COMPANY_DETAILS = (
    "Shubh Packaging, A leading packaging manufacturing and export company specializing "
    "in custom packaging, bulk packaging supply, printed & branded packaging, and export "
    "services for businesses in garments, textiles, FMCG, food & beverage, cosmetics, "
    "pharmaceuticals, and e-commerce."
)


def _get_client() -> OpenAI:
    api_key = os.environ.get("OPENROUTER_API_KEY", "")
    if not api_key:
        raise ValueError("OPENROUTER_API_KEY not set")
    return OpenAI(base_url="https://openrouter.ai/api/v1", api_key=api_key)


def _call_llm(system: str, user: str) -> Optional[str]:
    """Helper: call OpenRouter and return raw text response."""
    try:
        client = _get_client()
        response = client.chat.completions.create(
            model="openai/gpt-4o-mini",
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            response_format={"type": "json_object"},
            temperature=0.7,
        )
        return response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"❌ LLM call failed: {e}", exc_info=True)
        return None


# ─────────────────────────────────────────────
# AI Agent 2: Format reply using KB answer
# ─────────────────────────────────────────────
def format_kb_reply(
    original_subject: str,
    kb_answer: str,
    sender_name: str,
) -> str:
    """
    Generate a professional HTML email reply using a matched KB answer.
    Replicates AI Agent 2.
    Returns formatted HTML string (ready to send).
    """
    system = f"""You are an AI email formatter specializing in crafting professional HTML email responses for a packaging manufacturing and export company.

Your Task:
- Convert the provided text response into a well-structured, email-friendly HTML format.
- Ensure the response is clear, visually appealing, and well-organized.
- Use proper HTML tags like <h2>, <p>, <strong>, <br> for better readability.
- The email should start with a friendly greeting that includes the sender's name.
- Do NOT generate any email subject in the body.
- Format important details (pricing, MOQ, materials, lead times, packaging specifications) in bold.
- Ensure the response is concise, properly spaced, and mobile-friendly.

Return Format (STRICT JSON Only):
Return only a valid JSON object, without markdown, code blocks, or extra formatting:
{{
  "formatted_response": "<Complete HTML email excluding subject>"
}}"""

    user = f"""Generate a well-structured HTML email response using the given subject and response text.

Original Email Subject: {original_subject}
Response Text: {kb_answer}
Sender Name: {sender_name}
Company Name: Shubh Packaging

Your signature to include:
{SIGNATURE}

Return ONLY the JSON object."""

    raw = _call_llm(system, user)
    if not raw:
        return _fallback_html(sender_name, kb_answer)

    try:
        parsed = json.loads(raw)
        html = parsed.get("formatted_response", "")
        if html:
            logger.info("✅ AI Agent 2: KB-based reply formatted")
            return html
    except Exception as e:
        logger.error(f"❌ Agent 2 JSON parse error: {e}")

    return _fallback_html(sender_name, kb_answer)


# ─────────────────────────────────────────────
# AI Agent 3: Generate fallback reply (no KB match)
# ─────────────────────────────────────────────
def format_fallback_reply(
    original_subject: str,
    email_content: str,
    sender_name: str,
) -> str:
    """
    Generate a persuasive engagement email when no KB match is found.
    Replicates AI Agent 3.
    Returns formatted HTML string.
    """
    system = f"""You are a professional AI email assistant specializing in customer engagement and persuasion for a packaging manufacturing and export company.

Instructions:
- Start with a warm greeting that acknowledges the customer's email and includes their name.
- Reassure them that the team is working on their packaging requirements and will follow up soon.
- Make the email engaging by sharing relevant information about the company's packaging expertise:
  materials (boxes, cartons, bags, eco-friendly options), customization capabilities, and export services.
- Use persuasive language to keep the customer interested while they wait for a final response.
- Do NOT generate any email subject in the body.
- End with a professional and friendly closing.

Email Formatting:
- Use proper HTML tags for structure and readability.
- Ensure the response is mobile-friendly and visually appealing.
- Highlight important details using bold text.

Output Format:
Return a JSON object with:
  formatted_response: The complete HTML-formatted email (excluding the subject).

Do NOT include extra text, explanations, or formatting outside the JSON structure."""

    user = f"""Generate a persuasive and professional email response to engage the customer when no direct answer is available.

Original Email Subject: {original_subject}
Original Email Content: {email_content}
Sender Name: {sender_name}
Company Name: Shubh Packaging
Company Details: {COMPANY_DETAILS}

Your signature to include:
{SIGNATURE}

Return ONLY the JSON object:
{{
  "formatted_response": "<HTML email>"
}}"""

    raw = _call_llm(system, user)
    if not raw:
        return _generic_engagement_html(sender_name)

    try:
        parsed = json.loads(raw)
        html = parsed.get("formatted_response", "")
        if html:
            logger.info("✅ AI Agent 3: Fallback engagement reply formatted")
            return html
    except Exception as e:
        logger.error(f"❌ Agent 3 JSON parse error: {e}")

    return _generic_engagement_html(sender_name)


# ─────────────────────────────────────────────
# AI Agent 4: Clarification reply (More Info Needed)
# ─────────────────────────────────────────────
def format_clarification_reply(
    original_subject: str,
    email_content: str,
    sender_name: str,
    kb_results: List[Dict],
) -> str:
    """
    Generate a clarification request email with helpful KB snippets.
    Replicates AI Agent 4.
    Returns formatted HTML string.
    """
    system = f"""You are an AI assistant for Shubh Packaging manufacturing and export company. The company specializes in custom packaging, bulk packaging supply, printed & branded packaging, and export services for businesses in garments, textiles, FMCG, food & beverage, cosmetics, pharmaceuticals, and e-commerce.

Your task is to generate a professional, well-structured HTML email response when an incoming email lacks enough clarity for an immediate answer.

Steps to Follow:
1. Clarification Request: Identify missing or unclear details from the sender's message about packaging requirements. Politely ask for more specific information.
2. Retrieve Relevant Information: Summarize key points from available packaging solutions (materials, customization options, MOQ, lead times, export capabilities).
3. Company Information: Include a brief introduction about the company, highlighting packaging manufacturing and export services.
4. Professional & Engaging Tone: Begin with a greeting that includes the sender's name. Do not generate any subject line.
5. Format Response in Proper HTML: Use <h1>, <h2>, <p>, <ul>, <li>, <strong> for structure.

Email Signature:
{SIGNATURE}

Response Format (Strict JSON Only):
Return ONLY a JSON object:
{{
  "response": "Generated email response in HTML"
}}"""

    # Summarise top KB results for context
    kb_summary = ""
    for i, row in enumerate(kb_results[:3], 1):
        kb_summary += f"\n{i}. Q: {row.get('content', '')}\n   A: {row.get('answer', '')}\n"

    user = f"""Generate a clarification request email.

Email Subject: {original_subject}
Email Content: {email_content}
Sender Name: {sender_name}
Company Name: Shubh Packaging

Relevant KB Snippets (use for context):
{kb_summary if kb_summary else "No KB matches available."}

Return ONLY the JSON object."""

    raw = _call_llm(system, user)
    if not raw:
        return _generic_engagement_html(sender_name)

    try:
        parsed = json.loads(raw)
        html = parsed.get("response", parsed.get("formatted_response", ""))
        if html:
            logger.info("✅ AI Agent 4: Clarification reply formatted")
            return html
    except Exception as e:
        logger.error(f"❌ Agent 4 JSON parse error: {e}")

    return _generic_engagement_html(sender_name)


# ─────────────────────────────────────────────
# Simple HTML fallbacks (if LLM fails)
# ─────────────────────────────────────────────
def _fallback_html(sender_name: str, answer: str) -> str:
    greeting = f"Dear {sender_name}," if sender_name else "Dear Sir/Madam,"
    return f"""<p>{greeting}</p>
<p>Thank you for reaching out to Shubh Packaging.</p>
<p>{answer}</p>
<p>Please feel free to contact us if you have further questions.</p>
<br>
<p>Best regards,<br>
<strong>Pratyush Bajpai</strong><br>
Head of Sales and Marketing<br>
Shubh Packaging<br>
+91-8824907351 | www.shubhpackaging.in</p>"""


def _generic_engagement_html(sender_name: str) -> str:
    greeting = f"Dear {sender_name}," if sender_name else "Dear Sir/Madam,"
    return f"""<p>{greeting}</p>
<p>Thank you for contacting <strong>Shubh Packaging</strong>. We have received your inquiry and our team is reviewing it carefully.</p>
<p>We specialize in <strong>corrugated boxes, mono cartons, custom branded packaging</strong>, and export services for businesses across FMCG, pharmaceuticals, cosmetics, e-commerce, and more.</p>
<p>A dedicated team member will get back to you shortly with detailed information tailored to your requirements.</p>
<br>
<p>Best regards,<br>
<strong>Pratyush Bajpai</strong><br>
Head of Sales and Marketing<br>
Shubh Packaging — Bespoke Packaging Manufacturer<br>
+91-8824907351 | www.shubhpackaging.in | Udaipur, India</p>"""
