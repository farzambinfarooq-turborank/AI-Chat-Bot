import os
import re
import hmac
import logging
from typing import Optional, Dict, Any, List, Tuple

import httpx


# ==========================================================
# ENVIRONMENT
# ==========================================================

WHATSAPP_ACCESS_TOKEN = os.getenv("WHATSAPP_ACCESS_TOKEN")
WHATSAPP_PHONE_NUMBER_ID = os.getenv("WHATSAPP_PHONE_NUMBER_ID")
WHATSAPP_VERIFY_TOKEN = os.getenv("WHATSAPP_VERIFY_TOKEN")
WHATSAPP_API_VERSION = os.getenv("WHATSAPP_API_VERSION", "v21.0")

# Sirf debugging ke liye (/debug/whatsapp-templates). Asli number wale
# WABA ki ID: Meta Developers -> WhatsApp -> API Setup par likhi hoti hai.
WHATSAPP_BUSINESS_ACCOUNT_ID = os.getenv("WHATSAPP_BUSINESS_ACCOUNT_ID")

GRAPH_BASE_URL = "https://graph.facebook.com"


def _messages_url() -> str:
    return (
        f"{GRAPH_BASE_URL}/{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/messages"
    )


def _media_upload_url() -> str:
    return (
        f"{GRAPH_BASE_URL}/{WHATSAPP_API_VERSION}/"
        f"{WHATSAPP_PHONE_NUMBER_ID}/media"
    )


def _media_lookup_url(media_id: str) -> str:
    return f"{GRAPH_BASE_URL}/{WHATSAPP_API_VERSION}/{media_id}"


logger = logging.getLogger("whatsapp_agent")


# ==========================================================
# WEBHOOK VERIFICATION (Meta calls this once, on setup)
#
# Meta sends: GET /webhook?hub.mode=subscribe&hub.verify_token=...&hub.challenge=...
# You must echo back hub.challenge ONLY if the verify_token matches
# the one you set in your Meta App dashboard.
# ==========================================================

def verify_webhook_challenge(
    mode: Optional[str],
    token: Optional[str],
    challenge: Optional[str],
) -> Optional[str]:

    # Pehle None == None se verification pass ho sakti thi agar token set na ho.
    if (
        mode == "subscribe"
        and token
        and WHATSAPP_VERIFY_TOKEN
        and hmac.compare_digest(
            str(token).encode("utf-8"),
            WHATSAPP_VERIFY_TOKEN.encode("utf-8"),
        )
    ):
        return challenge

    return None


# ==========================================================
# PARSE INCOMING WEBHOOK PAYLOAD
#
# WhatsApp sends many payload shapes on the same webhook URL:
# - text messages
# - voice notes (type "audio")
# - message status updates (sent/delivered/read) — ignore these
# - other message types (image, video, location, etc.)
#
# We extract plain text messages AND audio voice notes here.
# Anything else returns an "unsupported_type" marker so the
# caller can skip it safely.
# ==========================================================

def extract_incoming_text_message(
    payload: Dict[str, Any],
) -> Optional[Dict[str, Any]]:

    try:

        entry = payload.get("entry", [])[0]
        change = entry.get("changes", [])[0]
        value = change.get("value", {})

        messages = value.get("messages")

        if not messages:
            # This is likely a status update (sent/delivered/read),
            # not a real incoming message.
            return None

        message = messages[0]

        contacts = value.get("contacts", [])
        profile_name = None

        if contacts:
            profile_name = (
                contacts[0]
                .get("profile", {})
                .get("name")
            )

        wa_id = message.get("from")  # e.g. "923001234567"
        message_id = message.get("id")

        # ------------------------------------------------------
        # TEXT MESSAGE
        # ------------------------------------------------------

        if message.get("type") == "text":

            text = message.get("text", {}).get("body", "")

            return {
                "wa_id": wa_id,
                "message_id": message_id,
                "text": text,
                "audio_id": None,
                "audio_mime_type": None,
                "profile_name": profile_name,
                "unsupported_type": None,
            }

        # ------------------------------------------------------
        # VOICE NOTE (audio)
        # ------------------------------------------------------

        if message.get("type") == "button":

            button = message.get("button", {}) or {}

            return {
                "wa_id": wa_id,
                "message_id": message_id,
                "text": button.get("text"),
                "audio_id": None,
                "audio_mime_type": None,
                "profile_name": profile_name,
                "unsupported_type": None,
                "button_payload": button.get("payload"),
            }

        if message.get("type") == "audio":

            audio = message.get("audio", {})

            return {
                "wa_id": wa_id,
                "message_id": message_id,
                "text": None,
                "audio_id": audio.get("id"),
                "audio_mime_type": audio.get(
                    "mime_type",
                    "audio/ogg",
                ),
                "profile_name": profile_name,
                "unsupported_type": None,
            }

        # ------------------------------------------------------
        # ANYTHING ELSE (image, video, location, etc.)
        # ------------------------------------------------------

        return {
            "wa_id": wa_id,
            "message_id": message_id,
            "text": None,
            "audio_id": None,
            "audio_mime_type": None,
            "profile_name": profile_name,
            "unsupported_type": message.get("type"),
        }

    except (IndexError, AttributeError, TypeError) as e:

        logger.debug("Failed to parse WhatsApp payload: %s", e)
        return None


