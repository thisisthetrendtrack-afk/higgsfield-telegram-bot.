# quota_manager.py
"""
Quota & premium manager for Higgsfield bot.

Usage:
    from quota_manager import QM

    if not QM.is_allowed(chat_id):
        # reply and return
    ...
    QM.increment_usage(chat_id)

Environment:
    DATABASE_URL must be set (postgres connection string).
    TELEGRAM_TOKEN optionally set so this module can notify ADMIN_ID on DB errors.
    ADMIN_ID should be set in bot.py - we accept passing it when needed, else default None.
"""

import os
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import traceback

# Optional: read ADMIN_ID from env (bot.py will typically have ADMIN_ID const)
TRY_NOTIFY_ADMIN = True
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else None
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
DATABASE_URL = os.getenv("DATABASE_URL")

# If set to "1" (string) then NON-PREMIUM users are blocked entirely (strict mode).
# If not set or "0", module uses daily limits from plans (normal behaviour).
BLOCK_NON_PREMIUM = os.getenv("BLOCK_NON_PREMIUM", "0") == "1"

# default free daily limit (backup)
FALLBACK_FREE_DAILY = 2

# Plan mapping (keep in sync with your bot's PLANS)
PLANS = {
    "starter": {"price": 2, "duration_days": 1, "daily_limit": 10, "name": "Starter (1 day)"},
    "weekly": {"price": 10, "duration_days": 7, "daily_limit": 50, "name": "Weekly (7 days)"},
    "monthly": {"price": 25, "duration_days": 30, "daily_limit": 150, "name": "Monthly (30 days)"},
    "lifetime": {"price": 50, "duration_days": 999999, "daily_limit": None, "name": "Lifetime"}
}


def _conn():
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL environment variable is not set for quota_manager")
    return psycopg2.connect(DATABASE_URL)


def _notify_admin(msg: str):
    """Attempt to notify admin via Telegram; fail silently if not possible."""
    if not TRY_NOTIFY_ADMIN or not TELEGRAM_TOKEN or ADMIN_ID is None:
        return
    try:
        from telegram import Bot
        bot = Bot(token=TELEGRAM_TOKEN)
        bot.send_message(chat_id=ADMIN_ID, text=f"[quota_manager] {msg}")
    except Exception:
        # don't raise in library code
        pass


