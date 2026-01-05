import logging
import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterable

DB_NAME = "donation_bot.db"

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES: tuple[str, ...] = ("UAH", "RUB", "USD")
DONATION_ENABLED_CURRENCIES_KEY = "donation_enabled_currencies"


@dataclass(frozen=True)
class Stats:
    total_raised: float
    pending_reviews: int
    total_donors: int


class Database:
    def __init__(self, db_path: str = DB_NAME):
        self.db_path = db_path

    def connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        return conn

    @contextmanager
    def _conn(self, *, commit: bool = False):
        conn = self.connect()
        try:
            yield conn
            if commit:
                conn.commit()
        finally:
            conn.close()

    def _table_columns(self, conn: sqlite3.Connection, table_name: str) -> set[str]:
        cur = conn.cursor()
        cur.execute(f"PRAGMA table_info({table_name})")
        return {row[1] for row in cur.fetchall()}

    def init(self) -> None:
        with self._conn(commit=True) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS users (
                    user_id INTEGER PRIMARY KEY,
                    username TEXT,
                    first_name TEXT,
                    language TEXT,
                    preferred_referrer_id INTEGER,
                    joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    amount REAL,
                    currency TEXT,
                    status TEXT DEFAULT 'pending',
                    proof_image_id TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    referrer_id INTEGER,
                    FOREIGN KEY (user_id) REFERENCES users (user_id)
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS settings (
                    key TEXT PRIMARY KEY,
                    value TEXT
                )
                """
            )
            cur.execute(
                """
                CREATE TABLE IF NOT EXISTS cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    details TEXT NOT NULL,
                    currency TEXT DEFAULT 'USD',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
                """
            )

            users_cols = self._table_columns(conn, "users")
            if "language" not in users_cols:
                cur.execute("ALTER TABLE users ADD COLUMN language TEXT")
            if "preferred_referrer_id" not in users_cols:
                cur.execute("ALTER TABLE users ADD COLUMN preferred_referrer_id INTEGER")

            tx_cols = self._table_columns(conn, "transactions")
            if "referrer_id" not in tx_cols:
                cur.execute("ALTER TABLE transactions ADD COLUMN referrer_id INTEGER")
            if "currency" not in tx_cols:
                cur.execute("ALTER TABLE transactions ADD COLUMN currency TEXT")

            cards_cols = self._table_columns(conn, "cards")
            if "currency" not in cards_cols:
                cur.execute("ALTER TABLE cards ADD COLUMN currency TEXT DEFAULT 'USD'")
            
            # migrate legacy single active_card setting into cards if needed
            cards_count_row = cur.execute("SELECT COUNT(*) FROM cards").fetchone()
            cards_count = int(cards_count_row[0] or 0) if cards_count_row else 0
            if cards_count == 0:
                legacy_row = cur.execute(
                    "SELECT value FROM settings WHERE key = 'active_card'"
                ).fetchone()
                if legacy_row and legacy_row[0]:
                    cur.execute(
                        "INSERT INTO cards (details, is_active, currency) VALUES (?, 1, 'USD')",
                        (legacy_row[0],),
                    )

            enabled_row = cur.execute(
                "SELECT value FROM settings WHERE key = ?",
                (DONATION_ENABLED_CURRENCIES_KEY,),
            ).fetchone()
            if not enabled_row:
                cur.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (DONATION_ENABLED_CURRENCIES_KEY, ",".join(SUPPORTED_CURRENCIES)),
                )

    def execute(self, sql: str, params: Iterable[Any] = (), *, commit: bool = False) -> None:
        with self._conn(commit=commit) as conn:
            conn.execute(sql, tuple(params))

    def fetchone(self, sql: str, params: Iterable[Any] = ()) -> tuple[Any, ...] | None:
        with self._conn() as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.fetchone()

    def fetchall(self, sql: str, params: Iterable[Any] = ()) -> list[tuple[Any, ...]]:
        with self._conn() as conn:
            cur = conn.execute(sql, tuple(params))
            return cur.fetchall()

    def add_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        try:
            self.execute(
                "INSERT OR IGNORE INTO users (user_id, username, first_name) VALUES (?, ?, ?)",
                (user_id, username, first_name),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error adding user: {e}")

    def get_all_users(self) -> list[int]:
        return [row[0] for row in self.fetchall("SELECT user_id FROM users")]

    def create_transaction(self, user_id: int, amount: float, referrer_id: int | None = None, currency: str = "USD") -> int | None:
        with self._conn(commit=True) as conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO transactions (user_id, amount, currency, status, referrer_id) VALUES (?, ?, ?, 'pending_proof', ?)",
                    (user_id, amount, currency, referrer_id),
                )
                return int(cur.lastrowid)
            except Exception as e:
                logger.error(f"Error creating transaction: {e}")
                return None

    def update_transaction_proof(self, transaction_id: int, proof_image_id: str) -> None:
        try:
            self.execute(
                "UPDATE transactions SET proof_image_id = ?, status = 'pending_approval' WHERE id = ?",
                (proof_image_id, transaction_id),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error updating transaction proof: {e}")

    def update_transaction_status(self, transaction_id: int, status: str) -> None:
        try:
            self.execute(
                "UPDATE transactions SET status = ? WHERE id = ?",
                (status, transaction_id),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error updating transaction status: {e}")

    def get_transaction(self, transaction_id: int) -> tuple[Any, ...] | None:
        return self.fetchone("SELECT * FROM transactions WHERE id = ?", (transaction_id,))

    def get_user_history(self, user_id: int) -> list[tuple[Any, ...]]:
        return self.fetchall(
            """
            SELECT id, amount, status, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT 10
            """,
            (user_id,),
        )

    def delete_transaction(self, transaction_id: int) -> None:
        try:
            self.execute(
                "DELETE FROM transactions WHERE id = ?",
                (transaction_id,),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error deleting transaction: {e}")

    def set_active_card(self, card_details: str) -> None:
        try:
            self.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('active_card', ?)",
                (card_details,),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error setting active card: {e}")

    def get_active_card(self) -> str:
        row = self.fetchone("SELECT value FROM settings WHERE key = 'active_card'")
        return row[0] if row else "No card set. Contact admin."
 
    def add_card(self, details: str, active: bool = True, currency: str = "USD") -> int | None:
        with self._conn(commit=True) as conn:
            try:
                cur = conn.cursor()
                cur.execute(
                    "INSERT INTO cards (details, is_active, currency) VALUES (?, ?, ?)",
                    (details, 1 if active else 0, currency),
                )
                return int(cur.lastrowid)
            except Exception as e:
                logger.error(f"Error adding card: {e}")
                return None
 
    def list_cards(self, active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
        where = ""
        params: list[Any] = []
        if active_only is True:
            where = "WHERE is_active = 1"
        elif active_only is False:
            where = "WHERE is_active = 0"
        return self.fetchall(
            f"""
            SELECT id, details, is_active, created_at, currency
            FROM cards
            {where}
            ORDER BY created_at DESC
            """,
            params,
        )
 
    def set_card_active(self, card_id: int, active: bool) -> None:
        try:
            self.execute(
                "UPDATE cards SET is_active = ? WHERE id = ?",
                (1 if active else 0, card_id),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error updating card active state: {e}")
 
    def delete_card(self, card_id: int) -> None:
        try:
            self.execute("DELETE FROM cards WHERE id = ?", (card_id,), commit=True)
        except Exception as e:
            logger.error(f"Error deleting card: {e}")
 
    def get_active_cards(self) -> list[str]:
        rows = self.fetchall("SELECT details FROM cards WHERE is_active = 1 ORDER BY created_at DESC")
        return [r[0] for r in rows]
 
    def get_next_active_card(self, currency: str = "USD") -> str | None:
        with self._conn(commit=True) as conn:
            try:
                cur = conn.cursor()
                rows = cur.execute(
                    "SELECT id, details FROM cards WHERE is_active = 1 AND currency = ? ORDER BY created_at ASC, id ASC",
                    (currency,)
                ).fetchall()
                if not rows:
                    return None
                count = len(rows)
                # We need a separate pointer per currency to rotate fairly
                ptr_key = f'card_rr_pointer_{currency}'
                ptr_row = cur.execute(
                    "SELECT value FROM settings WHERE key = ?", (ptr_key,)
                ).fetchone()
                try:
                    ptr = int(ptr_row[0]) if ptr_row and ptr_row[0] is not None else 0
                except Exception:
                    ptr = 0
                ptr = ptr % count
                chosen = rows[ptr][1]
                next_ptr = (ptr + 1) % count
                cur.execute(
                    "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                    (ptr_key, str(next_ptr)),
                )
                return chosen
            except Exception as e:
                logger.error(f"Error getting next active card: {e}")
                return None

    def set_support_message(self, message: str) -> None:
        try:
            self.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES ('support_message', ?)",
                (message,),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error setting support message: {e}")

    def get_support_message(self) -> str | None:
        row = self.fetchone("SELECT value FROM settings WHERE key = 'support_message'")
        return row[0] if row and row[0] else None

    def get_enabled_donation_currencies(self) -> list[str]:
        row = self.fetchone(
            "SELECT value FROM settings WHERE key = ?",
            (DONATION_ENABLED_CURRENCIES_KEY,),
        )
        if not row or not row[0]:
            self.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (DONATION_ENABLED_CURRENCIES_KEY, ",".join(SUPPORTED_CURRENCIES)),
                commit=True,
            )
            return list(SUPPORTED_CURRENCIES)
        raw = str(row[0])
        values = [v.strip().upper() for v in raw.split(",") if v.strip()]
        allowed = [v for v in values if v in SUPPORTED_CURRENCIES]
        if not allowed:
            return []
        if allowed != values:
            self.execute(
                "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
                (DONATION_ENABLED_CURRENCIES_KEY, ",".join(allowed)),
                commit=True,
            )
        return allowed

    def set_donation_currency_enabled(self, currency: str, enabled: bool) -> list[str]:
        ccy = (currency or "").strip().upper()
        if ccy not in SUPPORTED_CURRENCIES:
            return self.get_enabled_donation_currencies()
        enabled_list = self.get_enabled_donation_currencies()
        enabled_set = set(enabled_list)
        if enabled:
            enabled_set.add(ccy)
        else:
            enabled_set.discard(ccy)
        ordered = [c for c in SUPPORTED_CURRENCIES if c in enabled_set]
        self.execute(
            "INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)",
            (DONATION_ENABLED_CURRENCIES_KEY, ",".join(ordered)),
            commit=True,
        )
        return ordered

    def is_donation_currency_enabled(self, currency: str) -> bool:
        ccy = (currency or "").strip().upper()
        if ccy not in SUPPORTED_CURRENCIES:
            return False
        return ccy in set(self.get_enabled_donation_currencies())

    def get_stats(self) -> Stats:
        total_amount_row = self.fetchone("SELECT SUM(amount) FROM transactions WHERE status = 'approved'")
        total_amount = float(total_amount_row[0] or 0.0) if total_amount_row else 0.0

        pending_row = self.fetchone("SELECT COUNT(*) FROM transactions WHERE status = 'pending_approval'")
        pending_count = int(pending_row[0] or 0) if pending_row else 0

        donor_row = self.fetchone(
            "SELECT COUNT(DISTINCT user_id) FROM transactions WHERE status = 'approved'"
        )
        donor_count = int(donor_row[0] or 0) if donor_row else 0

        return Stats(total_raised=total_amount, pending_reviews=pending_count, total_donors=donor_count)

    def get_user_total_donated(self, user_id: int) -> float:
        row = self.fetchone(
            "SELECT SUM(amount) FROM transactions WHERE user_id = ? AND status = 'approved'",
            (user_id,),
        )
        return float(row[0] or 0.0) if row else 0.0

    def get_user(self, user_id: int) -> tuple[Any, ...] | None:
        return self.fetchone("SELECT user_id, username, first_name FROM users WHERE user_id = ?", (user_id,))

    def set_user_language(self, user_id: int, lang: str) -> None:
        try:
            self.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id), commit=True)
        except Exception as e:
            logger.error(f"Error setting user language: {e}")

    def get_user_language(self, user_id: int) -> str | None:
        row = self.fetchone("SELECT language FROM users WHERE user_id = ?", (user_id,))
        return row[0] if row and row[0] else None

    def set_user_preferred_referrer(self, user_id: int, referrer_id: int | None) -> None:
        try:
            self.execute(
                "UPDATE users SET preferred_referrer_id = ? WHERE user_id = ?",
                (referrer_id, user_id),
                commit=True,
            )
        except Exception as e:
            logger.error(f"Error setting preferred referrer: {e}")

    def get_user_preferred_referrer(self, user_id: int) -> int | None:
        row = self.fetchone("SELECT preferred_referrer_id FROM users WHERE user_id = ?", (user_id,))
        return int(row[0]) if row and row[0] is not None else None


_db = Database(DB_NAME)


def get_connection():
    return _db.connect()


def init_db():
    _db.init()


def add_user(user_id, username, first_name):
    _db.add_user(user_id, username, first_name)


def get_all_users():
    return _db.get_all_users()


def create_transaction(user_id, amount, referrer_id=None, currency="USD"):
    return _db.create_transaction(user_id, amount, referrer_id, currency)


def update_transaction_proof(transaction_id, proof_image_id):
    _db.update_transaction_proof(transaction_id, proof_image_id)


def update_transaction_status(transaction_id, status):
    _db.update_transaction_status(transaction_id, status)


def get_transaction(transaction_id):
    return _db.get_transaction(transaction_id)


def get_user_history(user_id):
    return _db.get_user_history(user_id)

def delete_transaction(transaction_id: int) -> None:
    _db.delete_transaction(transaction_id)


def set_active_card(card_details):
    _db.set_active_card(card_details)


def get_active_card():
    return _db.get_active_card()
 
def add_card(details: str, active: bool = True, currency: str = "USD") -> int | None:
    return _db.add_card(details, active, currency)
 
def list_cards(active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
    return _db.list_cards(active_only)
 
def set_card_active(card_id: int, active: bool) -> None:
    _db.set_card_active(card_id, active)
 
def delete_card(card_id: int) -> None:
    _db.delete_card(card_id)
 
def get_active_cards() -> list[str]:
    return _db.get_active_cards()
 
def get_next_active_card(currency: str = "USD") -> str | None:
    return _db.get_next_active_card(currency)

def set_support_message(message: str) -> None:
    _db.set_support_message(message)

def get_support_message() -> str | None:
    return _db.get_support_message()

def get_enabled_donation_currencies() -> list[str]:
    return _db.get_enabled_donation_currencies()

def set_donation_currency_enabled(currency: str, enabled: bool) -> list[str]:
    return _db.set_donation_currency_enabled(currency, enabled)

def is_donation_currency_enabled(currency: str) -> bool:
    return _db.is_donation_currency_enabled(currency)


def get_stats():
    stats = _db.get_stats()
    return {
        "total_raised": stats.total_raised,
        "pending_reviews": stats.pending_reviews,
        "total_donors": stats.total_donors,
    }


def get_user_total_donated(user_id):
    return _db.get_user_total_donated(user_id)


def get_user(user_id):
    return _db.get_user(user_id)


def set_user_language(user_id, lang):
    _db.set_user_language(user_id, lang)


def get_user_language(user_id):
    return _db.get_user_language(user_id)

def set_user_preferred_referrer(user_id: int, referrer_id: int | None) -> None:
    _db.set_user_preferred_referrer(user_id, referrer_id)

def get_user_preferred_referrer(user_id: int) -> int | None:
    return _db.get_user_preferred_referrer(user_id)
