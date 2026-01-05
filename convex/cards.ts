import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const formatTimestamp = (ms: number) => {
  const d = new Date(ms);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(
    d.getUTCDate(),
  )} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
};

const nextCounterValue = async (db: any, key: string) => {
  const doc = await db
    .query("counters")
    .withIndex("by_key", (q: any) => q.eq("key", key))
    .unique();
  if (!doc) {
    await db.insert("counters", { key, value: 1 });
    return 1;
  }
  const next = (doc.value ?? 0) + 1;
  await db.patch(doc._id, { value: next });
  return next;
};

const getSettingDoc = async (db: any, key: string) => {
  return await db
    .query("settings")
    .withIndex("by_key", (q: any) => q.eq("key", key))
    .unique();
};

const setSettingValue = async (db: any, key: string, value: string) => {
  const doc = await getSettingDoc(db, key);
  if (doc) await db.patch(doc._id, { value });
  else await db.insert("settings", { key, value });
};

const getCardById = async (db: any, card_id: number) => {
  return await db
    .query("cards")
    .withIndex("by_card_id", (q: any) => q.eq("card_id", card_id))
    .unique();
};

export const add = mutation({
  args: {
    details: v.string(),
    active: v.boolean(),
    currency: v.string(),
  },
  handler: async ({ db }, { details, active, currency }) => {
    const card_id = await nextCounterValue(db, "cards");
    const ms = Date.now();
    await db.insert("cards", {
      card_id,
      details,
      currency,
      is_active: active,
      created_at: formatTimestamp(ms),
      created_at_ms: ms,
    });
    return card_id;
  },
});

export const list = query({
  args: { active_only: v.union(v.boolean(), v.null()) },
  handler: async ({ db }, { active_only }) => {
    const cards = await db.query("cards").collect();
    const filtered =
      active_only === null ? cards : cards.filter((c: any) => c.is_active === active_only);
    filtered.sort((a: any, b: any) => (b.created_at_ms ?? 0) - (a.created_at_ms ?? 0));
    return filtered.map((c: any) => ({
      card_id: c.card_id,
      details: c.details,
      is_active: c.is_active,
      created_at: c.created_at,
      currency: c.currency,
    }));
  },
});

export const setActive = mutation({
  args: { card_id: v.number(), active: v.boolean() },
  handler: async ({ db }, { card_id, active }) => {
    const card = await getCardById(db, card_id);
    if (!card) return false;
    await db.patch(card._id, { is_active: active });
    return true;
  },
});

export const deleteCard = mutation({
  args: { card_id: v.number() },
  handler: async ({ db }, { card_id }) => {
    const card = await getCardById(db, card_id);
    if (!card) return false;
    await db.delete(card._id);
    return true;
  },
});

export const activeCards = query({
  args: {},
  handler: async ({ db }) => {
    const all = await db.query("cards").collect();
    const active = all.filter((c: any) => c.is_active === true);
    active.sort((a: any, b: any) => (b.created_at_ms ?? 0) - (a.created_at_ms ?? 0));
    return active.map((c: any) => c.details);
  },
});

export const nextActiveCard = mutation({
  args: { currency: v.string() },
  handler: async ({ db }, { currency }) => {
    const ccy = currency.trim().toUpperCase();
    const cards = await db
      .query("cards")
      .withIndex("by_currency_active_created_at_ms", (q) =>
        q.eq("currency", ccy).eq("is_active", true),
      )
      .collect();
    cards.sort((a: any, b: any) => {
      const aMs = a.created_at_ms ?? 0;
      const bMs = b.created_at_ms ?? 0;
      if (aMs !== bMs) return aMs - bMs;
      return (a.card_id ?? 0) - (b.card_id ?? 0);
    });
    if (!cards.length) return null;

    const ptrKey = `card_rr_pointer_${ccy}`;
    const ptrDoc = await getSettingDoc(db, ptrKey);
    const raw = ptrDoc?.value ?? "0";
    let ptr = 0;
    try {
      ptr = parseInt(raw, 10) || 0;
    } catch {
      ptr = 0;
    }
    ptr = ptr % cards.length;
    const chosen = cards[ptr];
    const nextPtr = (ptr + 1) % cards.length;
    await setSettingValue(db, ptrKey, String(nextPtr));
    return chosen.details;
  },
});

export const currenciesWithActiveCards = query({
  args: {},
  handler: async ({ db }) => {
    const cards = await db.query("cards").collect();
    const activeCards = cards.filter((c: any) => c.is_active === true);
    const currencies = new Set(activeCards.map((c: any) => c.currency));
    return Array.from(currencies);
  },
});