def ensure_tables():
    """Create minimal tables if they don't exist (safe to call at startup)."""
    try:
        conn = _conn()
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS users (
                chat_id BIGINT PRIMARY KEY,
                count INT DEFAULT 0,
                date DATE DEFAULT CURRENT_DATE,
                plan_type VARCHAR(20),
                plan_expiry TIMESTAMP
            )
        """)
        # Keep other tables creation elsewhere (bot.init_db) if needed
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _notify_admin(f"ensure_tables DB error: {e}\n{traceback.format_exc()}")


def get_user_row(chat_id):
    """Return user row dict or None."""
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row
    except Exception as e:
        _notify_admin(f"get_user_row DB error: {e}\n{traceback.format_exc()}")
        return None


def get_user_daily_limit(chat_id):
    """
    Return daily limit for user:
     - None means unlimited (e.g., lifetime)
     - integer for max daily usage
    """
    if chat_id == ADMIN_ID:
        return None
    row = get_user_row(chat_id)
    if not row:
        # fallback free daily value
        return FALLBACK_FREE_DAILY
    # if plan_expiry present and in future -> use that plan's limit
    plan_expiry = row.get("plan_expiry")
    if plan_expiry:
        try:
            if isinstance(plan_expiry, str):
                plan_expiry_dt = datetime.fromisoformat(plan_expiry)
            else:
                plan_expiry_dt = plan_expiry
            if datetime.now() < plan_expiry_dt:
                plan_type = row.get("plan_type") or "starter"
                return PLANS.get(plan_type, {}).get("daily_limit", FALLBACK_FREE_DAILY)
        except Exception:
            # if parse fails, fallback
            pass
    # no active plan -> free daily
    return FALLBACK_FREE_DAILY


def is_premium(chat_id):
    """Return True if user currently has an active premium plan."""
    row = get_user_row(chat_id)
    if not row:
        return False
    plan_expiry = row.get("plan_expiry")
    if not plan_expiry:
        return False
    try:
        if isinstance(plan_expiry, str):
            plan_dt = datetime.fromisoformat(plan_expiry)
        else:
            plan_dt = plan_expiry
        return datetime.now() < plan_dt
    except Exception:
        return False


def is_allowed(chat_id):
    """
    Main check to decide whether to allow generation.
    - If BLOCK_NON_PREMIUM True: only allow if premium or admin.
    - Else enforce daily limit (return True if user under limit).
    Returns True if allowed, False if blocked.
    """
    # admin always allowed
    if chat_id == ADMIN_ID:
        return True

    # Strict mode: block non-premium
    if BLOCK_NON_PREMIUM:
        if is_premium(chat_id):
            return True
        return False

    # Normal mode: check daily counter & limit
    try:
        conn = _conn()
        cur = conn.cursor(cursor_factory=RealDictCursor)
        today = datetime.now().strftime("%Y-%m-%d")
        # ensure user row exists
        cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
        row = cur.fetchone()
        if not row:
            cur.execute("INSERT INTO users (chat_id, count, date) VALUES (%s, 0, %s) ON CONFLICT (chat_id) DO NOTHING", (chat_id, today))
            conn.commit()
            cur.close()
            conn.close()
            return True

        # reset if different date
        if row.get("date") != today:
            cur.execute("UPDATE users SET count = 0, date = %s WHERE chat_id = %s", (today, chat_id))
            conn.commit()
            # refresh row
            cur.execute("SELECT * FROM users WHERE chat_id = %s", (chat_id,))
            row = cur.fetchone()

        daily_limit = get_user_daily_limit(chat_id)
        if daily_limit is None:
            cur.close()
            conn.close()
            return True

        if row.get("count", 0) >= daily_limit:
            cur.close()
            conn.close()
            return False

        cur.close()
        conn.close()
        return True
    except Exception as e:
        # notify and DENY by default (safer); change to return True if you want allow-by-default
        _notify_admin(f"is_allowed DB error: {e}\n{traceback.format_exc()}")
        return False


def increment_usage(chat_id):
    """
    Atomically increment usage counter for today. Safe to call after generation success.
    """
    if chat_id == ADMIN_ID:
        return
    try:
        conn = _conn()
        cur = conn.cursor()
        # make sure row exists first
        cur.execute("INSERT INTO users (chat_id, count, date) VALUES (%s, 0, CURRENT_DATE) ON CONFLICT (chat_id) DO NOTHING", (chat_id,))
        cur.execute("UPDATE users SET count = count + 1 WHERE chat_id = %s", (chat_id,))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        _notify_admin(f"increment_usage DB error: {e}\n{traceback.format_exc()}")


def get_remaining(chat_id):
    """Return (remaining_count, daily_limit) where remaining_count is int or None for unlimited."""
    try:
        if chat_id == ADMIN_ID:
            return (None, None)
        row = get_user_row(chat_id)
        daily_limit = get_user_daily_limit(chat_id)
        if daily_limit is None:
            return (None, None)
        used = 0
        if row:
            used = row.get("count", 0)
        remaining = max(0, daily_limit - used)
        return (remaining, daily_limit)
    except Exception as e:
        _notify_admin(f"get_remaining DB error: {e}\n{traceback.format_exc()}")
        return (None, None)


# single-access instance for convenient import
QM = type("QM", (), {
    "ensure_tables": staticmethod(ensure_tables),
    "is_allowed": staticmethod(is_allowed),
    "increment_usage": staticmethod(increment_usage),
    "get_remaining": staticmethod(get_remaining),
    "is_premium": staticmethod(is_premium),
    "get_user_daily_limit": staticmethod(get_user_daily_limit),
})
