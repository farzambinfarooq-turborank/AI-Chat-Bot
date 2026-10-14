import re
import uuid
from typing import Optional, Dict, Any, List

from .business_data import BUSINESS_DATA
from .product_matching import normalize_text, find_product_from_messages
# NOTE: the "Hello" -> mixed-language reply issue is in ai_agent.py's
# SALES_RULES (LANGUAGE section), not in this file. See the chat
# message for the recommended prompt tweak.


# ==========================================================
# ORDER FIELD SEQUENCE
# ==========================================================

ORDER_FIELD_SEQUENCE = [
    "product",
    "size",
    "color",
    "quantity",
    "name",
    "phone",
    "city",
    "address",
    "payment_method",
]

FIELD_LABELS = {
    "product": "product",
    "size": "size",
    "color": "color",
    "quantity": "quantity",
    "name": "customer name",
    "phone": "phone number",
    "city": "city",
    "address": "delivery address",
    "payment_method": "payment method (Cash on Delivery or Bank Transfer)",
}


# ==========================================================
# BUYING INTENT
# ==========================================================

BUYING_INTENT_KEYWORDS = [
    "order karna hai",
    "order karni hai",
    "order krna hai",
    "order krni hai",
    "order kar dein",
    "order kar do",
    "order kar den",
    "order kardo",
    "order krdo",
    "order kar dena",
    "order karwana",
    "order krwana",
    "order mangwani hai",
    "order mangwana hai",
    "mangwani hai",
    "mangwana hai",
    "order confirm",
    "order place",
    "order book",
    "le lunga",
    "le loon",
    "lena hai",
    "lenaa hai",
    "chahiye mujhe ye",
    "ye le lu",
    "ye lena hai",
    "ye chahiye mujhe",
    "buy karna hai",
    "buy krna hai",
    "kharidna hai",
    "kharidna hy",
    "final kar do",
    "final krdo",
    "confirm kar do",
    "confirm krdo",
    "book kar do",
    "book krdo",
    "book karna hai",
    "book krna hai",
    "mangwana hai",
    "mangwa do",
    "mangwao",

    # English buying-intent phrases — this business also gets
    # customers who write in plain English, not just Roman
    # Urdu, so these need explicit coverage too.
    "place an order",
    "place my order",
    "place the order",
    "place order",
    "want to order",
    "want to buy",
    "i want to buy",
    "i'd like to order",
    "id like to order",
    "like to order",
    "like to place an order",
    "like to proceed",
    "want to proceed",
    "confirm the order",
    "confirm my order",
    "confirm this order",
    "yes i want to order",
    "yes, place the order",
    "i'll take it",
    "ill take it",
    "i will take it",
    "book this order",
]

ORDER_INTENT_PATTERN = re.compile(
    r"\border\b\s*"
    r"(karna|karni|krna|krni|kar dena|kar den|kar dein|"
    r"kardo|krdo|karwana|krwana|karwani|krwani|karwao|"
    r"krwao|confirm|place|book|dedo|de do|de den|de dein|"
    r"dena|deni|de dena|de deni)\b",
    re.IGNORECASE,
)


def detect_buying_intent(text: str) -> bool:
    normalized = normalize_text(str(text or ""))

    if any(keyword in normalized for keyword in BUYING_INTENT_KEYWORDS):
        return True

    return bool(ORDER_INTENT_PATTERN.search(normalized))


# ==========================================================
# IMPLICIT BUYING INTENT (affirmative reply / volunteered details)
#
# Real customers often confirm buying intent with a short "haan" /
# "hn" / "ok" reply to the bot's own question, or by simply typing
# their name/phone/address straight away without ever saying the
# word "order". These are just as valid a signal as the explicit
# keywords above, so we detect them separately here.
# ==========================================================

AFFIRMATIVE_KEYWORDS = [
    "haan",
    "han",
    "hn",
    "hnji",
    "ji haan",
    "ji han",
    "ji",
    "g",
    "yes",
    "yep",
    "yeah",
    "sure",
    "ok",
    "okay",
    "theek hai",
    "thik hai",
    "bilkul",
    "zaroor",
]

ORDER_PROMPT_SIGNAL_PATTERN = re.compile(
    r"(?:order\s+(?:karna|karni|krna|krni|kar dena|kar den|kar dein|"
    r"kardo|krdo|karwana|krwana|karwani|krwani|karwao|"
    r"krwao|confirm|place|book|dedo|de do|de den|de dein)|"
    r"chahte\s+h[ae]in|"
    r"karwana\s+chahte|"
    r"book\s+kar(?:wa)?(?:u|oon)?|"
    r"place\s+(?:an|your|the|my)?\s*order|"
    r"want\s+to\s+(?:order|buy|proceed)|"
    r"like\s+to\s+(?:order|place|buy|proceed)|"
    r"proceed\s+with\s+(?:the|this|your|my)?\s*order|"
    r"confirm\s+(?:the|this|your|my)?\s*order)"
    r"[^?]{0,40}\?\s*$",
    re.IGNORECASE,
)


def is_short_affirmative_reply(text: str) -> bool:
    """
    True only for a short, direct "yes"-type reply (so we don't
    accidentally match "haan" buried inside an unrelated sentence).
    """

    normalized = normalize_text(str(text or ""))

    if not normalized:
        return False

    words = normalized.split()

    if len(words) > 4:
        return False

    return (
        normalized in AFFIRMATIVE_KEYWORDS
        or any(word in AFFIRMATIVE_KEYWORDS for word in words)
    )


def assistant_recently_asked_about_order(
    messages: List[Dict[str, Any]],
) -> bool:
    """
    True if the message right before the customer's latest reply was
    the assistant asking whether the customer wants to place an order.
    """

    if len(messages) < 2:
        return False

    previous_message = messages[-2]

    if previous_message.get("role") != "assistant":
        return False

    content = str(previous_message.get("content", ""))

    return bool(ORDER_PROMPT_SIGNAL_PATTERN.search(content))


def has_strong_contact_signal(text: str) -> bool:
    """
    True if the customer volunteered a phone number together with a
    name, city, or address in the same message — a strong real-world
    signal of buying intent even without any explicit "order" phrase.
    """

    if not extract_phone(text):
        return False

    return bool(
        extract_city(text)
        or extract_name_smart(text)
        or extract_address_smart(text)
    )


# ==========================================================
# PHONE
# ==========================================================

PHONE_PATTERN = re.compile(
    r"(?:\+92|0092|92|0)?[\s-]?3\d{2}[\s-]?\d{7}\b"
)


def extract_phone(text: str) -> Optional[str]:
    text = str(text or "")

    match = PHONE_PATTERN.search(text)

    if not match:
        return None

    digits = re.sub(r"\D", "", match.group(0))

    if digits.startswith("0092"):
        digits = "0" + digits[4:]

    elif digits.startswith("92"):
        digits = "0" + digits[2:]

    if len(digits) == 10 and digits.startswith("3"):
        digits = "0" + digits

    if len(digits) == 11 and digits.startswith("03"):
        return digits

    return None


