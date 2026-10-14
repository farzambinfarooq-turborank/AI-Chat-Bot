import os
import json
import logging
from typing import Dict, Any, List, Optional

import httpx

from fastapi import FastAPI, BackgroundTasks, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from datetime import datetime, timezone

from .ai_agent import get_ai_reply
from .dashboard_agent import get_dashboard_analytics, get_daily_snapshot
from .support_agent import create_support_state
from .order_agent import get_order_decision
from .follow_up_agent import (
    FOLLOW_UP_STAGE_SEQUENCE,
    create_follow_up_state,
    mark_order_delivered,
    get_due_follow_ups,
    get_next_due_stage,
    build_follow_up_message,
    mark_stage_sent,
    is_awaiting_feedback,
    record_feedback_response,
    build_feedback_thank_you,
)
from .whatsapp_agent import (
    verify_webhook_challenge,
    extract_incoming_text_message,
    send_whatsapp_text,
    mark_message_as_read,
    wa_session_id,
)
from . import whatsapp_agent
from . import voice_agent
from . import db
from . import alerts
from . import security
from .legal import router as legal_router

import re
from fastapi import HTTPException, Header
from pydantic import Field
from .business_data import BUSINESS_DATA
from .order_agent import (
    generate_order_id,
    get_product_by_id,
    get_delivery_estimate,
    extract_phone,
)


# ==========================================================
# FASTAPI APP
# ==========================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s %(name)s: %(message)s",
)

logger = logging.getLogger("main")

app = FastAPI(
    title="AI Customer Representative",
    version="0.9.0",
    docs_url=None,      # /docs, /redoc, /openapi.json band — API map public nahi
    redoc_url=None,
    openapi_url=None,
)


# ==========================================================
# CORS
# ==========================================================
app.include_router(legal_router)
app.include_router(security.router)

