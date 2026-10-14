import re
from typing import Optional, Dict, Any, List

from .business_data import BUSINESS_DATA


# ==========================================================
# PRODUCT KEYWORDS
# ==========================================================

PRODUCT_KEYWORDS = {

    "product_001": [
        "black shirt",
        "black premium shirt",
        "premium cotton black shirt",
        "premium black shirt",
        "black wali shirt",
        "black shirt wali",
        "black wali",
    ],

    "product_002": [
        "white shirt",
        "classic white shirt",
        "white classic shirt",
        "white wali shirt",
        "white wali",
    ],

    "product_003": [
        "graphic t-shirt",
        "graphic tshirt",
        "graphic tee",
        "oversized t-shirt",
        "oversized tshirt",
        "oversized graphic",
        "graphic wali shirt",
        "graphic tee wali",
        # NEW — colloquial "<color> t-shirt" phrasing that customers
        # actually type. Without these, "black t-shirt" fell through
        # to ambiguous word-overlap scoring against product_001.
        "black t-shirt",
        "black tshirt",
        "black tee",
        "white t-shirt",
        "white tshirt",
        "white tee",
    ],
}


# ==========================================================
# NORMALIZE TEXT
# ==========================================================

def normalize_text(text: str) -> str:

    if not text:
        return ""

    text = str(text).lower().strip()

    text = text.replace("’", "'")

    text = re.sub(
        r"[-_/]+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text


# ==========================================================
# NEGATION-AWARE CLEANUP
#
# Handles corrections like "white nh black" / "white nahi black" /
# "white not black" — the word right before a negation marker is
# what the customer is REJECTING, so we drop it before matching.
#
# NOTE: "na" is intentionally excluded from this list — in Roman
# Urdu it's very often just a filler/emphasis word ("kar do na"),
# not a real negation, and including it caused false strips. If
# real negation corrections using bare "na" show up in testing,
# we can add clause-aware detection later (like support_agent.py
# already does), but for now "nahi"/"nai"/"nh"/"not" cover the
# common explicit-correction cases safely.
# ==========================================================

NEGATION_MARKERS = {"nahi", "nai", "nh", "not"}


def _remove_negated_terms(text: str) -> str:

    if not text:
        return text

    words = text.split()
    result: List[str] = []

    for word in words:

        if word in NEGATION_MARKERS:

            if result:
                result.pop()

            continue

        result.append(word)

    return " ".join(result)


# ==========================================================
# SINGLE-MESSAGE MATCH (exact/keyword first, then word overlap)
# ==========================================================

def _match_single_text(
    conversation_text: str,
    products: List[Dict[str, Any]],
) -> Optional[Dict[str, Any]]:

    if not conversation_text:
        return None

    # ------------------------------------------------------
    # 1. EXACT PRODUCT NAME / ID / KEYWORD
    # ------------------------------------------------------

    for product in products:

        product_name = normalize_text(product.get("name", ""))
        product_id = normalize_text(product.get("id", ""))

        if product_name and product_name in conversation_text:
            return product

        if product_id and product_id in conversation_text:
            return product

        keywords = PRODUCT_KEYWORDS.get(product.get("id"), [])

        for keyword in keywords:

            keyword = normalize_text(keyword)

            if keyword and keyword in conversation_text:
                return product

    # ------------------------------------------------------
    # 2. WORD-BASED MATCH (fallback only)
    # ------------------------------------------------------

    conversation_words = set(conversation_text.split())

    best_product = None
    best_score = 0

    for product in products:

        product_name = normalize_text(product.get("name", ""))
        product_words = set(product_name.split())

        if not product_words:
            continue

        score = len(conversation_words.intersection(product_words))

        if score > best_score:
            best_score = score
            best_product = product

    if best_score >= 2:
        return best_product

    return None


# ==========================================================
# FIND PRODUCT
#
# Scans the CUSTOMER's own messages only (assistant replies are
# excluded entirely — they were causing false matches), newest
# message first. The first message (starting from the latest)
# that clearly names a product wins, so a fresh correction like
# "White nh black" always overrides anything said earlier.
# ==========================================================

def find_product_from_messages(
    messages: List[Dict[str, Any]]
) -> Optional[Dict[str, Any]]:

    if not messages:
        return None

    user_messages = [
        message
        for message in messages
        if message.get("role") == "user"
    ]

    if not user_messages:
        return None

    products = BUSINESS_DATA.get(
        "products",
        []
    )

    if not products:
        return None

    for message in reversed(user_messages):

        raw_text = str(
            message.get(
                "content",
                ""
            )
        )

        text = _remove_negated_terms(
            normalize_text(raw_text)
        )

        match = _match_single_text(
            text,
            products,
        )

        if match:
            return match

    return None