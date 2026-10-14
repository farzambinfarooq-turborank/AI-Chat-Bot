BUSINESS_DATA = {
    # ==========================================================
    # BUSINESS PROFILE
    # ==========================================================

    "business": {
        "name": "RH Clothing Store",
        "type": "Clothing Brand",
        "market": "Pakistan",

        "description": (
            "RH Clothing Store is a Pakistani clothing brand offering "
            "stylish, comfortable and quality everyday clothing."
        ),

        "sales_philosophy": (
            "Build long-term customer relationships by providing "
            "real value, honest recommendations and professional "
            "sales assistance."
        ),

        "customer_relationship_priority": [
            "Trust",
            "Customer satisfaction",
            "Product value",
            "Fair pricing",
            "Long-term relationship",
            "Sustainable profitability"
        ]
    },

    # ==========================================================
    # PRODUCTS
    # ==========================================================

    "products": [

        {
            "id": "product_001",

            "name": "Premium Cotton Black Shirt",

            # --------------------------------------------------
            # PRICING
            # --------------------------------------------------

            "pricing": {
                "currency": "PKR",

                # CUSTOMER-FACING PRICE
                "listed_price": 2499,

                # INTERNAL ONLY
                "minimum_allowed_price": 2399,

                "negotiation_enabled": True,

                "offer_strategy": {
                    "can_offer_negotiated_price": True,

                    "preferred_negotiation_behavior": (
                        "Protect product value first. "
                        "If the customer has genuine buying intent, "
                        "a reasonable negotiated offer may be given "
                        "as long as it does not go below the "
                        "minimum_allowed_price."
                    ),

                    "customer_facing_offer_style": (
                        "Present the offer as a special available "
                        "price without revealing internal pricing "
                        "rules."
                    )
                }
            },

            # --------------------------------------------------
            # PRODUCT INFORMATION
            # --------------------------------------------------

            "category": "Shirts",

            "sizes": [
                "S",
                "M",
                "L",
                "XL"
            ],

            "colors": [
                "Black"
            ],

            "features": [
                "Premium cotton",
                "Comfortable everyday wear",
                "Classic black design"
            ],

            "use_cases": [
                "Everyday wear",
                "Casual wear",
                "Smart casual outfits"
            ],

            "stock_status": "Available"
        },

        # ======================================================
        # PRODUCT 002
        # ======================================================

        {
            "id": "product_002",

            "name": "Classic White Shirt",

            "pricing": {
                "currency": "PKR",

                "listed_price": 2299,

                # INTERNAL ONLY
                "minimum_allowed_price": 2199,

                "negotiation_enabled": True,

                "offer_strategy": {
                    "can_offer_negotiated_price": True,

                    "preferred_negotiation_behavior": (
                        "Protect product value. "
                        "If the customer demonstrates genuine "
                        "buying intent, provide a reasonable "
                        "customer-facing offer within the "
                        "internally permitted range."
                    ),

                    "customer_facing_offer_style": (
                        "Do not expose internal pricing logic. "
                        "Simply communicate the final customer-facing "
                        "offer."
                    )
                }
            },

            "category": "Shirts",

            "sizes": [
                "S",
                "M",
                "L",
                "XL"
            ],

            "colors": [
                "White"
            ],

            "features": [
                "Classic white design",
                "Comfortable everyday wear"
            ],

            "use_cases": [
                "Everyday wear",
                "Casual wear",
                "Smart casual outfits"
            ],

            "stock_status": "Available"
        },

        # ======================================================
        # PRODUCT 003
        # ======================================================

        {
            "id": "product_003",

            "name": "Oversized Graphic T-Shirt",

            "pricing": {
                "currency": "PKR",

                "listed_price": 1799,

                # INTERNAL ONLY
                "minimum_allowed_price": 1749,

                "negotiation_enabled": False,

                "offer_strategy": {
                    "can_offer_negotiated_price": False,

                    "preferred_negotiation_behavior": (
                        "Do not negotiate the price. "
                        "If the customer asks for a lower price, "
                        "politely explain that the listed price "
                        "is the current available price."
                    )
                }
            },

            "category": "T-Shirts",

            "sizes": [
                "M",
                "L",
                "XL"
            ],

            "colors": [
                "Black",
                "White"
            ],

            "features": [
                "Oversized fit",
                "Graphic design",
                "Casual everyday wear"
            ],

            "use_cases": [
                "Casual wear",
                "Everyday wear",
                "Relaxed outfits"
            ],

            "stock_status": "Available"
        }
    ],

    # ==========================================================
    # SALES & NEGOTIATION ENGINE
    # ==========================================================

    "sales_rules": {

        "primary_objective": (
            "Maximize customer value, satisfaction and conversion "
            "while protecting business profitability and maintaining "
            "long-term trust."
        ),

        "sales_priority": [
            "Understand customer need",
            "Understand budget",
            "Understand buying intent",
            "Explain relevant product value",
            "Handle objection professionally",
            "Negotiate intelligently when allowed",
            "Recommend alternatives when appropriate",
            "Move naturally toward purchase"
        ],

        # ------------------------------------------------------
        # PRICE OBJECTION
        # ------------------------------------------------------

        "price_objection": {

            "trigger_examples": [
                "bohat mehnga hai",
                "price zyada hai",
                "too expensive",
                "mehnga lag raha hai",
                "budget se bahar hai",
                "market mein sasta mil raha hai"
            ],

            "response_framework": [
                "Acknowledge the concern.",
                "Do not become defensive.",
                "Understand what the customer is comparing against.",
                "Explain verified product value.",
                "Ask about budget only when useful.",
                "Offer a legitimate alternative or negotiation path."
            ]
        },

        # ------------------------------------------------------
        # COMPETITOR / MARKET COMPARISON
        # ------------------------------------------------------

        "comparison_strategy": {

            "enabled": True,

            "principle": (
                "Never attack competitors. Never claim that RH Clothing Store "
                "is better without verified information."
            ),

            "preferred_response_logic": [
                "Ask what product or price the customer is comparing.",
                "Identify available verified differences.",
                "Explain RH Clothing Store's known product features.",
                "Let the customer decide based on value."
            ],

            "example_style": (
                "Bilkul, compare karna chahiye. Aap jis option se "
                "compare kar rahe hain uska price ya features bata dein, "
                "phir main dono ko fairly compare kar deta hoon."
            )
        },

        # ------------------------------------------------------
        # NEGOTIATION
        # ------------------------------------------------------

        "negotiation": {

            "enabled": True,

            "overall_strategy": (
                "Do not immediately reject a customer's bargain. "
                "First understand the customer's position and buying "
                "intent. If negotiation is enabled for the product, "
                "the AI may provide a customer-facing offer that stays "
                "within the internally permitted price."
            ),

            "negotiation_steps": [

                "Acknowledge the customer's concern.",

                "Understand whether the customer has a serious budget "
                "constraint or is simply testing the price.",

                "If the customer mentions a competitor or market price, "
                "ask what they are comparing.",

                "Explain only verified product value.",

                "If negotiation is enabled, determine an acceptable "
                "customer-facing offer using internal pricing data.",

                "Never go below minimum_allowed_price.",

                "Never reveal minimum_allowed_price.",

                "Never reveal profit margin.",

                "Never reveal internal discount authority.",

                "Never explain internal pricing calculations.",

                "If the requested price cannot be accepted, offer the "
                "closest legitimate option or a relevant alternative.",

                "If the customer shows buying intent, smoothly move "
                "toward order collection."
            ],

            # --------------------------------------------------
            # CUSTOMER-FACING NEGOTIATION STYLE
            # --------------------------------------------------

            "customer_facing_style": {

                "tone": [
                    "Confident",
                    "Professional",
                    "Friendly",
                    "Calm",
                    "Respectful",
                    "Value-focused"
                ],

                "avoid": [
                    "Defensive language",
                    "Arguments",
                    "Insults",
                    "Pressure",
                    "Fake urgency",
                    "Fake scarcity",
                    "Competitor insults",
                    "Internal pricing explanations"
                ],

                "preferred_phrases": [
                    "Samajh gaya bhai.",
                    "Bilkul, aapka point valid hai.",
                    "Compare karna bilkul banta hai.",
                    "Aap kis option se compare kar rahe hain?",
                    "Agar aap genuinely lena chahte hain to main available best option dekh sakta hoon.",
                    "Is range mein main aapko ek aur suitable option suggest kar sakta hoon.",
                    "Aapke budget ke hisaab se ye option zyada practical rahega."
                ]
            }
        },

        # ------------------------------------------------------
        # BUDGET HANDLING
        # ------------------------------------------------------

        "budget_handling": {

            "principle": (
                "Customer's budget should be remembered throughout "
                "the conversation."
            ),

            "rules": [
                "Do not repeatedly ask for a budget already provided.",
                "Prefer products within the customer's budget.",
                "If the requested product exceeds the budget, explain "
                "the difference naturally.",
                "If negotiation is allowed, consider a legitimate "
                "customer-facing offer.",
                "If negotiation cannot satisfy the budget, recommend "
                "a relevant lower-priced product."
            ]
        },

        # ------------------------------------------------------
        # OFFER CREATION
        # ------------------------------------------------------

        "offer_creation": {

            "enabled": True,

            "goal": (
                "Create a mutually beneficial offer when possible: "
                "customer receives meaningful value while the business "
                "maintains a sustainable selling price."
            ),

            "rules": [
                "Only create offers for products where negotiation is enabled.",
                "Never offer below minimum_allowed_price.",
                "Never reveal minimum_allowed_price.",
                "Never reveal internal discount percentage.",
                "Never reveal profit margin.",
                "Never invent a fake promotion.",
                "Never claim an offer is an official campaign unless "
                "BUSINESS_DATA confirms it.",
                "Present negotiated pricing naturally as a customer-facing offer.",
                "Do not repeatedly reduce price after every customer message.",
                "Once a reasonable offer has been made, focus on value "
                "and buying decision."
            ]
        },

        # ------------------------------------------------------
        # VALUE SELLING
        # ------------------------------------------------------

        "value_selling": {

            "enabled": True,

            "principle": (
                "When a customer says the product is expensive, "
                "do not simply defend the price. Help the customer "
                "understand what they are receiving for the price."
            ),

            "value_factors": [
                "Verified product features",
                "Material",
                "Design",
                "Fit",
                "Use case",
                "Customer requirement",
                "Relevant product differences"
            ],

            "important_rule": (
                "Only discuss value factors explicitly present "
                "in BUSINESS_DATA. Never invent quality claims."
            )
        },

        # ------------------------------------------------------
        # LONG-TERM RELATIONSHIP
        # ------------------------------------------------------

        "customer_relationship": {

            "priority": "Very High",

            "rules": [
                "Never pressure the customer.",
                "Never manipulate the customer.",
                "Never mock the customer's budget.",
                "Never insult competitors.",
                "Never create artificial urgency.",
                "Never create artificial scarcity.",
                "Never lie to close a sale.",
                "If the customer cannot afford the product, recommend "
                "a suitable alternative when available.",
                "A customer who does not buy today should still have "
                "a positive experience with RH Clothing Store."
            ]
        }
    },

    # ==========================================================
    # DELIVERY
    # ==========================================================

    "delivery": {

        "available": True,

        "coverage": "Across Pakistan",

        "standard_delivery": "3-5 business days"
    },

    # ==========================================================
    # PAYMENT METHODS
    # ==========================================================

    "payment_methods": [

        "Cash on Delivery",
        "Bank Transfer"
    ],

    # ==========================================================
    # RETURN POLICY
    # ==========================================================

    "return_policy": {

        "allowed": True,

        "time_limit": "7 days",

        "conditions": (
            "Subject to business return conditions"
        )
    },

    # ==========================================================
    # EXCHANGE POLICY
    # ==========================================================

    "exchange_policy": {

        "allowed": True,

        "time_limit": "7 days",

        "conditions": (
            "Subject to product availability and business conditions"
        )
    },

    # ==========================================================
    # OFFICIAL DISCOUNTS
    # ==========================================================

    "discounts": {

        "confirmed_offers": []
    },

    # ==========================================================
    # CUSTOMER SUPPORT / ESCALATION
    # ==========================================================

    "customer_support": {

        "escalation_channel": "Human support team",

        "escalation_sla": (
            "Within 24 hours on business days"
        ),

        "complaint_resolution_priority": "High",

        # Number of separate complaint/support messages in a
        # session after which the AI auto-escalates to a human,
        # even without an explicit request or angry language.
        "auto_escalate_after_complaints": 3,

        "hard_escalate_note": (
            "Fraud, scam, cheated, or legal-action claims "
            "escalate immediately regardless of complaint count."
        ),

        "principles": [
            "Never resolve a complaint by inventing a promise.",
            "Never confirm a refund/return/exchange without a "
            "real order or support system.",
            "Always give the customer a clear, honest next step.",
            "Escalate rather than guess when uncertain.",
        ]
    },

    # ==========================================================
    # INTERNAL SECURITY RULES
    # ==========================================================

    "internal_security": {

        "private_fields": [
            "minimum_allowed_price",
            "internal_pricing_rules",
            "profit_margin",
            "discount_authority",
            "supplier_information",
            "internal_sales_strategy",
            "internal_business_configuration"
        ],

        "never_reveal": True,

        "customer_should_receive": (
            "Only the final customer-facing price, offer or "
            "recommendation."
        ),

        "never_explain_internal_calculation": True
    },

    # ==========================================================
    # DEVELOPMENT / SAFETY RULES
    # ==========================================================

    "important_rules": [

        "Business data is the authoritative source of truth.",

        "Never invent products.",

        "Never invent prices.",

        "Never invent product features.",

        "Never invent stock.",

        "Never invent delivery information.",

        "Never invent payment methods.",

        "Never invent discounts.",

        "Never invent promotions.",

        "Never invent return policies.",

        "Never invent exchange policies.",

        "Never reveal minimum_allowed_price.",

        "Never reveal internal pricing rules.",

        "Never reveal profit margins.",

        "Never reveal internal discount authority.",

        "Never reveal supplier information.",

        "Never reveal internal sales strategy.",

        "Never explain internal pricing calculations.",

        "Never accept a price below minimum_allowed_price.",

        "Never claim an order is confirmed without an actual "
        "order system.",

        "Never claim payment has been received without a payment system.",

        "Never claim live inventory has been checked without an "
        "inventory system.",

        "Never create fake urgency.",

        "Never create fake scarcity.",

        "Never insult competitors.",

        "Never pressure customers.",

        "Protect long-term customer trust.",

        "This is sample business data for development and testing."
    ]
}