# Order matters: the LAST middleware added is the OUTERMOST. CORS must wrap
# the security middleware so even 401/429 replies carry CORS headers.
app.add_middleware(security.SecurityMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=security.allowed_origins(),
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


# ==========================================================
# CONFIG
# ==========================================================

MAX_STORED_MESSAGES = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ==========================================================
# REQUEST MODELS
# ==========================================================

class ChatRequest(BaseModel):
    session_id: str
    message: str


class OrderStatusUpdate(BaseModel):
    status: str


class FeedbackUpdate(BaseModel):
    message: str


class HumanReply(BaseModel):
    message: str


# ==========================================================
# MEMORY / DATABASE
#
# Currently in-memory storage.
# Production can replace these with a real database.
# ==========================================================

conversation_memory: Dict[
    str,
    List[Dict[str, Any]]
] = {}

order_memory: Dict[
    str,
    Dict[str, Any]
] = {}

support_memory: Dict[
    str,
    Dict[str, Any]
] = {}

orders_db: Dict[
    str,
    Dict[str, Any]
] = {}

follow_up_memory: Dict[
    str,
    Dict[str, Any]
] = {}


# ==========================================================
# STARTUP — LOAD PERSISTED DATA
#
# Runs once when the server boots (including after every
# Railway redeploy). Repopulates all the in-memory dicts
# above from Postgres, so conversations/orders/support state
# survive a redeploy instead of vanishing. If DATABASE_URL
# isn't set, these all safely return empty dicts and the app
# behaves exactly as before (pure in-memory, non-persistent).
# ==========================================================

# ----------------------------------------------------------
# WEBSITE ORDERS — opt-out list (STOP likhne wale) aur optional
# template ka naam. WEBSITE_TEMPLATE_NAME khali rakhein jab tak
# Meta template approve na ho.
# ----------------------------------------------------------

wa_opt_out: Dict[str, Any] = {}

# Sirf website-api (alag Railway service) yeh secret bhej kar order de sakti hai
WEBSITE_API_SECRET = os.getenv("WEBSITE_API_SECRET", "")

WEBSITE_TEMPLATE_NAME = os.getenv("WEBSITE_TEMPLATE_NAME", "")

# Meta mein template ki language jo hai wohi code yahan chahiye.
# Template "English" hai to "en", "English (US)" hai to "en_US".
WEBSITE_TEMPLATE_LANG = os.getenv("WEBSITE_TEMPLATE_LANG", "en")


@app.on_event("startup")
def load_persisted_data() -> None:

    db.init_db()

    security.log_config_warnings()

    conversation_memory.update(
        db.load_all("conversation_memory")
    )

    order_memory.update(
        db.load_all("order_memory")
    )

    support_memory.update(
        db.load_all("support_memory")
    )

    orders_db.update(
        db.load_all("orders_db")
    )

    follow_up_memory.update(
        db.load_all("follow_up_memory")
    )

    wa_opt_out.update(
        db.load_all("wa_opt_out")
    )



VALID_ORDER_STATUSES = [
    "pending_confirmation",
    "confirmed",
    "processing",
    "shipped",
    "out_for_delivery",
    "delivered",
    "cancelled",
]


# ==========================================================
# AUTO STATUS PROGRESSION
#
# Business owner asked: an order that's still sitting at
# "confirmed" should automatically flip to "out_for_delivery"
# once ORDER_AUTO_ADVANCE_DAYS days have passed, without
# anyone manually updating it. This runs lazily (checked
# whenever orders are read) rather than needing a separate
# cron/scheduler process.
# ==========================================================

ORDER_AUTO_ADVANCE_DAYS = int(
    os.getenv("ORDER_AUTO_ADVANCE_DAYS", "4")
)


def _auto_progress_order_statuses() -> None:

    now = datetime.now(timezone.utc)

    for order_id, order in orders_db.items():

        if order.get("status") != "confirmed":
            continue

        created_at = order.get("created_at")

        if not created_at:
            continue

        try:
            created_dt = datetime.fromisoformat(created_at)
        except ValueError:
            continue

        if created_dt.tzinfo is None:
            created_dt = created_dt.replace(tzinfo=timezone.utc)

        days_elapsed = (
            (now - created_dt).total_seconds() / 86400
        )

        if days_elapsed < ORDER_AUTO_ADVANCE_DAYS:
            continue

        order["status"] = "out_for_delivery"
        order["updated_at"] = now.isoformat()

        db.save(
            "orders_db",
            order_id,
            order,
        )

        session_id = order.get("session_id")

        if (
            session_id
            and session_id in order_memory
            and order_memory[session_id].get("order_id") == order_id
        ):

            order_memory[session_id]["status"] = "out_for_delivery"

            db.save(
                "order_memory",
                session_id,
                order_memory[session_id],
            )


# ==========================================================
# DEFAULT ORDER STATE
# ==========================================================

def create_order_state() -> Dict[str, Any]:

    return {
        "product": None,
        "product_id": None,
        "size": None,
        "color": None,
        "quantity": None,
        "name": None,
        "phone": None,
        "city": None,
        "address": None,
        "payment_method": None,
        "stage": "discovery",
        "buying_intent": False,
        "status": "collecting",
        "order_id": None,
        "last_asked_field": None,
    }


# ==========================================================
# HOME
# ==========================================================

@app.get("/")
def home():

    return {
        "status": "online",
        "message": "AI Customer Representative is running",
        "version": "0.9.0",
    }


# ==========================================================
# ==========================================================
# PHASE 8 — SHARED MESSAGE-HANDLING BRAIN
#
# This is the exact same logic that used to live directly inside
# the /chat endpoint. It has been pulled out into its own function
# so that BOTH the web /chat endpoint AND the WhatsApp webhook can
# call the same brain, on the same session/order/support memory.
# ==========================================================
# ==========================================================

def handle_incoming_message(
    session_id: str,
    message: str,
) -> Dict[str, Any]:

    message = (message or "").strip()

    if not message:

        return {
            "session_id": session_id,
            "reply": "Ji, aap apna question bata dein.",
            "support": support_memory.get(
                session_id,
                create_support_state(),
            ),
            "order": order_memory.get(
                session_id,
                create_order_state(),
            ),
        }

    # ------------------------------------------------------
    # CREATE SESSION
    # ------------------------------------------------------

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []

    if session_id not in order_memory:
        order_memory[session_id] = create_order_state()

    if session_id not in support_memory:
        support_memory[session_id] = create_support_state()


    # ------------------------------------------------------
    # STOP / opt-out
    # ------------------------------------------------------

    if message.strip().lower() in ("stop", "unsubscribe", "band karo"):

        wa_opt_out[session_id] = {"at": _now_iso()}
        db.save("wa_opt_out", session_id, wa_opt_out[session_id])

        reply = (
            "Theek hai, ab hum aapko koi automatic message nahi "
            "bhejenge. Zaroorat ho to yahan message kar dein."
        )

        conversation_memory[session_id].append(
            {"role": "user", "content": message, "timestamp": _now_iso()}
        )
        conversation_memory[session_id].append(
            {"role": "assistant", "content": reply, "timestamp": _now_iso()}
        )
        db.save("conversation_memory", session_id, conversation_memory[session_id])

        return {
            "session_id": session_id,
            "reply": reply,
            "support": support_memory[session_id],
            "order": order_memory[session_id],
        }

    # ------------------------------------------------------
    # Website order confirmation ("Order ORD-XXXXXXXX confirm")
    # ------------------------------------------------------

    # ------------------------------------------------------
    # Website order confirm/cancel via WhatsApp quick-reply
    # buttons (CONFIRM_ORDER / CANCEL_ORDER)
    # ------------------------------------------------------

    if message in ("__BTN_CONFIRM_ORDER__", "__BTN_CANCEL_ORDER__"):

        pending_order = None

        for candidate in sorted(
            orders_db.values(),
            key=lambda o: o.get("created_at", ""),
            reverse=True,
        ):

            if (
                candidate.get("session_id") == session_id
                and candidate.get("source") == "website"
                and candidate.get("status") == "processing"
                and not candidate.get("customer_confirmed")
            ):

                pending_order = candidate
                break

        if not pending_order:

            reply = (
                "Is waqt koi pending order confirmation nahi mila. "
                "Agar aapne website se order kiya hai, barae meherbani "
                "order ID hamein bhej dein."
            )

        elif message == "__BTN_CONFIRM_ORDER__":

            pending_order["status"] = "confirmed"
            pending_order["customer_confirmed"] = True
            pending_order["updated_at"] = _now_iso()
            db.save("orders_db", pending_order["order_id"], pending_order)

            reply = (
                f"Shukriya {pending_order.get('name')}! Aapka order "
                f"{pending_order['order_id']} confirm ho gaya hai. "
                f"Delivery {pending_order.get('delivery_estimate')} "
                "mein hogi. \u2705"
            )

        else:

            pending_order["status"] = "cancelled"
            pending_order["updated_at"] = _now_iso()
            db.save("orders_db", pending_order["order_id"], pending_order)

            reply = (
                f"Theek hai, order {pending_order['order_id']} cancel "
                "kar diya gaya hai. Agar dobara order karna ho to "
                "humein bata dein."
            )

        conversation_memory[session_id].append(
            {"role": "user", "content": message, "timestamp": _now_iso()}
        )
        conversation_memory[session_id].append(
            {"role": "assistant", "content": reply, "timestamp": _now_iso()}
        )
        db.save(
            "conversation_memory",
            session_id,
            conversation_memory[session_id],
        )

        return {
            "session_id": session_id,
            "reply": reply,
            "support": support_memory[session_id],
            "order": order_memory[session_id],
        }

    order_id_match = re.search(r"\bORD-[A-Z0-9]{8}\b", message.upper())

    if order_id_match:

        site_order = orders_db.get(order_id_match.group(0))

        # Sirf wahi number confirm kar sakta hai jis ne order diya tha
        if (
            site_order
            and site_order.get("source") == "website"
            and site_order.get("session_id") == session_id
        ):

            site_order["customer_confirmed"] = True

            # Sirf "processing" order hi confirmed hoga; agar owner order
            # ko shipped/delivered kar chuka hai to status peeche nahi jayega.
            if site_order.get("status") == "processing":
                site_order["status"] = "confirmed"

            site_order["updated_at"] = _now_iso()
            db.save("orders_db", site_order["order_id"], site_order)

            reply = (
                f"Shukriya {site_order.get('name')}! Aapka order "
                f"{site_order['order_id']} confirm ho gaya hai. "
                f"Delivery {site_order.get('delivery_estimate')} mein "
                "hogi. \u2705"
            )

            conversation_memory[session_id].append(
                {"role": "user", "content": message, "timestamp": _now_iso()}
            )
            conversation_memory[session_id].append(
                {"role": "assistant", "content": reply, "timestamp": _now_iso()}
            )
            db.save("conversation_memory", session_id, conversation_memory[session_id])

            return {
                "session_id": session_id,
                "reply": reply,
                "support": support_memory[session_id],
                "order": order_memory[session_id],
            }

    # ------------------------------------------------------
    # FOLLOW-UP FEEDBACK CAPTURE
    # ------------------------------------------------------

    existing_order_id = (
        order_memory[session_id].get("order_id")
    )

    pending_follow_up_state = (
        follow_up_memory.get(existing_order_id)
        if existing_order_id
        else None
    )

    if is_awaiting_feedback(
        pending_follow_up_state
    ):

        conversation_memory[session_id].append({
            "role": "user",
            "content": message,
            "timestamp": _now_iso(),
        })

        stage_result = record_feedback_response(
            pending_follow_up_state,
            message,
        )

        reply = build_feedback_thank_you(
            stage_result.get("rating")
        )

        conversation_memory[session_id].append({
            "role": "assistant",
            "content": reply,
            "timestamp": _now_iso(),
        })

        if (
            len(conversation_memory[session_id])
            > MAX_STORED_MESSAGES
        ):

            conversation_memory[session_id] = (
                conversation_memory[session_id][
                    -MAX_STORED_MESSAGES:
                ]
            )

        db.save(
            "conversation_memory",
            session_id,
            conversation_memory[session_id],
        )

        db.save(
            "follow_up_memory",
            existing_order_id,
            pending_follow_up_state,
        )

        return {
            "session_id": session_id,
            "reply": reply,
            "support": support_memory[session_id],
            "order": order_memory[session_id],
        }

    # ------------------------------------------------------
    # SAVE USER MESSAGE
    # ------------------------------------------------------

    conversation_memory[session_id].append({
        "role": "user",
        "content": message,
        "timestamp": _now_iso(),
    })

    # ------------------------------------------------------
    # ORDER DECISION
    # ------------------------------------------------------

    order_decision = get_order_decision(
        conversation_memory[session_id],
        order_memory[session_id],
    )

    new_order_record = (
        order_decision.get(
            "new_order_record"
        )
    )

    # ------------------------------------------------------
    # SAVE NEW ORDER
    # ------------------------------------------------------

    if new_order_record:

        now = (
            datetime.now(timezone.utc)
            .isoformat()
        )

        new_order_record["session_id"] = (
            session_id
        )

        new_order_record["created_at"] = now
        new_order_record["updated_at"] = now

        # ------------------------------------------------------
        # REPEAT-CUSTOMER CHECK
        #
        # Checked BEFORE this order is added to orders_db below —
        # if any OTHER order already exists for this same
        # session_id, this is a repeat order from an existing
        # customer, not their first.
        # ------------------------------------------------------

        is_repeat_order = any(
            existing_order.get("session_id") == session_id
            for existing_order in orders_db.values()
        )

        orders_db[
            new_order_record["order_id"]
        ] = new_order_record

        follow_up_memory[
            new_order_record["order_id"]
        ] = create_follow_up_state(
            new_order_record["order_id"]
        )

        db.save(
            "orders_db",
            new_order_record["order_id"],
            new_order_record,
        )

        db.save(
            "follow_up_memory",
            new_order_record["order_id"],
            follow_up_memory[
                new_order_record["order_id"]
            ],
        )

        # ------------------------------------------------------
        # ORDER ALERT EMAIL
        #
        # Fired for every confirmed order — new or repeat. Runs
        # synchronously; if Resend is slow this adds a small delay
        # to the reply, but keeps this endpoint dependency-free
        # (no background task infra needed). If that delay becomes
        # noticeable in testing, we can move this to a
        # BackgroundTasks call like the WhatsApp webhook does.
        # ------------------------------------------------------

        alerts.send_order_alert(
            new_order_record,
            is_repeat=is_repeat_order,
        )

    # ------------------------------------------------------
    # GET AI RESPONSE
    # ------------------------------------------------------

    was_escalated_before = support_memory[
        session_id
    ].get(
        "escalated",
        False,
    )

    reply = get_ai_reply(
        conversation_memory[session_id],
        support_memory[session_id],
        order_decision,
    )

    # ------------------------------------------------------
    # ESCALATION ALERT
    #
    # get_ai_reply() internally runs the support decision
    # logic (via build_support_prompt_text -> get_support_
    # decision), which mutates support_memory[session_id] in
    # place. By comparing before/after, we can detect the
    # exact turn a session newly becomes escalated and fire
    # a single alert email — without calling the support
    # decision logic a second time (which would double-count
    # the complaint counter).
    # ------------------------------------------------------

    is_escalated_now = support_memory[
        session_id
    ].get(
        "escalated",
        False,
    )

    if is_escalated_now and not was_escalated_before:

        alerts.send_escalation_alert(
            session_id=session_id,
            issue_type=support_memory[session_id].get(
                "issue_type"
            ),
            escalation_reason=support_memory[session_id].get(
                "escalation_reason"
            ),
            last_customer_message=message,
            order_reference=support_memory[session_id].get(
                "order_reference"
            ),
        )

    # ------------------------------------------------------
    # SAVE AI RESPONSE
    # ------------------------------------------------------

    conversation_memory[session_id].append({
        "role": "assistant",
        "content": reply,
        "timestamp": _now_iso(),
    })

    # ------------------------------------------------------
    # LIMIT MEMORY
    # ------------------------------------------------------

    if (
        len(conversation_memory[session_id])
        > MAX_STORED_MESSAGES
    ):

        conversation_memory[session_id] = (
            conversation_memory[session_id][
                -MAX_STORED_MESSAGES:
            ]
        )

    # ------------------------------------------------------
    # PERSIST TO DATABASE
    # ------------------------------------------------------

    db.save(
        "conversation_memory",
        session_id,
        conversation_memory[session_id],
    )

    db.save(
        "order_memory",
        session_id,
        order_memory[session_id],
    )

    db.save(
        "support_memory",
        session_id,
        support_memory[session_id],
    )

    # ------------------------------------------------------
    # RESPONSE
    # ------------------------------------------------------

    return {
        "session_id": session_id,
        "reply": reply,
        "support": support_memory[session_id],
        "order": order_memory[session_id],
    }


# ==========================================================
# CHAT (WEB)
# ==========================================================

@app.post("/chat")
def chat(request: ChatRequest):

    return handle_incoming_message(
        request.session_id,
        request.message,
    )


# ==========================================================
# GET SESSION
# ==========================================================

@app.get("/session/{session_id}")
def get_session(session_id: str):

    return {
        "session_id": session_id,
        "conversation": conversation_memory.get(
            session_id,
            []
        ),
        "order": order_memory.get(
            session_id,
            create_order_state()
        ),
        "support": support_memory.get(
            session_id,
            create_support_state()
        ),
    }


# ==========================================================
# RESET SESSION
# ==========================================================

@app.delete("/session/{session_id}")
def reset_session(session_id: str):

    conversation_memory.pop(
        session_id,
        None,
    )

    order_memory.pop(
        session_id,
        None,
    )

    support_memory.pop(
        session_id,
        None,
    )

    db.delete("conversation_memory", session_id)
    db.delete("order_memory", session_id)
    db.delete("support_memory", session_id)

    return {
        "session_id": session_id,
        "status": "reset",
    }


# ==========================================================
# GET SUPPORT STATE
# ==========================================================

@app.get("/session/{session_id}/support")
def get_support_state(session_id: str):

    return {
        "session_id": session_id,
        "support": support_memory.get(
            session_id,
            create_support_state()
        ),
    }


# ==========================================================
# LIST ESCALATIONS
# ==========================================================

@app.get("/escalations")
def list_escalations():

    escalated_sessions = []

    for (
        session_id,
        state
    ) in support_memory.items():

        if state.get("escalated"):

            escalated_sessions.append({
                "session_id": session_id,
                "issue_type": state.get(
                    "issue_type"
                ),
                "escalation_reason": state.get(
                    "escalation_reason"
                ),
                "complaint_count": state.get(
                    "complaint_count"
                ),
                "order_reference": state.get(
                    "order_reference"
                ),
            })

    return {
        "count": len(escalated_sessions),
        "escalations": escalated_sessions,
    }


# ==========================================================
# RESOLVE ESCALATION
# ==========================================================

@app.post(
    "/session/{session_id}/support/resolve"
)
def resolve_support(session_id: str):

    if session_id not in support_memory:

        support_memory[
            session_id
        ] = create_support_state()

    support_memory[session_id][
        "escalated"
    ] = False

    support_memory[session_id][
        "escalation_reason"
    ] = None

    support_memory[session_id][
        "complaint_count"
    ] = 0

    db.save(
        "support_memory",
        session_id,
        support_memory[session_id],
    )

    return {
        "session_id": session_id,
        "status": "resolved",
        "support": support_memory[
            session_id
        ],
    }


# ==========================================================
# MANUAL HUMAN REPLY
#
# Lets a real staff member reply directly to a customer for
# an escalated (or any) conversation — bypasses the AI
# entirely. If the session is a WhatsApp session, the message
# is also sent live over WhatsApp via the same Cloud API
# credentials the bot uses. The message is stored in the
# conversation history as an assistant turn so the AI has
# full context if it ever picks the conversation back up.
# ==========================================================

@app.post("/session/{session_id}/reply")
def send_human_reply(
    session_id: str,
    reply: HumanReply,
):

    message = (
        reply.message or ""
    ).strip()

    if not message:

        return {
            "session_id": session_id,
            "sent": False,
            "message": "Reply message cannot be empty.",
        }

    if session_id not in conversation_memory:
        conversation_memory[session_id] = []

    conversation_memory[session_id].append({
        "role": "assistant",
        "content": message,
        "timestamp": _now_iso(),
    })

    db.save(
        "conversation_memory",
        session_id,
        conversation_memory[session_id],
    )

    sent_over_whatsapp = False

    if session_id.startswith("whatsapp:"):

        wa_id = session_id.split(
            "whatsapp:",
            1,
        )[1]

        sent_over_whatsapp = bool(
            send_whatsapp_text(
                wa_id,
                message,
            )
        )

    return {
        "session_id": session_id,
        "sent": True,
        "sent_over_whatsapp": sent_over_whatsapp,
    }


# ==========================================================
# GET CURRENT ORDER FOR SESSION
# ==========================================================

@app.get("/session/{session_id}/order")
def get_session_order(session_id: str):

    return {
        "session_id": session_id,
        "order": order_memory.get(
            session_id,
            create_order_state()
        ),
    }


# ==========================================================
# GET SPECIFIC ORDER
# ==========================================================

@app.get("/order/{order_id}")
def get_order(order_id: str):

    _auto_progress_order_statuses()

    order = orders_db.get(order_id)

    if not order:

        return {
            "order_id": order_id,
            "found": False,
            "message": (
                "No order found with this ID."
            ),
        }

    return {
        "found": True,
        "order": order,
    }


# ==========================================================
# DELETE ORDER
# ==========================================================

@app.delete("/order/{order_id}")
def delete_order(order_id: str):

    order = orders_db.pop(order_id, None)

    if not order:

        return {
            "order_id": order_id,
            "deleted": False,
            "message": (
                "No order found with this ID."
            ),
        }

    follow_up_memory.pop(order_id, None)

    db.delete("orders_db", order_id)
    db.delete("follow_up_memory", order_id)

    # If the customer's live session was still pointing at this
    # order, clear that reference so a new order can be started
    # cleanly instead of referring to an order that no longer
    # exists.
    session_id = order.get("session_id")

    if (
        session_id
        and session_id in order_memory
        and order_memory[session_id].get("order_id") == order_id
    ):

        order_memory[session_id]["order_id"] = None
        order_memory[session_id]["status"] = "collecting"
        order_memory[session_id]["stage"] = "collecting"

        db.save(
            "order_memory",
            session_id,
            order_memory[session_id],
        )

    return {
        "order_id": order_id,
        "deleted": True,
    }


# ==========================================================
# LIST ALL ORDERS
# ==========================================================

@app.get("/orders")
def list_orders():

    _auto_progress_order_statuses()

    orders = list(
        orders_db.values()
    )

    orders.sort(
        key=lambda order: order.get(
            "created_at",
            ""
        ),
        reverse=True,
    )

    return {
        "count": len(orders),
        "orders": orders,
    }


# ==========================================================
# UPDATE ORDER STATUS
# ==========================================================

@app.post("/order/{order_id}/status")
def update_order_status(
    order_id: str,
    update: OrderStatusUpdate,
):

    if order_id not in orders_db:

        return {
            "order_id": order_id,
            "updated": False,
            "message": (
                "No order found with this ID."
            ),
        }

    if (
        update.status
        not in VALID_ORDER_STATUSES
    ):

        return {
            "order_id": order_id,
            "updated": False,
            "message": (
                "Invalid status. Valid values: "
                + ", ".join(
                    VALID_ORDER_STATUSES
                )
            ),
        }

    orders_db[order_id][
        "status"
    ] = update.status

    orders_db[order_id][
        "updated_at"
    ] = (
        datetime.now(timezone.utc)
        .isoformat()
    )

    # ------------------------------------------------------
    # SYNC CUSTOMER SESSION
    # ------------------------------------------------------

    session_id = orders_db[
        order_id
    ].get("session_id")

    if (
        session_id
        and session_id in order_memory
        and order_memory[session_id].get(
            "order_id"
        ) == order_id
    ):

        order_memory[session_id][
            "status"
        ] = update.status

    # ------------------------------------------------------
    # START FOLLOW-UP CLOCK
    # ------------------------------------------------------

    if update.status == "delivered":

        if order_id not in follow_up_memory:

            follow_up_memory[
                order_id
            ] = create_follow_up_state(
                order_id
            )

        mark_order_delivered(
            follow_up_memory[order_id]
        )

        db.save(
            "follow_up_memory",
            order_id,
            follow_up_memory[order_id],
        )

    db.save(
        "orders_db",
        order_id,
        orders_db[order_id],
    )

    if (
        session_id
        and session_id in order_memory
    ):

        db.save(
            "order_memory",
            session_id,
            order_memory[session_id],
        )

    return {
        "order_id": order_id,
        "updated": True,
        "order": orders_db[order_id],
    }


# ==========================================================
# PHASE 6 — FOLLOW-UPS
# ==========================================================

@app.get("/follow-ups")
def list_follow_ups():

    return {
        "count": len(
            follow_up_memory
        ),
        "follow_ups": list(
            follow_up_memory.values()
        ),
    }


@app.get("/follow-ups/{order_id}")
def get_follow_up(order_id: str):

    state = follow_up_memory.get(
        order_id
    )

    if not state:

        return {
            "order_id": order_id,
            "found": False,
            "message": (
                "No follow-up state for this order."
            ),
        }

    return {
        "found": True,
        "follow_up": state,
    }


@app.get("/follow-ups/due/list")
def list_due_follow_ups():

    due = get_due_follow_ups(
        orders_db,
        follow_up_memory,
    )

    return {
        "count": len(due),
        "due": due,
    }


# ==========================================================
# INTERNAL FOLLOW-UP SENDER
# ==========================================================

def _send_follow_up(
    order_id: str,
    stage: str,
) -> Dict[str, Any]:

    order = orders_db.get(
        order_id
    )

    state = follow_up_memory.get(
        order_id
    )

    if not order or not state:

        return {
            "order_id": order_id,
            "sent": False,
            "message": (
                "Order or follow-up state not found."
            ),
        }

    message = build_follow_up_message(
        order,
        stage,
    )

    session_id = order.get(
        "session_id"
    )

    if session_id:

        if (
            session_id
            not in conversation_memory
        ):

            conversation_memory[
                session_id
            ] = []

        conversation_memory[
            session_id
        ].append({
            "role": "assistant",
            "content": message,
            "timestamp": _now_iso(),
        })

        db.save(
            "conversation_memory",
            session_id,
            conversation_memory[session_id],
        )

        # ----------------------------------------------
        # If this session belongs to a WhatsApp customer,
        # also push the follow-up out over WhatsApp itself
        # (not just into in-memory conversation history).
        # ----------------------------------------------

        if session_id.startswith("whatsapp:"):

            wa_id = session_id.split(
                "whatsapp:",
                1,
            )[1]

            send_whatsapp_text(
                wa_id,
                message,
            )

    mark_stage_sent(
        state,
        stage,
    )

    db.save(
        "follow_up_memory",
        order_id,
        state,
    )

    return {
        "order_id": order_id,
        "stage": stage,
        "sent": True,
        "message": message,
    }


# ==========================================================
# SEND FOLLOW-UP MANUALLY
# ==========================================================

@app.post(
    "/follow-ups/{order_id}/send/{stage}"
)
def send_follow_up(
    order_id: str,
    stage: str,
):

    if (
        stage
        not in FOLLOW_UP_STAGE_SEQUENCE
    ):

        return {
            "order_id": order_id,
            "sent": False,
            "message": (
                "Invalid stage. Valid values: "
                + ", ".join(
                    FOLLOW_UP_STAGE_SEQUENCE
                )
            ),
        }

    return _send_follow_up(
        order_id,
        stage,
    )


# ==========================================================
# RUN ALL DUE FOLLOW-UPS
# ==========================================================

@app.post("/follow-ups/run-due")
def run_due_follow_ups():

    due = get_due_follow_ups(
        orders_db,
        follow_up_memory,
    )

    sent = []

    for item in due:

        result = _send_follow_up(
            item["order_id"],
            item["stage"],
        )

        sent.append(result)

    return {
        "count": len(sent),
        "sent": sent,
    }


# ==========================================================
# SUBMIT FEEDBACK
# ==========================================================

@app.post(
    "/follow-ups/{order_id}/feedback"
)
def submit_feedback(
    order_id: str,
    update: FeedbackUpdate,
):

    state = follow_up_memory.get(
        order_id
    )

    if not state:

        return {
            "order_id": order_id,
            "recorded": False,
            "message": (
                "No follow-up state for this order."
            ),
        }

    stage_result = (
        record_feedback_response(
            state,
            update.message,
        )
    )

    db.save(
        "follow_up_memory",
        order_id,
        state,
    )

    return {
        "order_id": order_id,
        "recorded": True,
        "feedback": stage_result,
    }


# ==========================================================
# ==========================================================
# PHASE 7 — DASHBOARD
# ==========================================================
# ==========================================================


# ==========================================================
# DASHBOARD ANALYTICS
# ==========================================================

@app.get("/dashboard/analytics")
def dashboard_analytics():

    _auto_progress_order_statuses()

    return get_dashboard_analytics(
        conversation_memory=conversation_memory,
        orders_db=orders_db,
        support_memory=support_memory,
        follow_up_memory=follow_up_memory,
    )


# ==========================================================
# DAILY SNAPSHOT
#
# ?date=YYYY-MM-DD (defaults to today, UTC). Returns how many
# conversations were active and how many orders were placed
# on that specific date.
# ==========================================================

@app.get("/dashboard/daily")
def dashboard_daily(
    date: Optional[str] = None,
):

    target_date = date or (
        datetime.now(timezone.utc)
        .date()
        .isoformat()
    )

    return get_daily_snapshot(
        conversation_memory=conversation_memory,
        orders_db=orders_db,
        date_str=target_date,
    )


# ==========================================================
# DASHBOARD CONVERSATIONS
# ==========================================================

@app.get("/dashboard/conversations")
def dashboard_conversations():

    conversations = []

    for (
        session_id,
        messages
    ) in conversation_memory.items():

        last_message = None
        last_message_at = None

        if messages:

            last_message = messages[
                -1
            ].get("content")

            last_message_at = messages[
                -1
            ].get("timestamp")

        order = order_memory.get(
            session_id,
            {}
        )

        support = support_memory.get(
            session_id,
            {}
        )

        conversations.append({
            "session_id": session_id,
            "message_count": len(
                messages
            ),
            "last_message": last_message,
            "last_message_at": last_message_at,
            "order_id": order.get(
                "order_id"
            ),
            "order_status": order.get(
                "status"
            ),
            "buying_intent": order.get(
                "buying_intent",
                False,
            ),
            "support_issue": support.get(
                "issue_type"
            ),
            "escalated": support.get(
                "escalated",
                False,
            ),
        })

    conversations.sort(
        key=lambda item: item.get(
            "message_count",
            0,
        ),
        reverse=True,
    )

    return {
        "total": len(conversations),
        "conversations": conversations,
    }


# ==========================================================
# DASHBOARD CONVERSATION DETAIL
# ==========================================================

@app.get(
    "/dashboard/conversations/{session_id}"
)
def dashboard_conversation_detail(
    session_id: str,
):

    messages = conversation_memory.get(
        session_id
    )

    if messages is None:

        return {
            "found": False,
            "session_id": session_id,
            "message": (
                "Conversation not found."
            ),
        }

    return {
        "found": True,
        "session_id": session_id,
        "messages": messages,
        "order_state": order_memory.get(
            session_id,
            create_order_state(),
        ),
        "support_state": support_memory.get(
            session_id,
            create_support_state(),
        ),
    }


# ==========================================================
# DASHBOARD ORDERS
# ==========================================================

@app.get("/dashboard/orders")
def dashboard_orders(
    status: Optional[str] = None,
):

    _auto_progress_order_statuses()

    orders = list(
        orders_db.values()
    )

    if status:

        orders = [
            order
            for order in orders
            if order.get("status") == status
        ]

    orders.sort(
        key=lambda order: order.get(
            "created_at",
            ""
        ),
        reverse=True,
    )

    return {
        "total": len(orders),
        "orders": orders,
    }


# ==========================================================
# DASHBOARD ESCALATIONS
# ==========================================================

@app.get("/dashboard/escalations")
def dashboard_escalations():

    escalations = []

    for (
        session_id,
        state
    ) in support_memory.items():

        if state.get("escalated"):

            escalations.append({
                "session_id": session_id,
                "issue_type": state.get(
                    "issue_type"
                ),
                "complaint_count": state.get(
                    "complaint_count",
                    0,
                ),
                "order_reference": state.get(
                    "order_reference"
                ),
                "escalation_reason": state.get(
                    "escalation_reason"
                ),
            })

    return {
        "total": len(escalations),
        "escalations": escalations,
    }


# ==========================================================
# DASHBOARD FOLLOW-UPS
# ==========================================================

@app.get("/dashboard/follow-ups")
def dashboard_follow_ups():

    follow_ups = []

    for (
        order_id,
        state
    ) in follow_up_memory.items():

        follow_ups.append({
            "order_id": order_id,
            **state,
        })

    return {
        "total": len(follow_ups),
        "follow_ups": follow_ups,
    }


# ==========================================================
# DASHBOARD HEALTH / SUMMARY
# ==========================================================

@app.get("/dashboard/summary")
def dashboard_summary():

    _auto_progress_order_statuses()

    analytics = get_dashboard_analytics(
        conversation_memory=conversation_memory,
        orders_db=orders_db,
        support_memory=support_memory,
        follow_up_memory=follow_up_memory,
    )

    return {
        "status": "online",
        "version": "0.9.0",
        "generated_at": (
            datetime.now(timezone.utc)
            .isoformat()
        ),
        "summary": {
            "total_conversations": (
                analytics["conversations"]["total"]
            ),
            "total_orders": (
                analytics["orders"]["total"]
            ),
            "delivered_orders": (
                analytics["orders"].get(
                    "delivered",
                    0,
                )
            ),
            "active_escalations": (
                analytics["support"][
                    "active_escalations"
                ]
            ),
            "average_rating": (
                analytics["feedback"][
                    "average_rating"
                ]
            ),
        },
    }


# ==========================================================
# ==========================================================
# PHASE 8 — WHATSAPP WEBHOOK
# ==========================================================
# ==========================================================


# ==========================================================
# WEBHOOK VERIFICATION (Meta calls this once during setup)
# ==========================================================

@app.get("/webhook/whatsapp")
async def whatsapp_webhook_verify(request: Request):

    params = request.query_params

    result = verify_webhook_challenge(
        params.get("hub.mode"),
        params.get("hub.verify_token"),
        params.get("hub.challenge"),
    )

    if result is not None:

        return (
            int(result)
            if result.isdigit()
            else result
        )

    return {
        "status": "verification_failed",
    }


# ==========================================================
# BACKGROUND PROCESSOR
#
# Runs AFTER the webhook already returned 200 to Meta, so Meta
# never times out waiting on the AI reply. Meta expects a fast
# ack and can eventually disable a slow/unresponsive webhook.
#
# PHASE 9 — VOICE NOTES
#
# Incoming messages now come in two flavours:
#
#   1. TEXT   -> unchanged: goes straight into
#                handle_incoming_message() and the reply is
#                sent back as a WhatsApp text message.
#
#   2. AUDIO  -> the voice note is downloaded from WhatsApp,
#                transcribed with Gemini (voice_agent), the
#                transcript is fed into the EXACT SAME
#                handle_incoming_message() brain used for
#                text, and the resulting reply text is turned
#                back into speech (voice_agent) and sent to
#                the customer as a WhatsApp voice note. No
#                text reply is sent for a voice conversation.
#
# If anything in the voice pipeline fails (download,
# transcription, synthesis, or upload), the code falls back
# to a text message so the customer is never left without an
# answer.
# ==========================================================

def _process_whatsapp_message_background(
    payload: Dict[str, Any],
) -> None:

    parsed = extract_incoming_text_message(
        payload
    )

    if not parsed or not parsed.get("wa_id"):
        return

    wa_id = parsed["wa_id"]

    if parsed.get("message_id"):

        mark_message_as_read(
            parsed["message_id"]
        )

    session_id = wa_session_id(wa_id)

    # ------------------------------------------------------
    # QUICK-REPLY BUTTON (order confirmation template ka
    # "CONFIRM_ORDER" / "CANCEL_ORDER" button dabane par)
    # ------------------------------------------------------

    # Template button dabane par WhatsApp ya to payload bhejta hai
    # (CONFIRM_ORDER / CANCEL_ORDER) ya button ka text
    # ("Yes, Confirm Order" / "No, Cancel Order"). Dono handle hote hain.
    button_key = (
        parsed.get("button_payload")
        or parsed.get("text")
        or ""
    ).strip().lower()

    confirm_keys = ("confirm_order", "yes, confirm order")
    cancel_keys = ("cancel_order", "no, cancel order")

    if (
        "button_payload" in parsed
        and (button_key in confirm_keys or button_key in cancel_keys)
    ):

        marker = (
            "__BTN_CONFIRM_ORDER__"
            if button_key in confirm_keys
            else "__BTN_CANCEL_ORDER__"
        )

        result = handle_incoming_message(
            session_id,
            marker,
        )

        send_whatsapp_text(
            wa_id,
            result["reply"],
        )

        return

    # ------------------------------------------------------
    # VOICE NOTE
    # ------------------------------------------------------

    if parsed.get("audio_id"):

        media = whatsapp_agent.download_whatsapp_media(
            parsed["audio_id"]
        )

        if not media:

            send_whatsapp_text(
                wa_id,
                "Maazrat, aapka voice message download nahi ho "
                "saka. Barae meherbani dobara bhejein.",
            )

            return

        audio_bytes, mime_type = media

        transcript = voice_agent.transcribe_audio_bytes(
            audio_bytes,
            mime_type,
        )

        if not transcript:

            send_whatsapp_text(
                wa_id,
                "Maazrat, voice message samajh nahi aaya. Barae "
                "meherbani dobara bolein ya likh kar bhej dein.",
            )

            return

        result = handle_incoming_message(
            session_id,
            transcript,
        )

        reply_text = result["reply"]

        voice_bytes = voice_agent.synthesize_speech_ogg(
            reply_text
        )

        sent_as_voice = False

        if voice_bytes:

            media_id = whatsapp_agent.upload_whatsapp_media(
                voice_bytes
            )

            if media_id:

                sent_as_voice = whatsapp_agent.send_whatsapp_audio(
                    wa_id,
                    media_id,
                )

        if not sent_as_voice:

            # Fallback so the customer always gets an answer
            # even if TTS/upload/send failed for some reason.
            send_whatsapp_text(
                wa_id,
                reply_text,
            )

        return

    # ------------------------------------------------------
    # UNSUPPORTED TYPE (image, video, location, etc.)
    # ------------------------------------------------------

    if parsed.get("text") is None:

        send_whatsapp_text(
            wa_id,
            "Maazrat, is waqt sirf text ya voice messages support "
            "hote hain. Please apna sawal likh kar ya voice note "
            "bhej dein.",
        )

        return

    # ------------------------------------------------------
    # TEXT MESSAGE
    # ------------------------------------------------------

    result = handle_incoming_message(
        session_id,
        parsed["text"],
    )

    send_whatsapp_text(
        wa_id,
        result["reply"],
    )


# ==========================================================
# RECEIVE INCOMING WHATSAPP MESSAGES
# ==========================================================

@app.post("/webhook/whatsapp")
async def whatsapp_webhook_receive(
    request: Request,
    background_tasks: BackgroundTasks,
):

    # Sirf Meta ki signed requests qubool hoti hain.
    raw_body = await request.body()

    if not security.verify_whatsapp_signature(
        raw_body,
        request.headers.get("x-hub-signature-256"),
    ):

        logger.warning("Rejected WhatsApp webhook with bad/missing signature")

        raise HTTPException(403, "Invalid signature")

    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(400, "Invalid JSON")

    # Meta ke delivery status updates (sent / delivered / read /
    # failed) log karein, taake pata chale message customer tak
    # pohancha ya Meta ne baad mein reject kiya (aur kyun).
    try:

        for entry in payload.get("entry", []):

            for change in entry.get("changes", []):

                for status in (
                    change.get("value", {}).get("statuses") or []
                ):

                    if status.get("status") == "failed":

                        logger.error(
                            "WhatsApp delivery FAILED | to=%s | errors=%s",
                            status.get("recipient_id"),
                            status.get("errors"),
                        )

                    else:

                        logger.info(
                            "WhatsApp status | to=%s | status=%s",
                            status.get("recipient_id"),
                            status.get("status"),
                        )

    except Exception:

        logger.exception("Failed to log WhatsApp status update")

    background_tasks.add_task(
        _process_whatsapp_message_background,
        payload,
    )

    # Ack immediately — Meta requires a fast 200 response.
    return {
        "status": "received",
    }


# ==========================================================
# WEBSITE ORDER ENDPOINT (R&H website ke checkout se)
# ==========================================================

class WebsiteOrder(BaseModel):
    product_id: str
    size: str
    color: str
    quantity: int = Field(ge=1, le=10)
    name: str = Field(min_length=2, max_length=80)
    phone: str
    city: str = Field(min_length=2, max_length=60)
    address: str = Field(min_length=10, max_length=300)
    payment_method: str
    whatsapp_opt_in: bool = False
    opt_in_text: str = ""
    website: str = ""  # honeypot: sirf bots isay bharte hain



# ==========================================================
# WEBSITE ORDER — WhatsApp confirmation sender
#
# Template bhejta hai (business-initiated message ke liye
# zaroori). Result hamesha log hota hai, taake Railway logs
# mein saaf nazar aaye ke message gaya ya nahi. Agar template
# fail ho jaye to plain text fallback try hota hai (yeh sirf
# tab deliver hota hai jab customer ne pichle 24 ghante mein
# message kiya ho).
# ==========================================================

def _send_website_order_whatsapp(
    wa_id: str,
    record: Dict[str, Any],
) -> None:

    try:

        sent = whatsapp_agent.send_whatsapp_template(
            wa_id,
            WEBSITE_TEMPLATE_NAME,
            [
                record["name"],
                record["order_id"],
                f"PKR {record['total']}",
            ],
            WEBSITE_TEMPLATE_LANG,
        )

        if sent:

            logger.info(
                "Website order %s: WhatsApp template '%s' (%s) "
                "sent to %s",
                record["order_id"],
                WEBSITE_TEMPLATE_NAME,
                WEBSITE_TEMPLATE_LANG,
                wa_id,
            )

            return

        logger.error(
            "Website order %s: WhatsApp template '%s' (lang=%s) "
            "FAILED for %s — see the 'WhatsApp template send "
            "failed' line above for Meta's error. Trying plain "
            "text fallback.",
            record["order_id"],
            WEBSITE_TEMPLATE_NAME,
            WEBSITE_TEMPLATE_LANG,
            wa_id,
        )

        fallback_text = (
            f"Assalam-o-Alaikum {record['name']}! Aapka order "
            f"{record['order_id']} mil gaya hai. "
            f"Total: PKR {record['total']}. "
            "Confirm karne ke liye order ID yahan bhej dein."
        )

        if send_whatsapp_text(wa_id, fallback_text):

            logger.info(
                "Website order %s: plain-text fallback sent to %s",
                record["order_id"],
                wa_id,
            )

        else:

            logger.error(
                "Website order %s: plain-text fallback also failed "
                "for %s",
                record["order_id"],
                wa_id,
            )

    except Exception:

        logger.exception(
            "Website order %s: unexpected error while sending "
            "WhatsApp confirmation",
            record.get("order_id"),
        )


@app.post("/webhooks/website-order")
def website_order(
    order: WebsiteOrder,
    background_tasks: BackgroundTasks,
    x_site_secret: str = Header(default=""),
):

    if not security.safe_equals(x_site_secret, WEBSITE_API_SECRET):
        raise HTTPException(403, "Forbidden")

    if order.website:
        return {"status": "ok"}

    product = get_product_by_id(order.product_id)

    if not product:
        raise HTTPException(422, "Product nahi mila.")

    if order.size not in product.get("sizes", []):
        raise HTTPException(422, "Yeh size is product mein available nahi.")

    if order.color not in product.get("colors", []):
        raise HTTPException(422, "Yeh color is product mein available nahi.")

    if order.payment_method not in BUSINESS_DATA.get("payment_methods", []):
        raise HTTPException(422, "Payment method sahi nahi.")

    phone = extract_phone(order.phone)
    wa_id = whatsapp_agent.normalize_phone_to_wa_id(order.phone)

    if not phone or not wa_id:
        raise HTTPException(422, "Phone number sahi nahi.")

    session_id = wa_session_id(wa_id)
    now = _now_iso()
    order_id = generate_order_id()
    unit_price = product["pricing"]["listed_price"]

    will_send_template = bool(
        order.whatsapp_opt_in
        and WEBSITE_TEMPLATE_NAME
        and session_id not in wa_opt_out
    )

    record = {
        "order_id": order_id,
        "source": "website",
        "product": product["name"],
        "product_id": product["id"],
        "size": order.size,
        "color": order.color,
        "quantity": order.quantity,
        "total": unit_price * order.quantity,
        "name": order.name.strip(),
        "phone": phone,
        "city": order.city.strip(),
        "address": order.address.strip(),
        "payment_method": order.payment_method,
        # Website order shuru mein hamesha "processing" hota hai.
        # Customer WhatsApp par confirm kare to "confirmed" ho jata hai.
        "status": "processing",
        "delivery_estimate": get_delivery_estimate(),
        "session_id": session_id,
        "whatsapp_opt_in": order.whatsapp_opt_in,
        "opt_in_text": order.opt_in_text if order.whatsapp_opt_in else "",
        "opt_in_at": now if order.whatsapp_opt_in else None,
        "customer_confirmed": False,
        "created_at": now,
        "updated_at": now,
    }

    is_repeat = any(
        o.get("session_id") == session_id for o in orders_db.values()
    )

    orders_db[order_id] = record
    follow_up_memory[order_id] = create_follow_up_state(order_id)

    db.save("orders_db", order_id, record)
    db.save("follow_up_memory", order_id, follow_up_memory[order_id])

    background_tasks.add_task(alerts.send_order_alert, record, is_repeat)

    if will_send_template:

        background_tasks.add_task(
            _send_website_order_whatsapp,
            wa_id,
            record,
        )

    else:

        logger.warning(
            "Website order %s: WhatsApp template NOT sent | "
            "whatsapp_opt_in=%s | WEBSITE_TEMPLATE_NAME=%r | "
            "opted_out=%s",
            order_id,
            order.whatsapp_opt_in,
            WEBSITE_TEMPLATE_NAME,
            session_id in wa_opt_out,
        )

    return {
        "status": "ok",
        "order_id": order_id,
        "whatsapp_queued": will_send_template,
    }


# ==========================================================
# DEBUG — WhatsApp templates check
#
# Browser mein kholein:
#   /debug/whatsapp-templates   (dashboard login token zaroori hai)
# Dikhata hai ke bot ke token ko kaun si templates (aur kis
# language code mein) nazar aa rahi hain. Masla theek hone ke
# baad is endpoint ko hata dein.
# ==========================================================

@app.get("/debug/whatsapp-templates")
def debug_whatsapp_templates():

    return whatsapp_agent.debug_template_info()


# ==========================================================
# DEBUG — Template ko direct test karein aur Meta ka asli
# error browser mein dekhein.
#
# Browser mein kholein (apna number 03xxxxxxxxx format mein):
#   /debug/test-template?phone=03XXXXXXXXX   (login token zaroori hai)
#
# Masla theek hone ke baad is endpoint ko hata dein.
# ==========================================================

@app.get("/debug/test-template")
def debug_test_template(
    phone: str = "",
):

    wa_id = whatsapp_agent.normalize_phone_to_wa_id(phone)

    if not wa_id:
        raise HTTPException(422, "Phone number sahi nahi.")

    if not WEBSITE_TEMPLATE_NAME:
        return {"error": "WEBSITE_TEMPLATE_NAME env variable khali hai"}

    payload = {
        "messaging_product": "whatsapp",
        "to": wa_id,
        "type": "template",
        "template": {
            "name": WEBSITE_TEMPLATE_NAME,
            "language": {"code": WEBSITE_TEMPLATE_LANG},
            "components": [
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": "Test User"},
                        {"type": "text", "text": "ORD-TEST1234"},
                        {"type": "text", "text": "PKR 2499"},
                    ],
                }
            ],
        },
    }

    try:

        response = httpx.post(
            whatsapp_agent._messages_url(),
            headers={
                "Authorization": (
                    f"Bearer {whatsapp_agent.WHATSAPP_ACCESS_TOKEN}"
                ),
                "Content-Type": "application/json",
            },
            json=payload,
            timeout=15.0,
        )

        return {
            "template": WEBSITE_TEMPLATE_NAME,
            "language": WEBSITE_TEMPLATE_LANG,
            "to": wa_id,
            "meta_status_code": response.status_code,
            "meta_response": response.json(),
        }

    except Exception as e:

        return {"error": str(e)}