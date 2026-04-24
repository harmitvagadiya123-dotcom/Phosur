"""
chatbot_agent.py — Main orchestrator for the Packaging Chatbot Agent.

Replaces the full n8n 'Packaging_Chatbot_ Phosur' workflow in Python.

Pipeline:
  1. Receive message with session_id
  2. Lookup session in Google Sheet
  3. If new session → create session + return welcome message
  4. If existing session:
     a. Check for company details (regex) → extract via AI → save to sheet
     b. Check buying intent → update customer sheet
     c. Generate embedding → search Supabase KB (smart context matching)
     d. If KB match found → return matched answer
     e. If no KB match → fetch knowledge doc → AI response → safety check
  5. Update session history
  6. Return response
"""

import logging
from typing import Dict

from .session_service import lookup_session, create_session, update_session_history
from .contact_extractor import (
    has_company_details,
    extract_contact_details_regex,
    extract_contact_details_ai,
    save_customer_info,
)
from .buying_intent_detector import detect_buying_intent, update_buying_intent_sheet
from .kb_search import generate_embedding, fetch_all_kb_entries, smart_context_match
from .ai_responder import fetch_knowledge_doc, get_ai_response, validate_content_safety

logger = logging.getLogger(__name__)

WELCOME_MESSAGE = (
    "Hello! I'm Rui 👋\n\n"
    "I'm here to help you get started. To provide you with the best service, "
    "could you please share:\n\n"
    "1. Your Name\n"
    "2. Your company website\n"
    "3. Phone Number\n"
    "4. Email Address\n\n"
    "You can share all details in one message!"
)

DETAILS_RECEIVED_MESSAGE = (
    "Thank you for providing your company details! "
    "If you have any doubts, feel free to ask."
)

UNSAFE_CONTENT_MESSAGE = (
    "I apologize, but I cannot provide that response "
    "as it may contain inappropriate content."
)

FALLBACK_ERROR_MESSAGE = (
    "I'm sorry, I couldn't process your request right now. "
    "Please try again or contact us at info@packaging.com."
)


