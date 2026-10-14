import os
import html
import logging
from typing import Optional

import httpx


# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("alerts")


# ==========================================================
# ENVIRONMENT
#
# RESEND_API_KEY   -> from resend.com/api-keys
# ALERT_EMAIL_TO   -> where alerts should be delivered
#                     (your own inbox)
# ALERT_EMAIL_FROM -> optional. Defaults to Resend's shared
#                     sandbox sender, which works without any
#                     domain verification as long as
#                     ALERT_EMAIL_TO is the same address you
#                     signed up to Resend with.
#
# NOTE: raw SMTP (smtplib) does NOT work on Railway — outbound
# SMTP ports are blocked by the platform (Errno 101 Network
# unreachable), regardless of credentials. Resend's API runs
# over normal HTTPS, which is not blocked.
# ==========================================================

RESEND_API_KEY = os.getenv("RESEND_API_KEY", "")

ALERT_EMAIL_TO = os.getenv(
    "ALERT_EMAIL_TO",
    "",
)

ALERT_EMAIL_FROM = os.getenv(
    "ALERT_EMAIL_FROM",
    "onboarding@resend.dev",
)

RESEND_API_URL = "https://api.resend.com/emails"


# ==========================================================
# CONFIG CHECK
# ==========================================================

def is_configured() -> bool:

    return bool(
        RESEND_API_KEY
        and ALERT_EMAIL_TO
    )


# ==========================================================
# SEND ESCALATION ALERT EMAIL
# ==========================================================

def send_escalation_alert(
    session_id: str,
    issue_type: Optional[str],
    escalation_reason: Optional[str],
    last_customer_message: str,
    order_reference: Optional[str] = None,
) -> bool:

    if not is_configured():

        logger.warning(
            "Email alerts not configured — set RESEND_API_KEY "
            "and ALERT_EMAIL_TO to enable escalation alert "
            "emails."
        )

        return False

    subject = (
        f"\u26a0\ufe0f RH Clothing Store — Customer needs human help "
        f"({issue_type or 'unclear'})"
    )

    body_lines = [
        "A customer conversation was just escalated and needs "
        "a human to step in.",
        "",
        f"Session: {session_id}",
        f"Issue type: {issue_type or 'unclear'}",
        f"Escalation reason: {escalation_reason or 'n/a'}",
    ]

    if order_reference:

        body_lines.append(
            f"Order reference: {order_reference}"
        )

    body_lines.append("")
    body_lines.append(
        "Customer's last message:"
    )
    body_lines.append(
        f'"{last_customer_message}"'
    )
    body_lines.append("")
    body_lines.append(
        "Open the dashboard's Support tab to see the full "
        "conversation and reply."
    )

    body_text = "\n".join(body_lines)

    body_html = (
        "<p>"
        + "</p><p>".join(
            html.escape(line) if line else "&nbsp;"
            for line in body_lines
        )
        + "</p>"
    )

    payload = {
        "from": ALERT_EMAIL_FROM,
        "to": [ALERT_EMAIL_TO],
        "subject": subject,
        "text": body_text,
        "html": body_html,
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:

        response = httpx.post(
            RESEND_API_URL,
            headers=headers,
            json=payload,
            timeout=15.0,
        )

        if response.status_code >= 400:

            logger.error(
                "Failed to send escalation alert email "
                "[%s]: %s",
                response.status_code,
                response.text,
            )

            return False

        logger.info(
            "Escalation alert email sent for session %s",
            session_id,
        )

        return True

    except httpx.HTTPError as e:

        logger.error(
            "Failed to send escalation alert email: %s",
            e,
        )

        return False


# ==========================================================
# SEND NEW ORDER ALERT EMAIL
#
# Fired every time a NEW order is confirmed by the backend
# (see main.py -> handle_incoming_message). If the same
# customer session already has an earlier order in orders_db,
# this is treated as a REPEAT order and the subject line is
# changed accordingly, so the business owner can tell at a
# glance from their inbox whether this is a brand-new
# customer order or someone ordering again.
# ==========================================================

def send_order_alert(
    order: dict,
    is_repeat: bool = False,
) -> bool:

    if not is_configured():

        logger.warning(
            "Email alerts not configured — set RESEND_API_KEY "
            "and ALERT_EMAIL_TO to enable order alert emails."
        )

        return False

    customer_name = order.get("name") or "Customer"
    order_id = order.get("order_id") or "N/A"

    if is_repeat:

        subject = (
            f"\U0001F501 Repeat order se {customer_name} — "
            f"{order_id}"
        )

    else:

        subject = (
            f"\U0001F6CD\ufe0f New order — {order_id} "
            f"({customer_name})"
        )

    body_lines = [
        (
            f"{customer_name} ne dobara order kiya hai."
            if is_repeat
            else f"{customer_name} ka naya order aya hai."
        ),
        "",
        f"Order ID: {order_id}",
        f"Customer: {customer_name}",
        f"Phone: {order.get('phone') or 'n/a'}",
        f"Product: {order.get('product') or 'n/a'}",
        f"Size: {order.get('size') or 'n/a'}",
        f"Color: {order.get('color') or 'n/a'}",
        f"Quantity: {order.get('quantity') or 'n/a'}",
        f"City: {order.get('city') or 'n/a'}",
        f"Address: {order.get('address') or 'n/a'}",
        (
            "Payment method: "
            f"{order.get('payment_method') or 'n/a'}"
        ),
        (
            "Delivery estimate: "
            f"{order.get('delivery_estimate') or 'n/a'}"
        ),
        "",
        "Open the dashboard's Orders tab to see full details.",
    ]

    body_text = "\n".join(body_lines)

    body_html = (
        "<p>"
        + "</p><p>".join(
            html.escape(line) if line else "&nbsp;"
            for line in body_lines
        )
        + "</p>"
    )

    payload = {
        "from": ALERT_EMAIL_FROM,
        "to": [ALERT_EMAIL_TO],
        "subject": subject,
        "text": body_text,
        "html": body_html,
    }

    headers = {
        "Authorization": f"Bearer {RESEND_API_KEY}",
        "Content-Type": "application/json",
    }

    try:

        response = httpx.post(
            RESEND_API_URL,
            headers=headers,
            json=payload,
            timeout=15.0,
        )

        if response.status_code >= 400:

            logger.error(
                "Failed to send order alert email [%s]: %s",
                response.status_code,
                response.text,
            )

            return False

        logger.info(
            "Order alert email sent for order %s (repeat=%s)",
            order_id,
            is_repeat,
        )

        return True

    except httpx.HTTPError as e:

        logger.error(
            "Failed to send order alert email: %s",
            e,
        )

        return False