from typing import Dict, Any, List


# ==========================================================
# ORDER STATUS ANALYTICS
# ==========================================================

ORDER_STATUSES = [
    "confirmed",
    "processing",
    "shipped",
    "out_for_delivery",
    "delivered",
    "cancelled",
]


def calculate_order_statistics(
    orders_db: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:

    statistics = {
        "total": len(orders_db),
    }

    # Start every known status at zero
    for status in ORDER_STATUSES:
        statistics[status] = 0

    # Count orders by status
    for order in orders_db.values():

        status = order.get("status")

        if status in statistics:
            statistics[status] += 1

    return statistics


# ==========================================================
# CONVERSATION ANALYTICS
# ==========================================================

def calculate_conversation_statistics(
    conversation_memory: Dict[str, List[Dict[str, Any]]]
) -> Dict[str, Any]:

    total_messages = 0
    active_conversations = 0

    for messages in conversation_memory.values():

        if messages:
            active_conversations += 1

        total_messages += len(messages)

    return {
        "total": len(conversation_memory),
        "active": active_conversations,
        "total_messages": total_messages,
    }


# ==========================================================
# SUPPORT / ESCALATION ANALYTICS
# ==========================================================

def calculate_support_statistics(
    support_memory: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:

    active_escalations = 0

    issue_types = {
        "return": 0,
        "exchange": 0,
        "complaint": 0,
    }

    for state in support_memory.values():

        if state.get("escalated"):
            active_escalations += 1

        issue_type = state.get("issue_type")

        if issue_type in issue_types:
            issue_types[issue_type] += 1

    return {
        "total_sessions": len(support_memory),
        "active_escalations": active_escalations,
        "issue_types": issue_types,
    }


# ==========================================================
# FOLLOW-UP ANALYTICS
# ==========================================================

def calculate_follow_up_statistics(
    follow_up_memory: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:

    total = len(follow_up_memory)

    delivered_orders = 0
    awaiting_feedback = 0
    feedback_received = 0

    for state in follow_up_memory.values():

        if state.get("delivered_at"):
            delivered_orders += 1

        if state.get("awaiting_feedback"):
            awaiting_feedback += 1

        if state.get("feedback_received"):
            feedback_received += 1

    return {
        "total": total,
        "delivered_orders": delivered_orders,
        "awaiting_feedback": awaiting_feedback,
        "feedback_received": feedback_received,
    }


# ==========================================================
# FEEDBACK ANALYTICS
# ==========================================================

def calculate_feedback_statistics(
    follow_up_memory: Dict[str, Dict[str, Any]]
) -> Dict[str, Any]:

    ratings = []

    for state in follow_up_memory.values():

        feedback = state.get("feedback")

        # Support different possible feedback structures
        if isinstance(feedback, dict):

            rating = feedback.get("rating")

            if isinstance(rating, (int, float)):
                ratings.append(rating)

        # Some implementations may store rating directly
        rating = state.get("rating")

        if isinstance(rating, (int, float)):
            ratings.append(rating)

    total_feedback = len(ratings)

    average_rating = 0

    if total_feedback > 0:
        average_rating = round(
            sum(ratings) / total_feedback,
            2,
        )

    return {
        "total": total_feedback,
        "average_rating": average_rating,
        "ratings": ratings,
    }


# ==========================================================
# RECENT ORDERS
# ==========================================================

def get_recent_orders(
    orders_db: Dict[str, Dict[str, Any]],
    limit: int = 10,
) -> List[Dict[str, Any]]:

    orders = list(orders_db.values())

    # Sort newest first
    orders.sort(
        key=lambda order: order.get(
            "created_at",
            ""
        ),
        reverse=True,
    )

    return orders[:limit]


# ==========================================================
# RECENT ESCALATIONS
# ==========================================================

def get_active_escalations(
    support_memory: Dict[str, Dict[str, Any]]
) -> List[Dict[str, Any]]:

    escalations = []

    for session_id, state in support_memory.items():

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

    return escalations


# ==========================================================
# DAILY SNAPSHOT (date-filtered counts)
#
# Lets the business owner pick a single date and see exactly
# how many conversations were active that day and how many
# orders were placed that day — independent of the lifetime
# totals shown elsewhere on the Overview page.
#
# A conversation "counts" for a date if ANY of its messages
# has a timestamp on that date (messages are stored with an
# ISO 8601 "timestamp" field — see main.py). Older messages
# saved before this field existed simply won't match any
# date filter, which is expected or new data going forward.
# ==========================================================

def get_daily_snapshot(
    conversation_memory: Dict[str, List[Dict[str, Any]]],
    orders_db: Dict[str, Dict[str, Any]],
    date_str: str,
) -> Dict[str, Any]:

    conversations_count = 0

    for messages in conversation_memory.values():

        for message in messages:

            timestamp = message.get("timestamp") or ""

            if timestamp.startswith(date_str):
                conversations_count += 1
                break

    orders_count = 0

    for order in orders_db.values():

        created_at = order.get("created_at") or ""

        if created_at.startswith(date_str):
            orders_count += 1

    return {
        "date": date_str,
        "conversations": conversations_count,
        "orders": orders_count,
    }


# ==========================================================
# MAIN DASHBOARD ANALYTICS
# ==========================================================

def get_dashboard_analytics(
    conversation_memory: Dict[
        str,
        List[Dict[str, Any]]
    ],
    orders_db: Dict[
        str,
        Dict[str, Any]
    ],
    support_memory: Dict[
        str,
        Dict[str, Any]
    ],
    follow_up_memory: Dict[
        str,
        Dict[str, Any]
    ],
) -> Dict[str, Any]:

    conversations = (
        calculate_conversation_statistics(
            conversation_memory
        )
    )

    orders = calculate_order_statistics(
        orders_db
    )

    support = calculate_support_statistics(
        support_memory
    )

    follow_ups = calculate_follow_up_statistics(
        follow_up_memory
    )

    feedback = calculate_feedback_statistics(
        follow_up_memory
    )

    return {
        "conversations": conversations,
        "orders": orders,
        "support": support,
        "follow_ups": follow_ups,
        "feedback": feedback,
        "recent_orders": get_recent_orders(
            orders_db,
            limit=10,
        ),
        "active_escalations": get_active_escalations(
            support_memory
        ),
    }