# ==========================================================
# CITY
# ==========================================================

KNOWN_CITIES = [
    "rahim yar khan",
    "dera ghazi khan",
    "dera ismail khan",
    "muzaffarabad",
    "rawalpindi",
    "islamabad",
    "sheikhupura",
    "gujranwala",
    "bahawalpur",
    "faisalabad",
    "hyderabad",
    "peshawar",
    "sargodha",
    "abbottabad",
    "nawabshah",
    "karachi",
    "lahore",
    "multan",
    "quetta",
    "sialkot",
    "sukkur",
    "larkana",
    "mardan",
    "gujrat",
    "kasur",
    "mirpur",
    "gilgit",
    "swat",
    "jhelum",
    "okara",
    "sahiwal",
    "chiniot",
    "kamoke",
    "hafizabad",
    "attock",
    "wah",
]


def extract_city(text: str) -> Optional[str]:
    normalized = normalize_text(str(text or ""))

    # Longest first to avoid partial matching.
    for city in sorted(KNOWN_CITIES, key=len, reverse=True):

        if re.search(
            rf"\b{re.escape(city)}\b",
            normalized,
        ):
            return city.title()

    return None


# ==========================================================
# PAYMENT METHOD
# ==========================================================

PAYMENT_METHOD_KEYWORDS = {
    "Cash on Delivery": [
        "cash on delivery",
        "cash pe delivery",
        "cash on delievery",
        "cash",
        "cod",
        "naqad",
    ],
    "Bank Transfer": [
        "bank transfer",
        "online transfer",
        "transfer",
        "bank",
    ],
}


def extract_payment_method(text: str) -> Optional[str]:
    normalized = normalize_text(str(text or ""))

    valid_methods = BUSINESS_DATA.get(
        "payment_methods",
        [],
    )

    # More specific phrases first.
    for method in (
        "Cash on Delivery",
        "Bank Transfer",
    ):

        if method not in valid_methods:
            continue

        for keyword in PAYMENT_METHOD_KEYWORDS[method]:

            if re.search(
                rf"\b{re.escape(keyword)}\b",
                normalized,
            ):
                return method

    return None


# ==========================================================
# QUANTITY
# ==========================================================

QUANTITY_PATTERN = re.compile(
    r"\b(\d{1,2})\b"
)

QUANTITY_BLOCK_CONTEXT_WORDS = [
    "block",
    "house",
    "flat",
    "no",
    "number",
    "street",
    "road",
    "phase",
    "sector",
    "floor",
    "plot",
    "building",
    "gali",
    "makan",
]


def extract_quantity(text: str) -> Optional[int]:
    text = str(text or "")
    normalized = normalize_text(text)

    # ------------------------------------------------------
    # Strong quantity signal
    # Examples:
    # 1 shirt
    # 2 shirts
    # 3 pieces
    # 4 pcs
    # ------------------------------------------------------

    strong_pattern = re.search(
        r"\b(\d{1,2})\s*"
        r"(?:piece|pieces|pcs|pc|peice|"
        r"shirt|shirts|item|items)\b",
        normalized,
        re.IGNORECASE,
    )

    if strong_pattern:

        value = int(
            strong_pattern.group(1)
        )

        if 1 <= value <= 50:
            return value

    # ------------------------------------------------------
    # Explicit quantity
    # quantity 2
    # qty: 2
    # adad 3
    # ------------------------------------------------------

    explicit_pattern = re.search(
        r"\b(?:quantity|qty|adad)\s*"
        r"[:=-]?\s*(\d{1,2})\b",
        normalized,
        re.IGNORECASE,
    )

    if explicit_pattern:

        value = int(
            explicit_pattern.group(1)
        )

        if 1 <= value <= 50:
            return value

    # ------------------------------------------------------
    # Short reply
    # Example:
    # "1"
    # "2"
    # "3 chahiye"
    # ------------------------------------------------------

    stripped = normalized.strip()

    short_match = re.fullmatch(
        r"(\d{1,2})(?:\s+(?:chahiye|hai|lena hai))?",
        stripped,
        re.IGNORECASE,
    )

    if short_match:

        value = int(
            short_match.group(1)
        )

        if 1 <= value <= 50:
            return value

    # ------------------------------------------------------
    # Quantity keyword adjacent to a number, ANYWHERE in the
    # message — not just when the whole message is short.
    #
    # Handles real-world replies like:
    # "Hn M size main chaiye 1 lkn address sirf karachi nh hai"
    # where "1" sits right next to "chahiye"/"chaiye" but is
    # buried inside a longer sentence. The short-reply
    # fullmatch above only fires when the ENTIRE message is
    # just the number + keyword, so a longer sentence like
    # this previously fell through to the <=6-word bare-number
    # fallback below and was missed entirely — causing the bot
    # to keep re-asking for quantity even after the customer
    # had already answered it.
    # ------------------------------------------------------

    keyword_adjacent_pattern = re.search(
        r"\b(?:chahiye|chaiye|chaheye|chahye)\s+(\d{1,2})\b"
        r"|\b(\d{1,2})\s+(?:chahiye|chaiye|chaheye|chahye|lena hai)\b",
        normalized,
        re.IGNORECASE,
    )

    if keyword_adjacent_pattern:

        value = int(
            keyword_adjacent_pattern.group(1)
            or keyword_adjacent_pattern.group(2)
        )

        if 1 <= value <= 50:
            return value

    # ------------------------------------------------------
    # Bare number inside short message
    # ------------------------------------------------------

    match = QUANTITY_PATTERN.search(
        normalized
    )

    if not match:
        return None

    value = int(
        match.group(1)
    )

    if not (1 <= value <= 50):
        return None

    words = normalized.split()
    matched_token = match.group(1)

    for index, word in enumerate(words):

        if matched_token != word:
            continue

        if index > 0:

            previous_word = words[index - 1]

            if previous_word in QUANTITY_BLOCK_CONTEXT_WORDS:
                return None

        break

    # Only trust a bare number in a short message.
    if len(words) <= 6:
        return value

    return None


# ==========================================================
# SIZE
# ==========================================================

# ==========================================================
# NAME EXTRACTION — REVERSED ORDER STOP WORDS
#
# Used by extract_name_smart's reversed-order fallback ("Ahmed
# name hai") to know where the real name value STOPS while
# walking backward. Includes field-marker keywords, common
# connectors, and size/color tokens (a size letter like "xl"
# or "m" is alphabetic and would otherwise look like a valid
# name word to the backward scan).
# ==========================================================

NAME_REVERSED_STOP_WORDS = {
    "phone", "number", "mobile", "contact", "city", "shehar",
    "shaher", "address", "pata", "size", "color", "quantity",
    "qty", "piece", "pieces", "pcs", "cod", "cash", "bank",
    "transfer", "hai", "h", "is", "chahiye", "chaiye",
    "chaheye", "chahye", "ka", "ke", "ki", "aur", "or", "and",
    "orr", "se", "main", "mein", "bhi", "s", "m", "l", "xl",
    "xxl", "large", "medium", "small", "extra", "black",
    "white", "total", "order", "krni", "karni", "krna",
    "karna", "lena", "hain", "chahte",
}


