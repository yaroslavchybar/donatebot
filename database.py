import json
import logging
import os
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES: tuple[str, ...] = ("UAH", "RUB", "USD")


@dataclass(frozen=True)
class Stats:
    total_raised: float
    pending_reviews: int
    total_donors: int


class Database:
    """Convex HTTP API database client."""

    def __init__(self, convex_url: str, *, auth_header: str | None = None, timeout_s: float = 15.0):
        self.convex_url = convex_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout_s = timeout_s

    def _call(self, kind: str, path: str, args: dict[str, Any]) -> Any:
        url = f"{self.convex_url}/api/{kind}"
        payload = {"path": path, "args": args, "format": "json"}
        data = json.dumps(payload).encode("utf-8")
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if self.auth_header:
            headers["Authorization"] = self.auth_header
        req = Request(url, data=data, headers=headers, method="POST")
        try:
            with urlopen(req, timeout=self.timeout_s) as resp:
                raw = resp.read().decode("utf-8")
        except HTTPError as e:
            raise RuntimeError(f"Convex HTTP error: {e.code}") from e
        except URLError as e:
            raise RuntimeError(f"Convex connection error: {e}") from e

        try:
            out = json.loads(raw)
        except Exception as e:
            raise RuntimeError("Convex returned non-JSON response") from e

        if out.get("status") != "success":
            msg = out.get("errorMessage") or "Unknown Convex error"
            raise RuntimeError(msg)
        return out.get("value")

    def query(self, path: str, args: dict[str, Any] | None = None) -> Any:
        return self._call("query", path, args or {})

    def mutation(self, path: str, args: dict[str, Any] | None = None) -> Any:
        return self._call("mutation", path, args or {})

    def init(self) -> None:
        self.mutation("meta:initDefaults", {})

    def add_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        self.mutation(
            "users:add",
            {"user_id": int(user_id), "username": username, "first_name": first_name},
        )

    def get_all_users(self) -> list[int]:
        rows = self.query("users:listAllUserIds", {})
        return [int(x) for x in (rows or [])]

    def create_transaction(self, user_id: int, amount: float, referrer_id: int | None = None, currency: str = "USD") -> int | None:
        tx_id = self.mutation(
            "transactions:create",
            {
                "user_id": int(user_id),
                "amount": float(amount),
                "referrer_id": int(referrer_id) if referrer_id is not None else None,
                "currency": str(currency),
            },
        )
        return int(tx_id) if tx_id is not None else None

    def update_transaction_proof(self, transaction_id: int, proof_image_id: str) -> None:
        self.mutation(
            "transactions:updateProof",
            {"tx_id": int(transaction_id), "proof_image_id": str(proof_image_id)},
        )

    def update_transaction_status(self, transaction_id: int, status: str) -> None:
        self.mutation(
            "transactions:updateStatus",
            {"tx_id": int(transaction_id), "status": str(status)},
        )

    def get_transaction(self, transaction_id: int) -> tuple[Any, ...] | None:
        tx = self.query("transactions:get", {"tx_id": int(transaction_id)})
        if not tx:
            return None
        return (
            int(tx["tx_id"]),
            int(tx["user_id"]),
            float(tx["amount"]),
            str(tx["currency"]),
            str(tx["status"]),
            tx.get("proof_image_id"),
            str(tx["created_at"]),
            int(tx["referrer_id"]) if tx.get("referrer_id") is not None else None,
        )

    def get_user_history(self, user_id: int) -> list[tuple[Any, ...]]:
        rows = self.query("transactions:history", {"user_id": int(user_id)}) or []
        return [
            (int(r["tx_id"]), float(r["amount"]), str(r["status"]), str(r["created_at"]))
            for r in rows
        ]

    def delete_transaction(self, transaction_id: int) -> None:
        self.mutation("transactions:deleteTx", {"tx_id": int(transaction_id)})

    def set_active_card(self, card_details: str) -> None:
        self.mutation("settings:set", {"key": "active_card", "value": str(card_details)})

    def get_active_card(self) -> str:
        value = self.query("settings:get", {"key": "active_card"})
        return str(value) if value else "No card set. Contact admin."

    def add_card(self, details: str, active: bool = True, currency: str = "USD") -> int | None:
        card_id = self.mutation(
            "cards:add",
            {"details": str(details), "active": bool(active), "currency": str(currency)},
        )
        return int(card_id) if card_id is not None else None

    def list_cards(self, active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
        rows = self.query(
            "cards:list",
            {"active_only": active_only if active_only is not None else None},
        ) or []
        out: list[tuple[int, str, int, str, str]] = []
        for r in rows:
            out.append(
                (
                    int(r["card_id"]),
                    str(r["details"]),
                    1 if bool(r["is_active"]) else 0,
                    str(r["created_at"]),
                    str(r["currency"]),
                )
            )
        return out

    def set_card_active(self, card_id: int, active: bool) -> None:
        self.mutation("cards:setActive", {"card_id": int(card_id), "active": bool(active)})

    def delete_card(self, card_id: int) -> None:
        self.mutation("cards:deleteCard", {"card_id": int(card_id)})

    def get_active_cards(self) -> list[str]:
        rows = self.query("cards:activeCards", {}) or []
        return [str(x) for x in rows]

    def get_next_active_card(self, currency: str = "USD") -> str | None:
        return self.mutation("cards:nextActiveCard", {"currency": str(currency)})

    def get_currencies_with_active_cards(self) -> list[str]:
        rows = self.query("cards:currenciesWithActiveCards", {}) or []
        return [str(x) for x in rows]

    def set_support_message(self, message: str) -> None:
        self.mutation("settings:setSupportMessage", {"message": str(message)})

    def get_support_message(self) -> str | None:
        return self.query("settings:getSupportMessage", {})

    def get_enabled_donation_currencies(self) -> list[str]:
        rows = self.query("settings:getEnabledDonationCurrencies", {}) or []
        return [str(x) for x in rows]

    def set_donation_currency_enabled(self, currency: str, enabled: bool) -> list[str]:
        rows = self.mutation(
            "settings:setDonationCurrencyEnabled",
            {"currency": str(currency), "enabled": bool(enabled)},
        ) or []
        return [str(x) for x in rows]

    def is_donation_currency_enabled(self, currency: str) -> bool:
        return bool(self.query("settings:isDonationCurrencyEnabled", {"currency": str(currency)}))

    def get_stats(self) -> Stats:
        data = self.query("transactions:stats", {}) or {}
        return Stats(
            total_raised=float(data.get("total_raised") or 0.0),
            pending_reviews=int(data.get("pending_reviews") or 0),
            total_donors=int(data.get("total_donors") or 0),
        )

    def get_user_total_donated(self, user_id: int) -> float:
        value = self.query("transactions:userTotalDonated", {"user_id": int(user_id)})
        return float(value or 0.0)

    def get_user(self, user_id: int) -> tuple[Any, ...] | None:
        user = self.query("users:get", {"user_id": int(user_id)})
        if not user:
            return None
        return (int(user["user_id"]), user.get("username"), user.get("first_name"))

    def set_user_language(self, user_id: int, lang: str) -> None:
        self.mutation("users:setLanguage", {"user_id": int(user_id), "language": str(lang)})

    def get_user_language(self, user_id: int) -> str | None:
        return self.query("users:getLanguage", {"user_id": int(user_id)})

    def set_user_preferred_referrer(self, user_id: int, referrer_id: int | None) -> None:
        self.mutation(
            "users:setPreferredReferrer",
            {"user_id": int(user_id), "referrer_id": int(referrer_id) if referrer_id is not None else None},
        )

    def get_user_preferred_referrer(self, user_id: int) -> int | None:
        value = self.query("users:getPreferredReferrer", {"user_id": int(user_id)})
        return int(value) if value is not None else None


# Module-level database instance
_db: Database | None = None


def _get_db() -> Database:
    global _db
    if _db is None:
        url = (os.getenv("CONVEX_URL") or "").strip()
        if not url:
            raise RuntimeError("CONVEX_URL environment variable is required")
        auth = (os.getenv("CONVEX_AUTHORIZATION") or "").strip() or None
        _db = Database(url, auth_header=auth)
    return _db


def init_db():
    _get_db().init()


def add_user(user_id, username, first_name):
    _get_db().add_user(user_id, username, first_name)


def get_all_users():
    return _get_db().get_all_users()


def create_transaction(user_id, amount, referrer_id=None, currency="USD"):
    return _get_db().create_transaction(user_id, amount, referrer_id, currency)


def update_transaction_proof(transaction_id, proof_image_id):
    _get_db().update_transaction_proof(transaction_id, proof_image_id)


def update_transaction_status(transaction_id, status):
    _get_db().update_transaction_status(transaction_id, status)


def get_transaction(transaction_id):
    return _get_db().get_transaction(transaction_id)


def get_user_history(user_id):
    return _get_db().get_user_history(user_id)


def delete_transaction(transaction_id: int) -> None:
    _get_db().delete_transaction(transaction_id)


def set_active_card(card_details):
    _get_db().set_active_card(card_details)


def get_active_card():
    return _get_db().get_active_card()


def add_card(details: str, active: bool = True, currency: str = "USD") -> int | None:
    return _get_db().add_card(details, active, currency)


def list_cards(active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
    return _get_db().list_cards(active_only)


def set_card_active(card_id: int, active: bool) -> None:
    _get_db().set_card_active(card_id, active)


def delete_card(card_id: int) -> None:
    _get_db().delete_card(card_id)


def get_active_cards() -> list[str]:
    return _get_db().get_active_cards()


def get_next_active_card(currency: str = "USD") -> str | None:
    return _get_db().get_next_active_card(currency)


def get_currencies_with_active_cards() -> list[str]:
    return _get_db().get_currencies_with_active_cards()


def set_support_message(message: str) -> None:
    _get_db().set_support_message(message)


def get_support_message() -> str | None:
    return _get_db().get_support_message()


def get_enabled_donation_currencies() -> list[str]:
    return _get_db().get_enabled_donation_currencies()


def set_donation_currency_enabled(currency: str, enabled: bool) -> list[str]:
    return _get_db().set_donation_currency_enabled(currency, enabled)


def is_donation_currency_enabled(currency: str) -> bool:
    return _get_db().is_donation_currency_enabled(currency)


def get_stats():
    stats = _get_db().get_stats()
    return {
        "total_raised": stats.total_raised,
        "pending_reviews": stats.pending_reviews,
        "total_donors": stats.total_donors,
    }


def get_user_total_donated(user_id):
    return _get_db().get_user_total_donated(user_id)


def get_user(user_id):
    return _get_db().get_user(user_id)


def set_user_language(user_id, lang):
    _get_db().set_user_language(user_id, lang)


def get_user_language(user_id):
    return _get_db().get_user_language(user_id)


def set_user_preferred_referrer(user_id: int, referrer_id: int | None) -> None:
    _get_db().set_user_preferred_referrer(user_id, referrer_id)


def get_user_preferred_referrer(user_id: int) -> int | None:
    return _get_db().get_user_preferred_referrer(user_id)
