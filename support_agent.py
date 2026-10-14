import re
from typing import Optional, Dict, Any, List

from .business_data import BUSINESS_DATA


# ==========================================================
# SUPPORT ISSUE KEYWORDS
# ==========================================================

COMPLAINT_KEYWORDS = [
    "complaint",
    "shikayat",
    "problem",
    "issue",
    "masla",
    "masail",
    "defective",
    "damaged",
    "kharab",
    "torn",
    "phata",
    "wrong item",
    "ghalat item",
    "ghalat product",
    "ghalat size",
    "wrong product",
    "wrong size",
    "not satisfied",
    "bad quality",
    "quality kharab",
    "late delivery",
    "delay ho gaya",
    "der se aya",
    "abhi tak nahi aya",
    "not received",
    "nahi mila",
    "missing",
    "gum ho gaya",
]

RETURN_KEYWORDS = [
    "return",
    "wapas",
    "wapis",
    "vapis",
    "refund",
    "paisa wapas",
    "paise wapas",
    "return karna hai",
    "return karwana",
]

EXCHANGE_KEYWORDS = [
    "exchange",
    "size change",
    "size badalna",
    "size badal",
    "replace karna",
    "badal do",
    "different size",
    "different color",
    "color change",
]

# ------------------------------------------------------------
# Escalation triggers.
#
# IMPORTANT: these are intentionally broader/stronger signals
# than a normal complaint — direct requests for a human, or
# language indicating the situation has gone beyond what a
# scripted policy answer can resolve.
# ------------------------------------------------------------

ESCALATION_TRIGGER_KEYWORDS = [
    "manager",
    "human se baat",
    "insaan se baat",
    "agent se baat",
    "real person",
    "not a bot",
    "supervisor",
    "third time",
    "teesri baar",
    "baar baar",
    "fed up",
    "tang aa gaya",
    "tang aa chuka",
    "legal action",
    "consumer court",
    "fraud",
    "scam",
    "cheated",
    "dhoka",
    "worst service",
    "never buying again",
]

HARD_ESCALATION_KEYWORDS = [
    "fraud",
    "scam",
    "cheated",
    "dhoka",
    "legal action",
    "consumer court",
]

ORDER_ID_PATTERN = re.compile(
    r"\b(?:order\s*#?|ord[- ]?)(\d{3,10})\b",
    re.IGNORECASE,
)

# ------------------------------------------------------------
# Words that, if found near a keyword, flip its meaning
# (e.g. "return NAHI karna", "exchange NA chahiye").
# ------------------------------------------------------------

NEGATION_WORDS = [
    "nahi",
    "nai",
    "na",
    "mat",
    "not",
]

NEGATION_WINDOW = 3  # words to look on each side of the keyword, within a clause

CLAUSE_SPLIT_PATTERN = re.compile(
    r",|؛|\blekin\b|\bmagar\b|\bbalke\b|\bbalkay\b"
)


# ==========================================================
# NORMALIZE
# ==========================================================