SIZE_ALIASES = {
    "S": [
        "s",
        "small",
    ],
    "M": [
        "m",
        "medium",
        "med",
    ],
    "L": [
        "l",
        "large",
    ],
    "XL": [
        "xl",
        "extra large",
        "extra-large",
        "xlarge",
        "x large",
    ],
    "XXL": [
        "xxl",
        "2xl",
        "double xl",
        "extra extra large",
    ],
}


def extract_size(
    text: str,
    product: Optional[Dict[str, Any]],
) -> Optional[str]:

    if not product:
        return None

    normalized = normalize_text(
        str(text or "")
    )

    tokens = set(
        normalized.split()
    )

    for size in product.get(
        "sizes",
        [],
    ):

        size_key = str(
            size
        ).strip().upper()

        aliases = SIZE_ALIASES.get(
            size_key,
            [
                normalize_text(
                    str(size)
                )
            ],
        )

        for alias in aliases:

            alias_normalized = normalize_text(
                alias
            )

            if not alias_normalized:
                continue

            if " " in alias_normalized:

                if alias_normalized in normalized:
                    return size

            elif alias_normalized in tokens:

                return size

    return None


# ==========================================================
# COLOR
# ==========================================================

def extract_color(
    text: str,
    product: Optional[Dict[str, Any]],
) -> Optional[str]:

    if not product:
        return None

    normalized = normalize_text(
        str(text or "")
    )

    colors = product.get(
        "colors",
        [],
    )

    # Longest first.
    for color in sorted(
        colors,
        key=lambda item: len(str(item)),
        reverse=True,
    ):

        normalized_color = normalize_text(
            str(color)
        )

        if (
            normalized_color
            and re.search(
                rf"\b{re.escape(normalized_color)}\b",
                normalized,
            )
        ):
            return color

    return None


# ==========================================================
# NAME
# ==========================================================

def extract_name_smart(
    raw_text: str,
) -> Optional[str]:

    text = str(
        raw_text or ""
    ).strip()

    if not text:
        return None

    # ------------------------------------------------------
    # Explicit name patterns
    #
    # Examples:
    # Mera naam Ahmed Khan hai
    # Mera name Ahmed Khan hai
    # My name is Ahmed Khan
    # Naam Ahmed Khan hai
    # Name: Ahmed Khan
    # ------------------------------------------------------

    patterns = [
        r"\bmera\s+naam\s+(?:hai|is)\s+(.+?)(?=\s+(?:phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",

        r"\bmera\s+naam\s+(.+?)(?=\s+(?:hai|h|phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",

        r"\bmera\s+name\s+(?:hai|is)\s+(.+?)(?=\s+(?:phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",

        r"\bmera\s+name\s+(.+?)(?=\s+(?:hai|h|phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",

        r"\bmy\s+name\s+is\s+(.+?)(?=\s+(?:phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",

        r"\b(?:naam|name)\s*[:=-]?\s+(?!(?:hai|h|is)\b)(.+?)(?=\s+(?:hai|h|is|phone|number|mobile|contact|city|shehar|address|pata|size|color|quantity|qty|piece|pieces|pcs|cod|cash|bank|transfer)\b|$)",
    ]

    for pattern in patterns:

        match = re.search(
            pattern,
            text,
            flags=re.IGNORECASE,
        )

        if not match:
            continue

        candidate = match.group(
            1
        ).strip(
            " ,.:-"
        )

        # Remove trailing conversational words.
        candidate = re.sub(
            r"\s+(?:hai|h|is|aur|or|and|my|mera|meri)$",
            "",
            candidate,
            flags=re.IGNORECASE,
        ).strip()

        if candidate:
            return candidate

    # ------------------------------------------------------
    # REVERSED ORDER — "<value> naam/name hai"
    #
    # Very common real-world phrasing that the patterns above
    # do NOT cover: the customer states the value BEFORE the
    # keyword instead of after it, e.g. "Muhammad khan name
    # hai" instead of "mera naam Muhammad khan hai". The
    # patterns above all assume naam/name is followed by the
    # value; here naam/name is followed directly by hai/h/is
    # with the value sitting immediately before it instead.
    #
    # Walk backward word-by-word from just before "naam/name
    # hai", collecting up to 3 plain alphabetic words, and stop
    # as soon as a digit, punctuation-heavy token, or a known
    # field-marker/connector word is hit — this keeps the
    # capture to just the name itself instead of swallowing
    # unrelated quantity/size/address/phone text that happens
    # to sit earlier in a long, run-on message.
    # ------------------------------------------------------

    reversed_match = re.search(
        r"\b(?:naam|name)\s+(?:hai|h|is)\b",
        text,
        flags=re.IGNORECASE,
    )

    if reversed_match:

        preceding_text = text[
            :reversed_match.start()
        ]

        preceding_words = preceding_text.split()

        collected_words: List[str] = []

        for word in reversed(preceding_words):

            cleaned_word = word.strip(",.:-")

            if not cleaned_word:
                continue

            if not re.fullmatch(
                r"[A-Za-z]+",
                cleaned_word,
            ):
                break

            if cleaned_word.lower() in NAME_REVERSED_STOP_WORDS:
                break

            collected_words.insert(0, cleaned_word)

            if len(collected_words) >= 3:
                break

        if collected_words:
            return " ".join(collected_words)

    return None


# ==========================================================
# FREE TEXT CLEANER
# ==========================================================

def clean_free_text_field(
    raw_text: str,
) -> str:

    cleaned = str(
        raw_text or ""
    ).strip()

    prefixes = [
        "mera naam hai",
        "mera naam",
        "mera name hai",
        "mera name",
        "my name is",
        "naam hai",
        "name hai",
        "name is",
        "naam",
        "name",
    ]

    lowered = normalize_text(
        cleaned
    )

    for prefix in prefixes:

        if lowered.startswith(
            prefix
        ):

            cleaned = cleaned[
                len(prefix):
            ].strip(
                " ,.:-"
            )

            break

    return cleaned.strip()


# ==========================================================
# QUESTION-LIKE TEXT GUARD
#
# clean_free_text_field() above is a last-resort fallback used
# when the customer's reply is being collected for a free-text
# field (name/address) but doesn't contain a recognizable
# marker — it just returns the near-raw message text. That is
# unsafe on its own: if the customer's reply is actually an
# unrelated QUESTION (e.g. "Total kitne huay??" asked while the
# backend is still waiting on the address), that question would
# get silently saved as the field's value. This guard rejects
# any candidate that looks like a question, so the field stays
# empty and the bot asks again properly instead of corrupting
# the order with garbage.
# ==========================================================

