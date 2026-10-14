from .business_data import BUSINESS_DATA


def search_business_knowledge(query: str) -> str:

    query_lower = query.lower().strip()

    results = []

    # ======================================================
    # PRODUCTS
    # ======================================================

    for product in BUSINESS_DATA.get("products", []):

        searchable = [
            product.get("name", ""),
            *product.get("sizes", []),
            *product.get("colors", []),
            *product.get("features", []),
            *product.get("use_cases", []),
        ]

        searchable_text = " ".join(
            searchable
        ).lower()

        query_words = query_lower.split()

        if any(
            word in searchable_text
            for word in query_words
            if len(word) > 2
        ):

            results.append({
                "type": "product",
                "data": product,
            })


    # ======================================================
    # DELIVERY
    # ======================================================

    delivery_keywords = [
        "delivery",
        "deliver",
        "shipping",
        "ship",
        "kitne din",
        "kab milega",
        "courier",
    ]

    if any(
        keyword in query_lower
        for keyword in delivery_keywords
    ):

        results.append({
            "type": "delivery",
            "data": BUSINESS_DATA.get(
                "delivery",
                {}
            ),
        })


    # ======================================================
    # PAYMENT
    # ======================================================

    payment_keywords = [
        "payment",
        "cod",
        "cash on delivery",
        "bank transfer",
        "easypaisa",
        "jazzcash",
    ]

    if any(
        keyword in query_lower
        for keyword in payment_keywords
    ):

        results.append({
            "type": "payment",
            "data": BUSINESS_DATA.get(
                "payment_methods",
                []
            ),
        })


    # ======================================================
    # RETURN
    # ======================================================

    return_keywords = [
        "return",
        "wapas",
        "refund",
    ]

    if any(
        keyword in query_lower
        for keyword in return_keywords
    ):

        results.append({
            "type": "return",
            "data": BUSINESS_DATA.get(
                "return_policy",
                {}
            ),
        })


    # ======================================================
    # EXCHANGE
    # ======================================================

    exchange_keywords = [
        "exchange",
        "replace",
        "size change",
        "badal",
    ]

    if any(
        keyword in query_lower
        for keyword in exchange_keywords
    ):

        results.append({
            "type": "exchange",
            "data": BUSINESS_DATA.get(
                "exchange_policy",
                {}
            ),
        })


    # ======================================================
    # DISCOUNTS
    # ======================================================

    discount_keywords = [
        "discount",
        "sale",
        "offer",
        "coupon",
        "promo",
        "promotion",
    ]

    if any(
        keyword in query_lower
        for keyword in discount_keywords
    ):

        results.append({
            "type": "discount",
            "data": BUSINESS_DATA.get(
                "discounts",
                {}
            ),
        })


    # ======================================================
    # NO MATCH
    # ======================================================

    if not results:

        return (
            "No specific business information was found. "
            "Do not guess or invent an answer."
        )


    # ======================================================
    # FORMAT
    # ======================================================

    output = [
        "RELEVANT BUSINESS KNOWLEDGE:"
    ]

    for item in results:

        output.append(
            f"\n{item['type'].upper()}:"
        )

        output.append(
            str(item["data"])
        )

    return "\n".join(output)