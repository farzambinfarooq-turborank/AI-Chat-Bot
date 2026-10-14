import os
import json
import logging
from typing import Optional, Dict, Any

import psycopg2
from psycopg2.extras import Json


# ==========================================================
# LOGGER
# ==========================================================

logger = logging.getLogger("db")


# ==========================================================
# ENVIRONMENT
#
# DATABASE_URL is provided automatically by Railway once a
# Postgres service is added to the project (or set manually
# in the ai-chat-bot service's Variables tab).
#
# If DATABASE_URL is missing, every function below becomes a
# safe no-op so the app still runs locally without Postgres
# (falls back to pure in-memory behaviour, same as before).
# ==========================================================

DATABASE_URL = os.getenv("DATABASE_URL")


# ==========================================================
# CONNECTION
# ==========================================================

def get_connection():

    if not DATABASE_URL:
        return None

    try:

        return psycopg2.connect(
            DATABASE_URL
        )

    except Exception as e:

        logger.error(
            "Database connection failed: %s",
            e,
        )

        return None


# ==========================================================
# SCHEMA
#
# Single generic key-value table, JSON values. store_name is
# like "conversation_memory", "orders_db", etc. — mirrors the
# in-memory dict names in main.py exactly, so each dict maps
# 1:1 onto rows here.
# ==========================================================

def init_db() -> None:

    conn = get_connection()

    if not conn:

        logger.warning(
            "DATABASE_URL not set — running with in-memory "
            "storage only. Data will NOT survive a redeploy."
        )

        return

    try:

        with conn:

            with conn.cursor() as cur:

                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS kv_store (
                        store_name TEXT NOT NULL,
                        key TEXT NOT NULL,
                        value JSONB NOT NULL,
                        updated_at TIMESTAMPTZ DEFAULT now(),
                        PRIMARY KEY (store_name, key)
                    )
                    """
                )

        logger.info(
            "Database initialized successfully."
        )

    except Exception as e:

        logger.error(
            "Database init failed: %s",
            e,
        )

    finally:

        conn.close()


# ==========================================================
# LOAD ALL ROWS FOR A STORE
#
# Used once at startup to repopulate the in-memory dicts from
# whatever was last persisted, so old conversations/orders
# survive a redeploy.
# ==========================================================

def load_all(
    store_name: str,
) -> Dict[str, Any]:

    conn = get_connection()

    if not conn:
        return {}

    result: Dict[str, Any] = {}

    try:

        with conn:

            with conn.cursor() as cur:

                cur.execute(
                    "SELECT key, value FROM kv_store "
                    "WHERE store_name = %s",
                    (store_name,),
                )

                for key, value in cur.fetchall():
                    result[key] = value

    except Exception as e:

        logger.error(
            "Database load_all(%s) failed: %s",
            store_name,
            e,
        )

    finally:

        conn.close()

    return result


# ==========================================================
# SAVE ONE KEY
#
# Called after every mutation (new message, order update,
# etc.) so the change is durable immediately, not just at
# shutdown.
# ==========================================================

def save(
    store_name: str,
    key: str,
    value: Any,
) -> None:

    conn = get_connection()

    if not conn:
        return

    try:

        with conn:

            with conn.cursor() as cur:

                cur.execute(
                    """
                    INSERT INTO kv_store (store_name, key, value, updated_at)
                    VALUES (%s, %s, %s, now())
                    ON CONFLICT (store_name, key)
                    DO UPDATE SET value = EXCLUDED.value, updated_at = now()
                    """,
                    (
                        store_name,
                        key,
                        Json(value),
                    ),
                )

    except Exception as e:

        logger.error(
            "Database save(%s, %s) failed: %s",
            store_name,
            key,
            e,
        )

    finally:

        conn.close()


# ==========================================================
# DELETE ONE KEY
# ==========================================================

def delete(
    store_name: str,
    key: str,
) -> None:

    conn = get_connection()

    if not conn:
        return

    try:

        with conn:

            with conn.cursor() as cur:

                cur.execute(
                    "DELETE FROM kv_store "
                    "WHERE store_name = %s AND key = %s",
                    (
                        store_name,
                        key,
                    ),
                )

    except Exception as e:

        logger.error(
            "Database delete(%s, %s) failed: %s",
            store_name,
            key,
            e,
        )

    finally:

        conn.close()