QUESTION_WORD_PATTERN = re.compile(
    r"\b(?:kya|kia|kitna|kitne|kitni|kaisay|kaise|kab|kahan|"
    r"kaunsa|kaunsi|kyun|kyu|why|what|when|where|how|which)\b",
    re.IGNORECASE,
)


def looks_like_a_question(text: str) -> bool:

    stripped = str(text or "").strip()

    if not stripped:
        return False

    if stripped.endswith("?"):
        return True

    if QUESTION_WORD_PATTERN.search(stripped):
        return True

    return False


# ==========================================================
# ADDRESS
# ==========================================================

ADDRESS_LEAD_MARKERS = [
    "delivery address",
    "delivery ka address",
    "address",
    "pata",
]

ADDRESS_STOP_MARKERS = [
    "phone",
    "number",
    "mobile",
    "contact",
    "city",
    "shehar",
    "shaher",
    "quantity",
    "qty",
    "piece",
    "pieces",
    "pcs",
    "cod",
    "cash on delivery",
    "cash",
    "bank transfer",
    "online transfer",
    "transfer",
    "payment",
    "size",
    "color",
]


def extract_address_smart(
    raw_text: str,
) -> Optional[str]:

    text = str(
        raw_text or ""
    ).strip()

    if not text:
        return None

    # ------------------------------------------------------
    # Find address marker.
    # ------------------------------------------------------

    lowered = normalize_text(
        text
    )

    start_idx = None
    marker_length = 0

    for marker in ADDRESS_LEAD_MARKERS:

        idx = lowered.find(
            marker
        )

        if idx != -1 and (
            start_idx is None
            or idx < start_idx
        ):

            start_idx = idx
            marker_length = len(marker)

    if start_idx is None:
        return None

    start = (
        start_idx
        + marker_length
    )

    candidate_text = text[
        start:
    ].strip(
        " ,.:-"
    )

    # ------------------------------------------------------
    # Remove "hai", "is", etc. after address marker.
    # ------------------------------------------------------

    connector_pattern = re.compile(
        r"^(?:hai|h|is|yeh hai|ye hai)\s+",
        re.IGNORECASE,
    )

    while connector_pattern.match(
        candidate_text
    ):

        candidate_text = connector_pattern.sub(
            "",
            candidate_text,
            count=1,
        ).strip(
            " ,.:-"
        )

    # ------------------------------------------------------
    # Stop when next order field starts.
    #
    # This fixes:
    #
    # address XYZ Colony hai 1 shirt chahiye aur
    #
    # -> XYZ Colony
    # ------------------------------------------------------

    stop_pattern = re.compile(
        r"\s+(?="
        r"phone\b|"
        r"number\b|"
        r"mobile\b|"
        r"contact\b|"
        r"city\b|"
        r"shehar\b|"
        r"shaher\b|"
        r"quantity\b|"
        r"qty\b|"
        r"\d{1,2}\s+(?:piece|pieces|pcs|pc|shirt|shirts|item|items)\b|"
        r"cod\b|"
        r"cash\b|"
        r"bank\b|"
        r"transfer\b|"
        r"payment\b|"
        r"size\b|"
        r"color\b"
        r")",
        re.IGNORECASE,
    )

    candidate = stop_pattern.split(
        candidate_text,
        maxsplit=1,
    )[0].strip(
        " ,.:-"
    )

    # ------------------------------------------------------
    # Remove trailing "hai / h / is".
    # ------------------------------------------------------

    candidate = re.sub(
        r"\s+(?:hai|h|is)$",
        "",
        candidate,
        flags=re.IGNORECASE,
    ).strip(
        " ,.:-"
    )

    return candidate if candidate else None


# ==========================================================
# BUNDLED FIELD EXTRACTION
# ==========================================================

def extract_all_explicit_fields(
    raw_text: str,
    product: Optional[Dict[str, Any]],
) -> Dict[str, Any]:

    text = str(
        raw_text or ""
    )

    result: Dict[str, Any] = {}

    # Name
    name = extract_name_smart(
        text
    )

    if name:
        result["name"] = name

    # Phone
    phone = extract_phone(
        text
    )

    if phone:
        result["phone"] = phone

    # City
    city = extract_city(
        text
    )

    if city:
        result["city"] = city

    # Address
    address = extract_address_smart(
        text
    )

    if address:
        result["address"] = address

    # Payment
    payment_method = extract_payment_method(
        text
    )

    if payment_method:
        result["payment_method"] = payment_method

    # Quantity
    quantity = extract_quantity(
        text
    )

    if quantity:
        result["quantity"] = quantity

    # Product-dependent fields
    if product:

        size = extract_size(
            text,
            product,
        )

        if size:
            result["size"] = size

        color = extract_color(
            text,
            product,
        )

        if color:
            result["color"] = color

    return result


# ==========================================================
# SINGLE-LINE BUNDLED REPLY FALLBACK
#
# extract_bundled_reply_fields() above only kicks in when the
# customer's reply has multiple LINES or COMMA-separated
# segments. Real customers very often instead send everything
# as ONE continuous, punctuation-free sentence — e.g.
# "Farzam 03320240092 karachi flat no b1 fareed square cod" —
# with no keyword marking which word is the name vs. the
# address. Falling back to "just use the whole raw message as
# the name/address" (the old behaviour) is unsafe: it happily
# swallows the phone number, city, and payment method into
# whichever free-text field happens to be missing.
#
# This function instead finds every substring already claimed
# by a SPECIFIC extractor (phone number, known city, payment
# method, size, color), masks those substrings out, and treats
# whatever UNCLAIMED words are left — grouped in the order they
# appear — as the free-text candidates (name first, then
# address), matching how customers naturally write these
# messages: name first, contact/location details after.
# ==========================================================