def normalize(text: str) -> str:

    if not text:
        return ""

    text = str(text).lower().strip()

    text = re.sub(
        r"[.!?؟۔]+",
        " ",
        text,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text


def split_clauses(text: str) -> List[str]:
    """
    Splits a message into smaller clauses on commas and common
    contrast words (lekin/magar/balke), so negation detected in
    one clause ("return nahi karna") doesn't bleed into a
    different clause of the same message ("exchange chahiye").
    """

    if not text:
        return []

    parts = CLAUSE_SPLIT_PATTERN.split(text)

    return [
        part.strip()
        for part in parts
        if part.strip()
    ]


# ==========================================================
# NEGATION-AWARE KEYWORD MATCH
# ==========================================================

def is_keyword_negated(
    words: List[str],
    keyword: str,
) -> bool:
    """
    Returns True if `keyword` (which may be multi-word) appears
    in `words` but has a negation word within NEGATION_WINDOW
    words on either side — meaning the customer is describing
    what they DON'T want, not making an actual request.
    """

    keyword_words = keyword.split()
    k_len = len(keyword_words)

    for i in range(len(words) - k_len + 1):

        if words[i:i + k_len] == keyword_words:

            start = max(0, i - NEGATION_WINDOW)
            end = min(len(words), i + k_len + NEGATION_WINDOW)

            context = (
                words[start:i]
                + words[i + k_len:end]
            )

            if any(
                negation in context
                for negation in NEGATION_WORDS
            ):
                return True

    return False


def keyword_matches(
    text: str,
    keywords: List[str],
) -> bool:
    """
    True if any keyword in `keywords` appears in any clause of
    `text` and is NOT negated nearby within that same clause.
    """

    if not text:
        return False

    clauses = split_clauses(text)

    if not clauses:
        clauses = [text]

    for clause in clauses:

        words = clause.split()

        for keyword in keywords:

            keyword = normalize(keyword)

            if not keyword:
                continue

            if keyword not in clause:
                continue

            if is_keyword_negated(words, keyword):
                continue

            return True

    return False


# ==========================================================
# DEFAULT SUPPORT STATE
# ==========================================================

def create_support_state() -> Dict[str, Any]:

    return {
        "issue_type": None,
        "complaint_count": 0,
        "order_reference": None,
        "escalated": False,
        "escalation_reason": None,
    }


# ==========================================================
# INTENT DETECTION
# ==========================================================

def detect_support_intent(message: str) -> Optional[str]:
    """
    Returns one of: 'return', 'exchange', 'complaint', or None.
    Checked in this priority order because a message can contain
    overlapping words (e.g. "kharab item return karna hai").
    Negated mentions (e.g. "return nahi karna") are skipped so
    the correct intent still comes through.
    """

    text = normalize(message)

    if not text:
        return None

    if keyword_matches(text, RETURN_KEYWORDS):
        return "return"

    if keyword_matches(text, EXCHANGE_KEYWORDS):
        return "exchange"

    if keyword_matches(text, COMPLAINT_KEYWORDS):
        return "complaint"

    return None


# ==========================================================
# ESCALATION DETECTION
# ==========================================================

def detect_escalation_trigger(message: str) -> bool:

    text = normalize(message)

    if not text:
        return False

    return keyword_matches(text, ESCALATION_TRIGGER_KEYWORDS)


def is_hard_escalation(message: str) -> bool:
    """
    Serious allegations (fraud/scam/legal) escalate immediately,
    regardless of complaint count.
    """

    text = normalize(message)

    if not text:
        return False

    return keyword_matches(text, HARD_ESCALATION_KEYWORDS)


# ==========================================================
# ORDER REFERENCE EXTRACTION
# ==========================================================

def extract_order_reference(message: str) -> Optional[str]:

    if not message:
        return None

    match = ORDER_ID_PATTERN.search(str(message))

    if match:
        return match.group(1)

    return None


# ==========================================================
# SUPPORT CONFIG (from BUSINESS_DATA, with safe fallback)
# ==========================================================

def get_support_config() -> Dict[str, Any]:

    return BUSINESS_DATA.get(
        "customer_support",
        {},
    )


def get_auto_escalate_threshold() -> int:

    config = get_support_config()

    try:
        return int(
            config.get(
                "auto_escalate_after_complaints",
                3,
            )
        )
    except (ValueError, TypeError):
        return 3


# ==========================================================
# SUPPORT DECISION ENGINE
# ==========================================================

def get_support_decision(
    messages: List[Dict[str, Any]],
    support_state: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    """
    Mutates support_state in place (so it persists across turns
    in the caller's session storage) and returns the backend
    decision for the latest message, or None if the latest
    message has no support-relevant content and there is no
    ongoing support issue for this session.
    """

    if not messages:
        return None

    latest_message = str(
        messages[-1].get(
            "content",
            "",
        )
    )

    intent = detect_support_intent(latest_message)
    escalation_trigger = detect_escalation_trigger(latest_message)
    hard_escalation = is_hard_escalation(latest_message)

    order_reference = extract_order_reference(latest_message)

    if order_reference:
        support_state["order_reference"] = order_reference

    # ------------------------------------------------------
    # Nothing support-related in this message, and no ongoing
    # issue tracked for this session yet.
    # ------------------------------------------------------

    if (
        intent is None
        and not escalation_trigger
        and not support_state.get("issue_type")
    ):
        return None

    if intent:
        support_state["issue_type"] = intent
        support_state["complaint_count"] = (
            support_state.get(
                "complaint_count",
                0,
            )
            + 1
        )

    # ------------------------------------------------------
    # ESCALATION DECISION
    # ------------------------------------------------------

    already_escalated = support_state.get(
        "escalated",
        False,
    )

    should_escalate = already_escalated
    escalation_reason = support_state.get(
        "escalation_reason"
    )

    if not already_escalated:

        if hard_escalation:

            should_escalate = True

            escalation_reason = (
                "serious_allegation_requires_human_review"
            )

        elif escalation_trigger:

            should_escalate = True

            escalation_reason = (
                "customer_requested_human_or_expressed_"
                "strong_frustration"
            )

        elif (
            support_state.get("complaint_count", 0)
            >= get_auto_escalate_threshold()
        ):

            should_escalate = True

            escalation_reason = (
                "repeated_unresolved_complaint"
            )

    support_state["escalated"] = should_escalate
    support_state["escalation_reason"] = (
        escalation_reason if should_escalate else None
    )

    # ------------------------------------------------------
    # AUTHORITATIVE POLICY DATA
    # ------------------------------------------------------

    policy_data = None

    if support_state.get("issue_type") == "return":

        policy_data = BUSINESS_DATA.get(
            "return_policy",
            {},
        )

    elif support_state.get("issue_type") == "exchange":

        policy_data = BUSINESS_DATA.get(
            "exchange_policy",
            {},
        )

    return {
        "issue_type": support_state.get("issue_type"),
        "complaint_count": support_state.get(
            "complaint_count",
            0,
        ),
        "order_reference": support_state.get(
            "order_reference"
        ),
        "escalated": support_state.get(
            "escalated",
            False,
        ),
        "escalation_reason": support_state.get(
            "escalation_reason"
        ),
        "policy_data": policy_data,
    }


# ==========================================================
# BUILD PROMPT TEXT (INTERNAL ONLY BLOCK FOR THE MODEL)
# ==========================================================

def build_support_prompt_text(
    messages: List[Dict[str, Any]],
    support_state: Dict[str, Any],
) -> str:

    decision = get_support_decision(
        messages,
        support_state,
    )

    if not decision:

        return (
            "No active complaint, return, or exchange issue "
            "detected for the latest message. Do not bring up "
            "support topics unless the customer does."
        )

    lines = [
        "SUPPORT DECISION — INTERNAL ONLY",
        "",
        f"Issue type: {decision['issue_type'] or 'unclear'}",
        f"Complaint count this session: {decision['complaint_count']}",
        (
            "Order reference: "
            f"{decision['order_reference'] or 'not provided'}"
        ),
        f"Escalated to human team: {decision['escalated']}",
    ]

    if decision["escalated"]:

        lines.append(
            f"Escalation reason (internal): {decision['escalation_reason']}"
        )

        lines.append("")

        lines.append(
            "INSTRUCTION: Calmly acknowledge the issue and "
            "apologize for the inconvenience without admitting "
            "fault you cannot verify. Tell the customer this has "
            "been forwarded to a human team member who will "
            "follow up. Do not keep troubleshooting yourself. "
            "Do not promise compensation, a refund amount, or a "
            "timeline you cannot verify. Do not reveal the "
            "internal escalation reason or complaint count."
        )

    else:

        if decision["policy_data"]:

            lines.append("")

            lines.append(
                f"Relevant policy (authoritative): {decision['policy_data']}"
            )

            lines.append("")

            lines.append(
                "INSTRUCTION: Use only the policy data above. "
                "Naturally confirm the eligibility conditions "
                "(time limit, item condition). Ask for the order "
                "reference only if it is not already known. "
                "Explain the next step the customer needs to "
                "take. Do NOT confirm that a return, exchange, "
                "or refund has been approved or processed — only "
                "a human or a real order system can confirm that."
            )

        else:

            lines.append("")

            lines.append(
                "INSTRUCTION: The customer is describing a "
                "problem. Acknowledge it empathetically. Ask "
                "ONE clarifying question if needed (what "
                "happened, order reference). Do not promise a "
                "resolution you cannot verify. If this turns out "
                "to be a return or exchange, guide the customer "
                "using BUSINESS_DATA return_policy / "
                "exchange_policy only."
            )

    return "\n".join(lines)