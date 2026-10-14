import re
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List


# ==========================================================
# FOLLOW-UP STAGE SEQUENCE
#
# Only 2 stages now. The review ask is no longer a separate
# stage/message — it's folded directly into the feedback
# thank-you reply (see build_feedback_thank_you below), so we
# never send the customer a 3rd separate message.
# ==========================================================

FOLLOW_UP_STAGE_SEQUENCE = [
    "delivery_confirmation",
    "feedback_request",
]

FOLLOW_UP_DELAY_HOURS = {
    "delivery_confirmation": 2,
    "feedback_request": 48,
}


# ==========================================================
# FEEDBACK EXTRACTION HELPERS
# ==========================================================

RATING_PATTERN = re.compile(
    r"\b([1-5])\s*(?:/\s*5|out of 5|stars?|star)?\b"
)

FEEDBACK_POSITIVE_KEYWORDS = [
    "acha", "achi", "achha", "great", "good", "nice",
    "best", "zabardast", "mast", "perfect", "satisfied",
    "khush", "awesome", "love it", "pasand aya", "pasand aaya",
]

FEEDBACK_NEGATIVE_KEYWORDS = [
    "bura", "buri", "kharab", "bad", "worst", "disappointed",
    "gandi", "problem", "issue", "not good", "pasand nahi",
]


def extract_rating(text: str) -> Optional[int]:

    if not text:
        return None

    match = RATING_PATTERN.search(text)

    if match:

        try:

            value = int(match.group(1))

            if 1 <= value <= 5:
                return value

        except ValueError:
            pass

    text_lower = text.lower()

    if any(k in text_lower for k in FEEDBACK_POSITIVE_KEYWORDS):
        return 5

    if any(k in text_lower for k in FEEDBACK_NEGATIVE_KEYWORDS):
        return 2

    return None


# ==========================================================
# STATE
# ==========================================================

def create_follow_up_state(order_id: str) -> Dict[str, Any]:

    return {
        "order_id": order_id,
        "delivered_at": None,
        "awaiting_stage": None,
        "stages": {
            stage: {
                "sent": False,
                "sent_at": None,
                "response": None,
                "rating": None,
                "responded_at": None,
                "skip": False,
                "skip_reason": None,
            }
            for stage in FOLLOW_UP_STAGE_SEQUENCE
        },
    }


def mark_order_delivered(
    follow_up_state: Dict[str, Any],
    delivered_at: Optional[str] = None,
) -> None:

    if follow_up_state.get("delivered_at"):
        return  # already marked, don't reset the clock

    follow_up_state["delivered_at"] = (
        delivered_at or datetime.now(timezone.utc).isoformat()
    )


def _hours_since(iso_timestamp: str) -> float:

    try:
        then = datetime.fromisoformat(iso_timestamp)
    except (ValueError, TypeError):
        return 0.0

    if then.tzinfo is None:
        then = then.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)

    return (now - then).total_seconds() / 3600.0


# ==========================================================
# DUE-STAGE LOGIC
# ==========================================================

def get_next_due_stage(
    follow_up_state: Dict[str, Any]
) -> Optional[str]:

    if not follow_up_state or not follow_up_state.get("delivered_at"):
        return None

    hours_since_delivery = _hours_since(
        follow_up_state["delivered_at"]
    )

    for stage in FOLLOW_UP_STAGE_SEQUENCE:

        stage_state = follow_up_state["stages"][stage]

        if stage_state["sent"] or stage_state.get("skip"):
            continue

        if hours_since_delivery >= FOLLOW_UP_DELAY_HOURS[stage]:
            return stage

        return None

    return None


def get_due_follow_ups(
    orders_db: Dict[str, Any],
    follow_up_memory: Dict[str, Any],
) -> List[Dict[str, Any]]:

    due = []

    for order_id, order in orders_db.items():

        if order.get("status") != "delivered":
            continue

        state = follow_up_memory.get(order_id)

        if not state or not state.get("delivered_at"):
            continue

        stage = get_next_due_stage(state)

        if stage:

            due.append({
                "order_id": order_id,
                "session_id": order.get("session_id"),
                "stage": stage,
                "message": build_follow_up_message(order, stage),
            })

    return due


# ==========================================================
# MESSAGE TEMPLATES
# ==========================================================

def build_follow_up_message(
    order: Dict[str, Any],
    stage: str,
) -> str:

    product_name = order.get("product") or "aapka order"
    order_id = order.get("order_id", "")

    if stage == "delivery_confirmation":

        return (
            f"Assalam-o-Alaikum! Aapka order {order_id} "
            f"({product_name}) deliver ho chuka hai. Kya sab "
            "kuch sahi salamat mila? 😊"
        )

    if stage == "feedback_request":

        # The review ask now lives in the thank-you reply
        # (build_feedback_thank_you), so this message only
        # asks for a rating/comment.
        return (
            f"Hi! Umeed hai {product_name} pasand aaya hoga. "
            "Aapka experience kaisa raha? 1 se 5 tak rating "
            "de dein, aur agar koi comment ho to woh bhi "
            "bata dein."
        )

    return ""


# ==========================================================
# SEND / RESPOND
# ==========================================================

def mark_stage_sent(
    follow_up_state: Dict[str, Any],
    stage: str,
) -> None:

    stage_state = follow_up_state["stages"].get(stage)

    if not stage_state:
        return

    stage_state["sent"] = True
    stage_state["sent_at"] = datetime.now(timezone.utc).isoformat()

    if stage == "feedback_request":
        follow_up_state["awaiting_stage"] = "feedback_request"


def is_awaiting_feedback(follow_up_state: Optional[Dict[str, Any]]) -> bool:

    if not follow_up_state:
        return False

    if follow_up_state.get("awaiting_stage") != "feedback_request":
        return False

    stage_state = follow_up_state["stages"]["feedback_request"]

    return stage_state["sent"] and stage_state["response"] is None


def record_feedback_response(
    follow_up_state: Dict[str, Any],
    message_text: str,
) -> Dict[str, Any]:

    stage_state = follow_up_state["stages"]["feedback_request"]

    stage_state["response"] = message_text
    stage_state["rating"] = extract_rating(message_text)
    stage_state["responded_at"] = datetime.now(timezone.utc).isoformat()

    follow_up_state["awaiting_stage"] = None

    return stage_state


# ==========================================================
# FEEDBACK THANK-YOU (now also carries the review ask)
#
# Rating >= 4  -> thank you + ask for a public review, right
#                 in the same message (no separate 3rd stage).
# Rating <= 2  -> thank you + apology, no review ask.
# No rating    -> plain thank you, no review ask (we can't
#                 tell if they were happy).
# ==========================================================

def build_feedback_thank_you(rating: Optional[int]) -> str:

    if rating is not None and rating >= 4:

        return (
            "Bohat shukriya! Khushi hui ke aapko pasand aaya. 😊 "
            "Agar thoda sa waqt ho to ek chhota review humein "
            "yahin bhej dein — yeh dusre customers ki madad "
            "karta hai. 🙏"
        )

    if rating is not None and rating <= 2:

        return (
            "Feedback share karne ka shukriya. Maazrat ke saath, "
            "hum is cheez ko improve karne ki koshish karenge. "
            "Agar koi specific issue hai to zaroor bataein."
        )

    return (
        "Bohat shukriya feedback dene ke liye! Aapka experience "
        "hamare liye ahem hai."
    )