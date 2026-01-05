import logging
import os
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

SUPPORTED_CURRENCIES: tuple[str, ...] = ("UAH", "RUB", "USD")


@dataclass(frozen=True)
class Stats:
    total_raised: float
    pending_reviews: int
    total_donors: int


class Database:
    """Async Convex HTTP API database client with connection pooling."""

    def __init__(self, convex_url: str, *, auth_header: str | None = None, timeout_s: float = 10.0):
        self.convex_url = convex_url.rstrip("/")
        self.auth_header = auth_header
        self.timeout_s = timeout_s
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            headers = {"Content-Type": "application/json", "Accept": "application/json"}
            if self.auth_header:
                headers["Authorization"] = self.auth_header
            self._client = httpx.AsyncClient(
                base_url=self.convex_url,
                headers=headers,
                timeout=self.timeout_s,
                http2=True,
            )
        return self._client

    async def _call(self, kind: str, path: str, args: dict[str, Any]) -> Any:
        client = await self._get_client()
        payload = {"path": path, "args": args, "format": "json"}
        try:
            resp = await client.post(f"/api/{kind}", json=payload)
            resp.raise_for_status()
            out = resp.json()
        except httpx.HTTPStatusError as e:
            raise RuntimeError(f"Convex HTTP error: {e.response.status_code}") from e
        except httpx.RequestError as e:
            raise RuntimeError(f"Convex connection error: {e}") from e
        except Exception as e:
            raise RuntimeError(f"Convex error: {e}") from e

        if out.get("status") != "success":
            msg = out.get("errorMessage") or "Unknown Convex error"
            raise RuntimeError(msg)
        return out.get("value")

    async def query(self, path: str, args: dict[str, Any] | None = None) -> Any:
        return await self._call("query", path, args or {})

    async def mutation(self, path: str, args: dict[str, Any] | None = None) -> Any:
        return await self._call("mutation", path, args or {})

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    async def init(self) -> None:
        await self.mutation("meta:initDefaults", {})

    async def add_user(self, user_id: int, username: str | None, first_name: str | None) -> None:
        await self.mutation(
            "users:add",
            {"user_id": int(user_id), "username": username, "first_name": first_name},
        )

    async def get_all_users(self) -> list[int]:
        rows = await self.query("users:listAllUserIds", {})
        return [int(x) for x in (rows or [])]

    async def create_transaction(self, user_id: int, amount: float, referrer_id: int | None = None, currency: str = "USD") -> int | None:
        tx_id = await self.mutation(
            "transactions:create",
            {
                "user_id": int(user_id),
                "amount": float(amount),
                "referrer_id": int(referrer_id) if referrer_id is not None else None,
                "currency": str(currency),
            },
        )
        return int(tx_id) if tx_id is not None else None

    async def update_transaction_proof(self, transaction_id: int, proof_image_id: str) -> None:
        await self.mutation(
            "transactions:updateProof",
            {"tx_id": int(transaction_id), "proof_image_id": str(proof_image_id)},
        )

    async def update_transaction_status(self, transaction_id: int, status: str) -> None:
        await self.mutation(
            "transactions:updateStatus",
            {"tx_id": int(transaction_id), "status": str(status)},
        )

    async def get_transaction(self, transaction_id: int) -> tuple[Any, ...] | None:
        tx = await self.query("transactions:get", {"tx_id": int(transaction_id)})
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

    async def get_user_history(self, user_id: int) -> list[tuple[Any, ...]]:
        rows = await self.query("transactions:history", {"user_id": int(user_id)}) or []
        return [
            (int(r["tx_id"]), float(r["amount"]), str(r["status"]), str(r["created_at"]))
            for r in rows
        ]

    async def delete_transaction(self, transaction_id: int) -> None:
        await self.mutation("transactions:deleteTx", {"tx_id": int(transaction_id)})

    async def set_active_card(self, card_details: str) -> None:
        await self.mutation("settings:set", {"key": "active_card", "value": str(card_details)})

    async def get_active_card(self) -> str:
        value = await self.query("settings:get", {"key": "active_card"})
        return str(value) if value else "No card set. Contact admin."

    async def add_card(self, details: str, active: bool = True, currency: str = "USD") -> int | None:
        card_id = await self.mutation(
            "cards:add",
            {"details": str(details), "active": bool(active), "currency": str(currency)},
        )
        return int(card_id) if card_id is not None else None

    async def list_cards(self, active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
        rows = await self.query(
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

    async def set_card_active(self, card_id: int, active: bool) -> None:
        await self.mutation("cards:setActive", {"card_id": int(card_id), "active": bool(active)})

    async def delete_card(self, card_id: int) -> None:
        await self.mutation("cards:deleteCard", {"card_id": int(card_id)})

    async def get_active_cards(self) -> list[str]:
        rows = await self.query("cards:activeCards", {}) or []
        return [str(x) for x in rows]

    async def get_next_active_card(self, currency: str = "USD") -> str | None:
        return await self.mutation("cards:nextActiveCard", {"currency": str(currency)})

    async def get_currencies_with_active_cards(self) -> list[str]:
        rows = await self.query("cards:currenciesWithActiveCards", {}) or []
        return [str(x) for x in rows]

    async def set_support_message(self, message: str) -> None:
        await self.mutation("settings:setSupportMessage", {"message": str(message)})

    async def get_support_message(self) -> str | None:
        return await self.query("settings:getSupportMessage", {})

    async def get_enabled_donation_currencies(self) -> list[str]:
        rows = await self.query("settings:getEnabledDonationCurrencies", {}) or []
        return [str(x) for x in rows]

    async def set_donation_currency_enabled(self, currency: str, enabled: bool) -> list[str]:
        rows = await self.mutation(
            "settings:setDonationCurrencyEnabled",
            {"currency": str(currency), "enabled": bool(enabled)},
        ) or []
        return [str(x) for x in rows]

    async def is_donation_currency_enabled(self, currency: str) -> bool:
        return bool(await self.query("settings:isDonationCurrencyEnabled", {"currency": str(currency)}))

    async def get_stats(self) -> Stats:
        data = await self.query("transactions:stats", {}) or {}
        return Stats(
            total_raised=float(data.get("total_raised") or 0.0),
            pending_reviews=int(data.get("pending_reviews") or 0),
            total_donors=int(data.get("total_donors") or 0),
        )

    async def get_user_total_donated(self, user_id: int) -> float:
        value = await self.query("transactions:userTotalDonated", {"user_id": int(user_id)})
        return float(value or 0.0)

    async def get_user(self, user_id: int) -> tuple[Any, ...] | None:
        user = await self.query("users:get", {"user_id": int(user_id)})
        if not user:
            return None
        return (int(user["user_id"]), user.get("username"), user.get("first_name"))

    async def set_user_language(self, user_id: int, lang: str) -> None:
        await self.mutation("users:setLanguage", {"user_id": int(user_id), "language": str(lang)})

    async def get_user_language(self, user_id: int) -> str | None:
        return await self.query("users:getLanguage", {"user_id": int(user_id)})

    async def set_user_preferred_referrer(self, user_id: int, referrer_id: int | None) -> None:
        await self.mutation(
            "users:setPreferredReferrer",
            {"user_id": int(user_id), "referrer_id": int(referrer_id) if referrer_id is not None else None},
        )

    async def get_user_preferred_referrer(self, user_id: int) -> int | None:
        value = await self.query("users:getPreferredReferrer", {"user_id": int(user_id)})
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


# Async wrapper functions for module-level access
async def init_db():
    await _get_db().init()


async def add_user(user_id, username, first_name):
    await _get_db().add_user(user_id, username, first_name)


async def get_all_users():
    return await _get_db().get_all_users()


async def create_transaction(user_id, amount, referrer_id=None, currency="USD"):
    return await _get_db().create_transaction(user_id, amount, referrer_id, currency)


async def update_transaction_proof(transaction_id, proof_image_id):
    await _get_db().update_transaction_proof(transaction_id, proof_image_id)


async def update_transaction_status(transaction_id, status):
    await _get_db().update_transaction_status(transaction_id, status)


async def get_transaction(transaction_id):
    return await _get_db().get_transaction(transaction_id)


async def get_user_history(user_id):
    return await _get_db().get_user_history(user_id)


async def delete_transaction(transaction_id: int) -> None:
    await _get_db().delete_transaction(transaction_id)


async def set_active_card(card_details):
    await _get_db().set_active_card(card_details)


async def get_active_card():
    return await _get_db().get_active_card()


async def add_card(details: str, active: bool = True, currency: str = "USD") -> int | None:
    return await _get_db().add_card(details, active, currency)


async def list_cards(active_only: bool | None = None) -> list[tuple[int, str, int, str, str]]:
    return await _get_db().list_cards(active_only)


async def set_card_active(card_id: int, active: bool) -> None:
    await _get_db().set_card_active(card_id, active)


async def delete_card(card_id: int) -> None:
    await _get_db().delete_card(card_id)


async def get_active_cards() -> list[str]:
    return await _get_db().get_active_cards()


async def get_next_active_card(currency: str = "USD") -> str | None:
    return await _get_db().get_next_active_card(currency)


async def get_currencies_with_active_cards() -> list[str]:
    return await _get_db().get_currencies_with_active_cards()


async def set_support_message(message: str) -> None:
    await _get_db().set_support_message(message)


async def get_support_message() -> str | None:
    return await _get_db().get_support_message()


async def get_enabled_donation_currencies() -> list[str]:
    return await _get_db().get_enabled_donation_currencies()


async def set_donation_currency_enabled(currency: str, enabled: bool) -> list[str]:
    return await _get_db().set_donation_currency_enabled(currency, enabled)


async def is_donation_currency_enabled(currency: str) -> bool:
    return await _get_db().is_donation_currency_enabled(currency)


async def get_stats():
    stats = await _get_db().get_stats()
    return {
        "total_raised": stats.total_raised,
        "pending_reviews": stats.pending_reviews,
        "total_donors": stats.total_donors,
    }


async def get_user_total_donated(user_id):
    return await _get_db().get_user_total_donated(user_id)


async def get_user(user_id):
    return await _get_db().get_user(user_id)


async def set_user_language(user_id, lang):
    await _get_db().set_user_language(user_id, lang)


async def get_user_language(user_id):
    return await _get_db().get_user_language(user_id)


async def set_user_preferred_referrer(user_id: int, referrer_id: int | None) -> None:
    await _get_db().set_user_preferred_referrer(user_id, referrer_id)


async def get_user_preferred_referrer(user_id: int) -> int | None:
    return await _get_db().get_user_preferred_referrer(user_id)