def extract_single_line_free_text_fields(
    raw_text: str,
    order_state: Dict[str, Any],
    product: Optional[Dict[str, Any]],
    allow_free_text: bool = True,
) -> Dict[str, Any]:

    text = str(
        raw_text or ""
    )

    if not text.strip():
        return {}

    # ------------------------------------------------------
    # GUARD — question-like messages are never a name/address.
    #
    # If the customer's ENTIRE message reads like a question
    # (e.g. "black t shirt is it available ??"), it is a product
    # inquiry, not a name or delivery address. Without this
    # guard, the leftover-word logic below would happily chop
    # up a sentence like "I want to order black t shirt is it
    # available ??" into "I want to order" (saved as the
    # customer's NAME) and "t shirt is it available ??" (saved
    # as the ADDRESS) — corrupting the order with garbage and
    # letting it get confirmed with fake contact details. Bail
    # out here instead, so these fields stay empty and the bot
    # asks the customer properly for their real name/address.
    # ------------------------------------------------------

    if looks_like_a_question(text):
        return {}

    lowered = text.lower()

    result: Dict[str, Any] = {}
    claimed_spans: List[Any] = []

    # Phone
    phone_span_match = PHONE_PATTERN.search(text)

    if phone_span_match:

        claimed_spans.append(
            phone_span_match.span()
        )

        phone_value = extract_phone(text)

        if (
            phone_value
            and not order_state.get("phone")
            and "phone" not in result
        ):
            result["phone"] = phone_value

    # City (longest names first, avoids a shorter city name
    # accidentally matching inside a longer one)
    for city in sorted(
        KNOWN_CITIES,
        key=len,
        reverse=True,
    ):

        city_span_match = re.search(
            rf"\b{re.escape(city)}\b",
            lowered,
        )

        if city_span_match:

            claimed_spans.append(
                city_span_match.span()
            )

            if (
                not order_state.get("city")
                and "city" not in result
            ):
                result["city"] = city.title()

            break

    # Payment method
    for method in (
        "Cash on Delivery",
        "Bank Transfer",
    ):

        matched_payment = False

        for keyword in PAYMENT_METHOD_KEYWORDS.get(
            method,
            [],
        ):

            payment_span_match = re.search(
                rf"\b{re.escape(keyword)}\b",
                lowered,
            )

            if payment_span_match:

                claimed_spans.append(
                    payment_span_match.span()
                )

                if (
                    not order_state.get("payment_method")
                    and "payment_method" not in result
                ):
                    result["payment_method"] = method

                matched_payment = True
                break

        if matched_payment:
            break

    # Even if the strict phone pattern above didn't validate (a
    # customer typo — one digit short/extra — is common), still
    # mask out any long digit run so a clearly phone-shaped
    # number doesn't leak into the name/address text. The phone
    # field itself is deliberately left EMPTY in that case, so
    # the bot correctly asks the customer to resend a valid
    # number instead of silently accepting a broken one.
    if not phone_span_match:

        generic_digits_match = re.search(
            r"\d{7,}",
            text,
        )

        if generic_digits_match:

            claimed_spans.append(
                generic_digits_match.span()
            )

    # Size / color tokens (product-dependent) — masked out so
    # they never get swept into the leftover name/address text.
    if product:

        for size in product.get(
            "sizes",
            [],
        ):

            size_key = str(size).strip().upper()

            aliases = SIZE_ALIASES.get(
                size_key,
                [normalize_text(str(size))],
            )

            for alias in aliases:

                alias_normalized = normalize_text(alias)

                if not alias_normalized:
                    continue

                size_span_match = re.search(
                    rf"\b{re.escape(alias_normalized)}\b",
                    lowered,
                )

                if size_span_match:

                    claimed_spans.append(
                        size_span_match.span()
                    )

                    break

        for color in product.get(
            "colors",
            [],
        ):

            color_normalized = normalize_text(
                str(color)
            )

            if not color_normalized:
                continue

            color_span_match = re.search(
                rf"\b{re.escape(color_normalized)}\b",
                lowered,
            )

            if color_span_match:

                claimed_spans.append(
                    color_span_match.span()
                )

    # No recognizable anchor found anywhere in the message — no
    # safe way to tell name/address apart from everything else,
    # so don't guess.
    if not claimed_spans:
        return result

    # ------------------------------------------------------
    # Mask every claimed span with a non-whitespace sentinel
    # (preserves the original word boundaries/spacing so
    # leftover multi-word phrases like "flat no b1 fareed
    # square" stay grouped together), then split on whitespace
    # to inspect word-by-word which tokens are still "free".
    # ------------------------------------------------------

    masked_chars = list(text)

    for start, end in claimed_spans:

        for i in range(start, end):
            masked_chars[i] = "\x01"

    masked_text = "".join(masked_chars)

    original_words = text.split()
    masked_words = masked_text.split()

    leftover_groups: List[List[str]] = []
    current_group: List[str] = []

    for original_word, masked_word in zip(
        original_words,
        masked_words,
    ):

        if "\x01" in masked_word:

            if current_group:
                leftover_groups.append(current_group)
                current_group = []

            continue

        current_group.append(original_word)

    if current_group:
        leftover_groups.append(current_group)

    # ------------------------------------------------------
    # Assign leftover groups, in the order they appear, to
    # whichever free-text fields are still missing — name
    # first (customers almost always give their name before
    # anything else), then address.
    #
    # GUARD — allow_free_text=False (see caller in
    # get_order_decision): on the very message that FIRST
    # establishes buying intent (e.g. "Yeah! I want to order
    # black t shirt"), the customer has not been asked for
    # their name/address yet — this text is just them
    # expressing intent and naming a product. Guessing name/
    # address from whatever words are left over here is what
    # produced garbage like Customer="Yeah! I want to order",
    # Address="t shirt" in production. Only guess free-text
    # fields once the backend has actually prompted for them
    # on a LATER turn.
    # ------------------------------------------------------

    if not allow_free_text:
        return result

    free_text_fields = []

    if (
        not order_state.get("name")
        and "name" not in result
    ):
        free_text_fields.append("name")

    if (
        not order_state.get("address")
        and "address" not in result
    ):
        free_text_fields.append("address")

    for field in free_text_fields:

        if not leftover_groups:
            break

        candidate = " ".join(
            leftover_groups.pop(0)
        ).strip(" ,.:-")

        if candidate:
            result[field] = candidate

    return result


# ==========================================================
# BUNDLED MULTI-LINE REPLY FALLBACK
#
# When the backend asks for SEVERAL missing order fields at
# once (see format_order_prompt_text below), real customers
# very often reply by simply listing the values one per line,
# in the same order the bot asked — WITHOUT restating the
# field name/keyword (e.g. just "Farzam" instead of
# "naam Farzam", just an address instead of "address: ...").
#
# extract_all_explicit_fields() above only catches fields that
# have a reliable non-keyword pattern (phone numbers, known
# cities, size/color tokens, payment method keywords, or a
# quantity followed by a unit word). Free-text fields (name,
# address) and a bare quantity number require a keyword marker
# there, so they get missed in this bundled-reply style.
#
# This function is a second pass: it splits the message into
# lines/segments, first claims any line that matches a strong,
# specific pattern (phone/city/payment/size/color/quantity),
# then assigns whatever UNCLAIMED lines are left to the
# remaining missing free-text fields (name, then address) in
# that order. It is intentionally only used when the customer
# is replying to a multi-field prompt (2+ fields still
# missing), so it never misfires on a normal one-field answer.
# ==========================================================