# ==========================================================
# DOWNLOAD INCOMING VOICE NOTE
#
# Two-step process per Meta's Cloud API:
# 1. GET /{media-id}  -> returns a short-lived "url" + mime_type
# 2. GET that url (with the SAME access token) -> raw audio bytes
# ==========================================================

def download_whatsapp_media(
    media_id: str,
) -> Optional[Tuple[bytes, str]]:

    if not WHATSAPP_ACCESS_TOKEN:

        logger.error(
            "WhatsApp credentials missing — cannot download media."
        )
        return None

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }

    try:

        with httpx.Client(timeout=20.0) as http_client:

            lookup_response = http_client.get(
                _media_lookup_url(media_id),
                headers=headers,
            )

            if lookup_response.status_code >= 400:

                logger.error(
                    "WhatsApp media lookup failed [%s]: %s",
                    lookup_response.status_code,
                    lookup_response.text,
                )
                return None

            media_info = lookup_response.json()

            media_url = media_info.get("url")
            mime_type = media_info.get(
                "mime_type",
                "audio/ogg",
            )

            if not media_url:
                logger.error("WhatsApp media lookup returned no url.")
                return None

            download_response = http_client.get(
                media_url,
                headers=headers,
            )

            if download_response.status_code >= 400:

                logger.error(
                    "WhatsApp media download failed [%s]",
                    download_response.status_code,
                )
                return None

            return download_response.content, mime_type

    except httpx.HTTPError as e:

        logger.error("WhatsApp media download error: %s", e)
        return None


# ==========================================================
# UPLOAD OUTGOING VOICE REPLY
#
# WhatsApp requires media to be uploaded first (returns a
# media id), which is then referenced when sending the actual
# message. Use audio/ogg with the opus codec so it renders as
# a proper voice-note bubble on the customer's side.
# ==========================================================

def upload_whatsapp_media(
    file_bytes: bytes,
    mime_type: str = "audio/ogg; codecs=opus",
    filename: str = "voice_reply.ogg",
) -> Optional[str]:

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:

        logger.error(
            "WhatsApp credentials missing — cannot upload media."
        )
        return None

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }

    data = {
        "messaging_product": "whatsapp",
        "type": mime_type,
    }

    files = {
        "file": (filename, file_bytes, mime_type),
    }

    try:

        with httpx.Client(timeout=30.0) as http_client:

            response = http_client.post(
                _media_upload_url(),
                headers=headers,
                data=data,
                files=files,
            )

        if response.status_code >= 400:

            logger.error(
                "WhatsApp media upload failed [%s]: %s",
                response.status_code,
                response.text,
            )
            return None

        return response.json().get("id")

    except httpx.HTTPError as e:

        logger.error("WhatsApp media upload error: %s", e)
        return None


# ==========================================================
# SEND TEXT MESSAGE
#
# IMPORTANT LIMITATION (Meta policy, not a bug):
# A plain text message like this can ONLY be delivered if the
# customer has messaged this WhatsApp number within the last
# 24 hours ("customer service window"). Outside that window,
# Meta silently rejects it. For messages a business needs to
# INITIATE (like an order confirmation request, where the
# customer may not have messaged recently or at all), use
# send_whatsapp_template() below instead — it works regardless
# of the 24-hour window because it uses a Meta-approved
# template.
# ==========================================================