class PackagingChatbotAgent:
    """
    Packaging Chatbot Agent.
    Processes incoming messages and returns responses.
    """

    def process(self, session_id: str, message: str, user_id: str = "anonymous") -> Dict:
        """
        Main entry point. Process a user message and return a response.

        Args:
            session_id: Unique session identifier from the frontend
            message: The user's message text
            user_id: Optional user identifier

        Returns:
            {
                "answer": str,
                "session_id": str,
                "status": str,  # "new_session" | "details_received" | "kb_match" | "ai_response" | "error"
            }
        """
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        logger.info(f"📨 Chatbot received: session={session_id}, message='{message[:60]}'")
        logger.info(f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")

        try:
            # ── Step 1: Lookup session ────────────────────────
            session = lookup_session(session_id)

            # ── Step 2: New session flow ──────────────────────
            if session is None:
                logger.info("🆕 New session — creating and sending welcome")
                create_session(session_id, message)
                return {
                    "answer": WELCOME_MESSAGE,
                    "session_id": session_id,
                    "status": "new_session",
                }

            # ── Step 3: Existing session — process message ────
            conversation_history = str(session.get("conversation_history", ""))
            context_data = str(session.get("context_data", ""))
            # Count messages to determine if returning user
            message_count = len(conversation_history.split(",")) if conversation_history else 0

            # ── Step 3a: Check for company details ────────────
            if has_company_details(message):
                logger.info("📋 Company details detected — extracting and saving")
                return self._handle_company_details(session_id, message, conversation_history)

            # ── Step 3b: Check buying intent ──────────────────
            intent_result = detect_buying_intent(message)
            if intent_result["has_buying_intent"]:
                logger.info(f"🎯 Buying intent detected: {intent_result['intent_level']}")
                update_buying_intent_sheet(
                    session_id,
                    intent_result["intent_level"],
                    conversation_history,
                )

            # ── Step 3c: KB search ────────────────────────────
            return self._handle_question(
                session_id, message, conversation_history, context_data, message_count
            )

        except Exception as e:
            logger.error(f"💥 Chatbot error: {e}", exc_info=True)
            return {
                "answer": FALLBACK_ERROR_MESSAGE,
                "session_id": session_id,
                "status": "error",
            }

    def _handle_company_details(
        self, session_id: str, message: str, conversation_history: str
    ) -> Dict:
        """Handle messages containing company/contact details."""
        # Step 1: Regex extraction
        regex_data = extract_contact_details_regex(message)

        # Step 2: AI extraction (enhances regex results)
        ai_data = extract_contact_details_ai(message, regex_data)

        # Step 3: Save to Google Sheet
        save_customer_info(session_id, ai_data)

        # Step 4: Update session history
        update_session_history(session_id, message, DETAILS_RECEIVED_MESSAGE)

        return {
            "answer": DETAILS_RECEIVED_MESSAGE,
            "session_id": session_id,
            "status": "details_received",
        }

    def _handle_question(
        self,
        session_id: str,
        message: str,
        conversation_history: str,
        context_data: str,
        message_count: int,
    ) -> Dict:
        """Handle a question/query message — KB search + AI fallback."""

        # ── Generate embedding ────────────────────────────
        user_embedding = generate_embedding(message)
        if user_embedding is None:
            logger.warning("⚠️ Embedding generation failed — falling back to AI response")
            return self._handle_ai_fallback(session_id, message, conversation_history)

        # ── Fetch KB entries from Supabase ────────────────
        kb_entries = fetch_all_kb_entries()
        if not kb_entries:
            logger.warning("⚠️ No KB entries fetched — falling back to AI response")
            return self._handle_ai_fallback(session_id, message, conversation_history)

        # ── Smart context matching ────────────────────────
        match_result = smart_context_match(
            user_message=message,
            user_embedding=user_embedding,
            kb_entries=kb_entries,
            conversation_history=conversation_history,
            context_data=context_data,
            message_count=message_count,
        )

        if match_result["route"] == "found":
            # ── KB match found ────────────────────────────
            answer = match_result["answer"]
            logger.info(f"✅ Returning KB answer (sim={match_result['similarity_score']})")

            # Update session history
            update_session_history(session_id, message, answer)

            return {
                "answer": answer,
                "session_id": session_id,
                "status": "kb_match",
            }
        else:
            # ── No KB match — AI fallback ─────────────────
            return self._handle_ai_fallback(session_id, message, conversation_history)

    def _handle_ai_fallback(
        self, session_id: str, message: str, conversation_history: str
    ) -> Dict:
        """Generate an AI response when no KB match is found."""
        logger.info("🤖 Generating AI fallback response...")

        # Fetch knowledge doc
        knowledge_content = fetch_knowledge_doc()

        # Generate AI response
        ai_response = get_ai_response(message, conversation_history, knowledge_content)

        if ai_response is None:
            update_session_history(session_id, message, FALLBACK_ERROR_MESSAGE)
            return {
                "answer": FALLBACK_ERROR_MESSAGE,
                "session_id": session_id,
                "status": "error",
            }

        # Content safety validation
        safety = validate_content_safety(message, ai_response)

        if safety["is_safe"] and safety["action"] == "approve":
            logger.info("✅ AI response passed safety check")
            update_session_history(session_id, message, ai_response)
            return {
                "answer": ai_response,
                "session_id": session_id,
                "status": "ai_response",
            }
        else:
            logger.warning(f"🛡️ AI response BLOCKED: {safety['reason']}")
            update_session_history(session_id, message, UNSAFE_CONTENT_MESSAGE)
            return {
                "answer": UNSAFE_CONTENT_MESSAGE,
                "session_id": session_id,
                "status": "blocked",
            }