def extract_bundled_reply_fields(
    raw_text: str,
    order_state: Dict[str, Any],
    product: Optional[Dict[str, Any]],
    allow_free_text: bool = True,
) -> Dict[str, Any]:

    text = str(
        raw_text or ""
    )

    # Split on newlines first; if the customer wrote it as one
    # line separated by commas instead, fall back to that.
    lines = [
        line.strip(" \t.,-")
        for line in re.split(r"[\n\r]+", text)
        if line.strip(" \t.,-")
    ]

    if len(lines) < 2:

        lines = [
            segment.strip(" \t.,-")
            for segment in text.split(",")
            if segment.strip(" \t.,-")
        ]

    if len(lines) < 2:
        return extract_single_line_free_text_fields(
            text,
            order_state,
            product,
            allow_free_text,
        )

    result: Dict[str, Any] = {}
    claimed_indexes = set()

    # ------------------------------------------------------
    # PASS 1 — claim any line that matches a strong, specific
    # pattern, REGARDLESS of whether that field was already
    # filled by the earlier full-text explicit pass. A line
    # that is clearly a phone number (for example) must never
    # be allowed to leak into the free-text pool just because
    # the phone field happened to already be set — otherwise
    # it gets mistaken for the name/address instead.
    # ------------------------------------------------------

    for index, line in enumerate(lines):

        value = extract_phone(line)

        if value:

            claimed_indexes.add(index)

            if (
                not order_state.get("phone")
                and "phone" not in result
            ):
                result["phone"] = value

            continue

        value = extract_payment_method(line)

        if value:

            claimed_indexes.add(index)

            if (
                not order_state.get("payment_method")
                and "payment_method" not in result
            ):
                result["payment_method"] = value

            continue

        value = extract_city(line)

        if value:

            claimed_indexes.add(index)

            if (
                not order_state.get("city")
                and "city" not in result
            ):
                result["city"] = value

            continue

        if product:

            value = extract_size(
                line,
                product,
            )

            if value:

                claimed_indexes.add(index)

                if (
                    not order_state.get("size")
                    and "size" not in result
                ):
                    result["size"] = value

                continue

            value = extract_color(
                line,
                product,
            )

            if value:

                claimed_indexes.add(index)

                if (
                    not order_state.get("color")
                    and "color" not in result
                ):
                    result["color"] = value

                continue

        bare_number_match = re.fullmatch(
            r"\d{1,2}",
            line,
        )

        if bare_number_match:

            numeric_value = int(
                bare_number_match.group(0)
            )

            if 1 <= numeric_value <= 50:

                claimed_indexes.add(index)

                if (
                    not order_state.get("quantity")
                    and "quantity" not in result
                ):
                    result["quantity"] = numeric_value

                continue

    # ------------------------------------------------------
    # PASS 2 — leftover free-text lines fill name, then
    # address, in the order they were sent.
    # ------------------------------------------------------

    if not allow_free_text:
        return result

    leftover_lines = [
        line
        for index, line in enumerate(lines)
        if index not in claimed_indexes
    ]

    free_text_fields = []

    if (
        not order_state.get("name")
        and "name" not in result
    ):
        free_text_fields.append("name")

    if (
        not order_state.get("address")
        and "address" not in result
    ):
        free_text_fields.append("address")

    for field in free_text_fields:

        if not leftover_lines:
            break

        result[field] = leftover_lines.pop(0)

    return result


# ==========================================================
# MISSING FIELD
# ==========================================================

def get_missing_field(
    order_state: Dict[str, Any],
) -> Optional[str]:

    for field in ORDER_FIELD_SEQUENCE:

        value = order_state.get(
            field
        )

        if value is None or value == "":
            return field

    return None


def get_missing_fields(
    order_state: Dict[str, Any],
) -> List[str]:
    """
    Returns ALL still-missing fields, in collection order, so the
    AI can ask for everything remaining in a single message
    instead of one field per turn.
    """

    missing = []

    for field in ORDER_FIELD_SEQUENCE:

        value = order_state.get(
            field
        )

        if value is None or value == "":
            missing.append(field)

    return missing


# ==========================================================
# DELIVERY
# ==========================================================

def get_delivery_estimate() -> str:

    delivery = BUSINESS_DATA.get(
        "delivery",
        {},
    )

    return delivery.get(
        "standard_delivery",
        "3-5 business days",
    )


# ==========================================================
# ORDER ID
# ==========================================================

def generate_order_id() -> str:

    return (
        "ORD-"
        + uuid.uuid4().hex[:8].upper()
    )


# ==========================================================
# PRODUCT LOOKUP
# ==========================================================

def get_product_by_id(
    product_id: Optional[str],
) -> Optional[Dict[str, Any]]:

    if not product_id:
        return None

    for product in BUSINESS_DATA.get(
        "products",
        [],
    ):

        if product.get(
            "id"
        ) == product_id:

            return product

    return None


# ==========================================================
# ORDER RECORD BUILDER
# ==========================================================

def build_order_record(
    order_state: Dict[str, Any],
) -> Dict[str, Any]:

    return {
        "order_id": order_state.get(
            "order_id"
        ),
        "product": order_state.get(
            "product"
        ),
        "product_id": order_state.get(
            "product_id"
        ),
        "size": order_state.get(
            "size"
        ),
        "color": order_state.get(
            "color"
        ),
        "quantity": order_state.get(
            "quantity"
        ),
        "name": order_state.get(
            "name"
        ),
        "phone": order_state.get(
            "phone"
        ),
        "city": order_state.get(
            "city"
        ),
        "address": order_state.get(
            "address"
        ),
        "payment_method": order_state.get(
            "payment_method"
        ),
        "status": order_state.get(
            "status",
            "confirmed",
        ),
        "delivery_estimate": get_delivery_estimate(),
    }


# ==========================================================
# START A NEW ORDER ROUND (REPEAT CUSTOMER)
#
# Once an order is confirmed, order_state.order_id is set and
# stays set forever for that session — otherwise the customer
# could never place a SECOND order in the same conversation
# (WhatsApp session_id is the same phone number every time).
#
# When the customer clearly wants to order again, this resets
# only the ORDER-SPECIFIC fields (product, size, color,
# quantity, order_id, status) so a fresh order can be
# collected — but deliberately KEEPS the previously known
# contact details (name, phone, city, address, payment_method)
# so the customer never has to repeat them. If the customer
# wants to ship to a different address this time, saying so
# will simply overwrite the kept value via the normal
# extraction logic below.
# ==========================================================

def start_new_order_round(
    order_state: Dict[str, Any],
) -> None:

    order_state["product"] = None
    order_state["product_id"] = None
    order_state["size"] = None
    order_state["color"] = None
    order_state["quantity"] = None

    order_state["order_id"] = None
    order_state["status"] = "collecting"
    order_state["stage"] = "collecting"
    order_state["last_asked_field"] = None
    order_state["buying_intent"] = True


# ==========================================================
# MAIN ORDER DECISION ENGINE
# ==========================================================