def send_whatsapp_text(
    to_wa_id: str,
    text: str,
) -> bool:

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:

        logger.error(
            "WhatsApp credentials missing — cannot send message."
        )
        return False

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {
            "preview_url": False,
            "body": text,
        },
    }

    try:

        with httpx.Client(timeout=15.0) as client:

            response = client.post(
                _messages_url(),
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:

            logger.error(
                "WhatsApp send failed [%s]: %s",
                response.status_code,
                response.text,
            )
            return False

        return True

    except httpx.HTTPError as e:

        logger.error("WhatsApp send request error: %s", e)
        return False


# ==========================================================
# SEND TEMPLATE MESSAGE
#
# Use this for any message the BUSINESS initiates (the
# customer hasn't necessarily messaged recently) — e.g. an
# order confirmation request right after a website order
# comes in. `template_name` must exactly match an APPROVED
# template in Meta Business Manager -> WhatsApp Manager ->
# Message Templates. `body_parameters` fills the template's
# {{1}}, {{2}}, {{3}}... placeholders IN ORDER — each one must
# be a single line (no newlines) per Meta's template rules.
# ==========================================================

def send_whatsapp_template(
    to_wa_id: str,
    template_name: str,
    body_parameters: List[str],
    language_code: str = "en_US",
) -> bool:

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:

        logger.error(
            "WhatsApp credentials missing — cannot send template "
            "message."
        )
        return False

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "template",
        "template": {
            "name": template_name,
            "language": {
                "code": language_code,
            },
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {
                            "type": "text",
                            "text": str(param),
                        }
                        for param in body_parameters
                    ],
                }
            ],
        },
    }

    try:

        with httpx.Client(timeout=15.0) as client:

            response = client.post(
                _messages_url(),
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:

            logger.error(
                "WhatsApp template send failed [%s] "
                "(template=%s, lang=%s, phone_number_id=%s): %s",
                response.status_code,
                template_name,
                language_code,
                WHATSAPP_PHONE_NUMBER_ID,
                response.text,
            )
            return False

        return True

    except httpx.HTTPError as e:

        logger.error("WhatsApp template send request error: %s", e)
        return False


# ==========================================================
# SEND VOICE REPLY
# ==========================================================

def send_whatsapp_audio(
    to_wa_id: str,
    media_id: str,
) -> bool:

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:

        logger.error(
            "WhatsApp credentials missing — cannot send voice reply."
        )
        return False

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "audio",
        "audio": {
            "id": media_id,
        },
    }

    try:

        with httpx.Client(timeout=15.0) as client:

            response = client.post(
                _messages_url(),
                headers=headers,
                json=payload,
            )

        if response.status_code >= 400:

            logger.error(
                "WhatsApp voice reply send failed [%s]: %s",
                response.status_code,
                response.text,
            )
            return False

        return True

    except httpx.HTTPError as e:

        logger.error("WhatsApp voice reply send error: %s", e)
        return False


# ==========================================================
# MARK MESSAGE AS READ (optional, but good UX — shows blue ticks)
# ==========================================================

def mark_message_as_read(message_id: str) -> None:

    if not WHATSAPP_ACCESS_TOKEN or not WHATSAPP_PHONE_NUMBER_ID:
        return

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "status": "read",
        "message_id": message_id,
    }

    try:

        with httpx.Client(timeout=10.0) as client:

            client.post(
                _messages_url(),
                headers=headers,
                json=payload,
            )

    except httpx.HTTPError as e:

        logger.debug("Failed to mark message as read: %s", e)


def normalize_phone_to_wa_id(raw_phone: str) -> Optional[str]:
    """
    "0314xxxxxxx", "+92314xxxxxxx", "0092314xxxxxxx" -> "92314xxxxxxx"
    (digits only, country code first, no leading zero).
    """

    if not raw_phone:
        return None

    digits = re.sub(r"\D", "", str(raw_phone))

    if digits.startswith("0092"):
        digits = "92" + digits[4:]
    elif digits.startswith("092"):
        digits = "92" + digits[3:]
    elif digits.startswith("0") and len(digits) == 11:
        digits = "92" + digits[1:]
    elif not digits.startswith("92"):
        digits = "92" + digits.lstrip("0")

    if len(digits) < 11 or len(digits) > 14:
        return None

    return digits


def wa_session_id(wa_id: str) -> str:
    """
    Namespaces WhatsApp numbers as session_ids so they never collide
    with session_ids coming from any other channel (e.g. a web widget).
    """
    return f"whatsapp:{wa_id}"


# ==========================================================
# DEBUG: bot ke token ko kaun si templates nazar aati hain?
#
# Token kabhi response mein wapas nahi aata.
# ==========================================================

def debug_template_info() -> Dict[str, Any]:

    if not WHATSAPP_ACCESS_TOKEN:
        return {"error": "WHATSAPP_ACCESS_TOKEN missing"}

    headers = {
        "Authorization": f"Bearer {WHATSAPP_ACCESS_TOKEN}",
    }

    result: Dict[str, Any] = {
        "configured_phone_number_id": WHATSAPP_PHONE_NUMBER_ID,
        "api_version": WHATSAPP_API_VERSION,
    }

    try:

        with httpx.Client(timeout=15.0) as client:

            phone_resp = client.get(
                f"{GRAPH_BASE_URL}/{WHATSAPP_API_VERSION}/"
                f"{WHATSAPP_PHONE_NUMBER_ID}",
                headers=headers,
                params={
                    "fields": "display_phone_number,verified_name",
                },
            )

            result["phone_number"] = phone_resp.json()

            if WHATSAPP_BUSINESS_ACCOUNT_ID:

                tpl_resp = client.get(
                    f"{GRAPH_BASE_URL}/{WHATSAPP_API_VERSION}/"
                    f"{WHATSAPP_BUSINESS_ACCOUNT_ID}/message_templates",
                    headers=headers,
                    params={
                        "fields": "name,language,status,category",
                        "limit": 100,
                    },
                )

                result["waba_id_used"] = WHATSAPP_BUSINESS_ACCOUNT_ID
                result["templates"] = tpl_resp.json()

            else:

                result["templates"] = (
                    "WHATSAPP_BUSINESS_ACCOUNT_ID env variable set nahi hai"
                )

    except httpx.HTTPError as e:

        result["error"] = str(e)

    return result