def get_order_decision(
    messages: List[Dict[str, Any]],
    order_state: Dict[str, Any],
) -> Dict[str, Any]:

    if not messages:

        return {
            "buying_intent": False,
            "active": False,
        }

    latest_message_raw = str(
        messages[-1].get(
            "content",
            "",
        )
    )

    latest_message = normalize_text(
        latest_message_raw
    )

    # ------------------------------------------------------
    # ALREADY CONFIRMED — unless the customer clearly wants
    # to place a NEW order in this same conversation, in
    # which case we start a fresh round below instead of
    # returning early here.
    # ------------------------------------------------------

    became_buying_intent_this_turn = False

    if order_state.get(
        "order_id"
    ):

        newly_mentioned_product = find_product_from_messages(
            messages[-1:]
        )

        different_product_mentioned = bool(
            newly_mentioned_product
            and newly_mentioned_product.get("id")
            != order_state.get("product_id")
        )

        wants_new_order = (
            detect_buying_intent(latest_message)
            or (
                is_short_affirmative_reply(latest_message_raw)
                and assistant_recently_asked_about_order(messages)
            )
            or different_product_mentioned
        )

        if not wants_new_order:

            return {
                "buying_intent": True,
                "active": True,
                "stage": "confirmed",
                "product": order_state.get(
                    "product"
                ),
                "collected": {
                    field: order_state.get(
                        field
                    )
                    for field in ORDER_FIELD_SEQUENCE
                },
                "missing_field": None,
                "order_id": order_state.get(
                    "order_id"
                ),
                "status": order_state.get(
                    "status"
                ),
                "delivery_estimate": get_delivery_estimate(),
                "new_order_record": None,
            }

        # Customer wants to order again — reuse known contact
        # details, start fresh on the order-specific fields.
        start_new_order_round(order_state)
        became_buying_intent_this_turn = True

    # ------------------------------------------------------
    # BUYING INTENT
    # ------------------------------------------------------

    if not order_state.get(
        "buying_intent"
    ):

        if detect_buying_intent(
            latest_message
        ):

            order_state[
                "buying_intent"
            ] = True

            order_state[
                "stage"
            ] = "collecting"

            became_buying_intent_this_turn = True

        elif (
            is_short_affirmative_reply(latest_message_raw)
            and assistant_recently_asked_about_order(messages)
        ):

            order_state[
                "buying_intent"
            ] = True

            order_state[
                "stage"
            ] = "collecting"

            became_buying_intent_this_turn = True

        elif has_strong_contact_signal(latest_message_raw):

            order_state[
                "buying_intent"
            ] = True

            order_state[
                "stage"
            ] = "collecting"

            became_buying_intent_this_turn = True

    if not order_state.get(
        "buying_intent"
    ):

        return {
            "buying_intent": False,
            "active": False,
        }

    # ------------------------------------------------------
    # PRODUCT
    # ------------------------------------------------------

    if not order_state.get(
        "product"
    ):

        matched_product = find_product_from_messages(
            messages
        )

        if matched_product:

            order_state[
                "product"
            ] = matched_product.get(
                "name"
            )

            order_state[
                "product_id"
            ] = matched_product.get(
                "id"
            )

    product = get_product_by_id(
        order_state.get(
            "product_id"
        )
    )

    # ------------------------------------------------------
    # AUTO COLOR
    # ------------------------------------------------------

    if (
        product
        and not order_state.get(
            "color"
        )
    ):

        colors = product.get(
            "colors",
            [],
        )

        if len(colors) == 1:

            order_state[
                "color"
            ] = colors[0]

    # ------------------------------------------------------
    # BACKFILL FROM EARLIER MESSAGES
    #
    # If buying intent has just turned True on THIS turn, the
    # customer may have already mentioned details (size, quantity,
    # color) in earlier messages, back when there was no active
    # order collection yet — those were never captured. Recover
    # them now instead of asking the customer to repeat themselves.
    #
    # NOTE: this only backfills fields that are still empty, so
    # it is safe to run even right after start_new_order_round()
    # reset the order-specific fields above — the kept contact
    # fields (name/phone/city/address/payment_method) are already
    # filled and will simply be skipped.
    #
    # IMPORTANT: for a REPEAT order (start_new_order_round already
    # ran above), scanning must start AFTER the previous order was
    # confirmed — never from the very beginning of the conversation.
    # Otherwise a color/size mentioned only in the PREVIOUS order's
    # messages (e.g. "white t-shirt order karni hai" from order #1)
    # can incorrectly get pulled into order #2 just because that
    # earlier product also happens to offer the same option, even
    # though the customer's current message clearly said something
    # else (e.g. "black t-shirt"). last_order_confirmed_index is set
    # the moment an order is confirmed below, and defaults to 0 for
    # a brand-new session that has never confirmed an order yet, so
    # first-order behaviour is unchanged.
    # ------------------------------------------------------

    if became_buying_intent_this_turn:

        backfill_start_index = (
            order_state.get(
                "last_order_confirmed_index"
            )
            or 0
        )

        for past_message in messages[backfill_start_index:-1]:

            if past_message.get(
                "role"
            ) != "user":
                continue

            past_fields = extract_all_explicit_fields(
                str(
                    past_message.get(
                        "content",
                        "",
                    )
                ),
                product,
            )

            for field, value in past_fields.items():

                if not order_state.get(
                    field
                ):
                    order_state[
                        field
                    ] = value

    # ------------------------------------------------------
    # EXPLICIT / BUNDLED EXTRACTION
    # ------------------------------------------------------

    explicit_fields = extract_all_explicit_fields(
        latest_message_raw,
        product,
    )

    for field, value in explicit_fields.items():

        if not order_state.get(
            field
        ):

            order_state[
                field
            ] = value

    # ------------------------------------------------------
    # BUNDLED MULTI-LINE FALLBACK
    #
    # Only runs when several fields are still missing after
    # the explicit pass above — i.e. the customer was likely
    # replying to a multi-field prompt with an unlabeled,
    # line-by-line list (see extract_bundled_reply_fields).
    # ------------------------------------------------------

    if len(get_missing_fields(order_state)) >= 2:

        bundled_fields = extract_bundled_reply_fields(
            latest_message_raw,
            order_state,
            product,
            # Never guess name/address from leftover words on the
            # SAME turn that buying intent first switched on — that
            # message is just the customer expressing intent
            # ("I want to order black t shirt"), not answering a
            # question about their name/address. Free-text guessing
            # only turns back on from the next turn, once the bot
            # has actually asked for these fields.
            allow_free_text=not became_buying_intent_this_turn,
        )

        for field, value in bundled_fields.items():

            if not order_state.get(
                field
            ):

                order_state[
                    field
                ] = value

    # ------------------------------------------------------
    # FALLBACK TO LAST ASKED FIELD
    # ------------------------------------------------------

    last_asked = order_state.get(
        "last_asked_field"
    )

    # Size
    if last_asked == "size":

        if (
            product
            and not order_state.get(
                "size"
            )
        ):

            value = extract_size(
                latest_message_raw,
                product,
            )

            if value:
                order_state[
                    "size"
                ] = value

    # Color
    elif last_asked == "color":

        if (
            product
            and not order_state.get(
                "color"
            )
        ):

            value = extract_color(
                latest_message_raw,
                product,
            )

            if value:
                order_state[
                    "color"
                ] = value

    # Quantity
    elif last_asked == "quantity":

        if not order_state.get(
            "quantity"
        ):

            value = extract_quantity(
                latest_message_raw
            )

            if value:
                order_state[
                    "quantity"
                ] = value

    # Name
    elif last_asked == "name":

        if not order_state.get(
            "name"
        ):

            value = extract_name_smart(
                latest_message_raw
            )

            if not value and not looks_like_a_question(
                latest_message_raw
            ):

                value = clean_free_text_field(
                    latest_message_raw
                )

            if value:

                order_state[
                    "name"
                ] = value

    # Phone
    elif last_asked == "phone":

        if not order_state.get(
            "phone"
        ):

            value = extract_phone(
                latest_message_raw
            )

            if value:

                order_state[
                    "phone"
                ] = value

    # City
    elif last_asked == "city":

        if not order_state.get(
            "city"
        ):

            value = extract_city(
                latest_message_raw
            )

            if value:

                order_state[
                    "city"
                ] = value

    # Address
    elif last_asked == "address":

        if not order_state.get(
            "address"
        ):

            value = extract_address_smart(
                latest_message_raw
            )

            if not value and not looks_like_a_question(
                latest_message_raw
            ):

                value = clean_free_text_field(
                    latest_message_raw
                )

            if value:

                order_state[
                    "address"
                ] = value

    # Payment
    elif last_asked == "payment_method":

        if not order_state.get(
            "payment_method"
        ):

            value = extract_payment_method(
                latest_message_raw
            )

            if value:

                order_state[
                    "payment_method"
                ] = value

    # ------------------------------------------------------
    # DETERMINE MISSING FIELD
    # ------------------------------------------------------

    missing_field = get_missing_field(
        order_state
    )

    missing_fields = get_missing_fields(
        order_state
    )

    order_state[
        "last_asked_field"
    ] = missing_field

    # ------------------------------------------------------
    # CONFIRM ORDER
    # ------------------------------------------------------

    new_order_record = None

    if (
        missing_field is None
        and not order_state.get(
            "order_id"
        )
    ):

        order_id = generate_order_id()

        order_state[
            "order_id"
        ] = order_id

        order_state[
            "status"
        ] = "confirmed"

        order_state[
            "stage"
        ] = "confirmed"

        order_state[
            "last_asked_field"
        ] = None

        # Remember exactly how far into the conversation this order
        # was confirmed. If the customer starts a REPEAT order later,
        # the backfill step above must only look at messages sent
        # AFTER this point — otherwise details belonging to THIS
        # (now-finished) order, like a color or size mentioned only
        # in these older messages, can leak into the next order.
        order_state[
            "last_order_confirmed_index"
        ] = len(messages)

        new_order_record = build_order_record(
            order_state
        )

    # ------------------------------------------------------
    # FINAL DECISION
    # ------------------------------------------------------

    return {
        "buying_intent": True,
        "active": True,
        "stage": order_state.get(
            "stage"
        ),
        "product": order_state.get(
            "product"
        ),
        "collected": {
            field: order_state.get(
                field
            )
            for field in ORDER_FIELD_SEQUENCE
        },
        "missing_field": missing_field,
        "missing_fields": missing_fields,
        "order_id": order_state.get(
            "order_id"
        ),
        "status": order_state.get(
            "status"
        ),
        "delivery_estimate": get_delivery_estimate(),
        "new_order_record": new_order_record,
    }


# ==========================================================
# INTERNAL PROMPT FORMATTER
# ==========================================================

def format_order_prompt_text(
    decision: Optional[Dict[str, Any]],
) -> str:

    if (
        not decision
        or not decision.get(
            "active"
        )
    ):

        return (
            "No active order collection in progress. "
            "Do not start collecting order details "
            "(name, phone, address, etc.) unless the "
            "customer shows clear buying intent. "
            "Do NOT say an order is confirmed, placed, "
            "processed, or being delivered — there is "
            "no order in the system yet."
        )

    lines = [
        "ORDER DECISION — INTERNAL ONLY",
        "",
        f"Stage: {decision.get('stage')}",
        (
            "Product: "
            f"{decision.get('product') or 'not confirmed yet'}"
        ),
        "",
        "Collected so far:",
    ]

    collected = decision.get(
        "collected",
        {},
    )

    for field in ORDER_FIELD_SEQUENCE:

        value = collected.get(
            field
        )

        lines.append(
            f"- {field}: "
            f"{value if value else 'MISSING'}"
        )

    if decision.get(
        "order_id"
    ):

        lines.append("")

        lines.append(
            f"Order ID: {decision['order_id']}"
        )

        lines.append(
            "Current order status: "
            f"{decision.get('status')}"
        )

        lines.append(
            "Delivery estimate: "
            f"{decision.get('delivery_estimate')}"
        )

        lines.append("")

        lines.append(
            "INSTRUCTION: The order is fully collected "
            "and confirmed by the backend. Tell the "
            "customer their Order ID and current status "
            "exactly as given above. Mention the delivery "
            "estimate only if the order has not been "
            "delivered yet. Do not keep asking for order "
            "details. Do not claim a status more advanced "
            "than what is shown above."
        )

    else:

        missing_fields = decision.get(
            "missing_fields"
        ) or []

        labels = [
            FIELD_LABELS.get(field, field)
            for field in missing_fields
        ]

        lines.append("")

        if len(labels) <= 1:

            lines.append(
                f"INSTRUCTION: Ask the customer for their "
                f"{labels[0] if labels else 'remaining detail'} "
                "next. Do not ask for anything already "
                "collected above. If any of the fields already "
                "shown as collected came from a PREVIOUS order "
                "in this same conversation (repeat customer), "
                "briefly and naturally mention you're using "
                "their previous details — e.g. 'Pichli dafa "
                "wali details se hi order kar deta hoon' — "
                "instead of silently reusing them. Do not "
                "confirm the order, invent an Order ID, or say "
                "'order placed' until every field above is "
                "filled by the backend. This applies even if an "
                "Order ID was shown earlier in this SAME "
                "conversation for a DIFFERENT order — never "
                "repeat, reuse, or reference that earlier Order "
                "ID as confirmation for this new request. Every "
                "order confirmation must come from a fresh "
                "Order ID given by the backend for THIS request "
                "specifically."
            )

        else:

            fields_text = ", ".join(labels)

            lines.append(
                "INSTRUCTION: The customer still needs to "
                f"provide: {fields_text}. Ask for ALL of "
                "these together in a single natural message "
                "(not one at a time) so the customer doesn't "
                "have to go back and forth. Keep it friendly "
                "and readable, e.g. as a short list. Do not "
                "ask for anything already collected above. "
                "If any of the fields already shown as "
                "collected came from a PREVIOUS order in this "
                "same conversation (repeat customer), briefly "
                "and naturally mention you're using their "
                "previous details instead of silently reusing "
                "them. If the customer's next reply only "
                "provides some of these, simply ask again for "
                "whatever is still missing — do not repeat "
                "fields already given. Do not confirm the "
                "order, invent an Order ID, or say 'order "
                "placed' until every field above is filled by "
                "the backend. This applies even if an Order ID "
                "was shown earlier in this SAME conversation for "
                "a DIFFERENT order — never repeat, reuse, or "
                "reference that earlier Order ID as confirmation "
                "for this new request. Every order confirmation "
                "must come from a fresh Order ID given by the "
                "backend for THIS request specifically."
            )

    return "\n".join(
        lines
    )