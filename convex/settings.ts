import { mutation, query } from "./_generated/server";
import type { DatabaseReader, DatabaseWriter } from "./_generated/server";
import type { Doc } from "./_generated/dataModel";
import { v } from "convex/values";

const SUPPORTED_CURRENCIES = ["UAH", "RUB", "USD"];
const DONATION_ENABLED_CURRENCIES_KEY = "donation_enabled_currencies";

const getSettingDoc = async (
  db: DatabaseReader | DatabaseWriter,
  key: string,
): Promise<Doc<"settings"> | null> => {
  return await db
    .query("settings")
    .withIndex("by_key", (q) => q.eq("key", key))
    .unique();
};

export const get = query({
  args: { key: v.string() },
  handler: async ({ db }, { key }) => {
    const doc = await getSettingDoc(db, key);
    return doc?.value ?? null;
  },
});

export const set = mutation({
  args: { key: v.string(), value: v.string() },
  handler: async ({ db }, { key, value }) => {
    const existing = await getSettingDoc(db, key);
    if (existing) {
      await db.patch(existing._id, { value });
      return true;
    }
    await db.insert("settings", { key, value });
    return true;
  },
});

export const getSupportMessage = query({
  args: {},
  handler: async ({ db }) => {
    const doc = await getSettingDoc(db, "support_message");
    return doc?.value ?? null;
  },
});

export const setSupportMessage = mutation({
  args: { message: v.string() },
  handler: async ({ db }, { message }) => {
    const doc = await getSettingDoc(db, "support_message");
    if (doc) {
      await db.patch(doc._id, { value: message });
      return true;
    }
    await db.insert("settings", { key: "support_message", value: message });
    return true;
  },
});

export const getEnabledDonationCurrencies = query({
  args: {},
  handler: async ({ db }) => {
    const doc = await getSettingDoc(db, DONATION_ENABLED_CURRENCIES_KEY);
    const raw = doc?.value ?? SUPPORTED_CURRENCIES.join(",");
    const values = raw
      .split(",")
      .map((v) => v.trim().toUpperCase())
      .filter((v) => v.length > 0);
    const allowed = values.filter((v) => SUPPORTED_CURRENCIES.includes(v));
    return allowed.length ? allowed : [];
  },
});

export const setDonationCurrencyEnabled = mutation({
  args: { currency: v.string(), enabled: v.boolean() },
  handler: async ({ db }, { currency, enabled }) => {
    const ccy = currency.trim().toUpperCase();
    const doc = await getSettingDoc(db, DONATION_ENABLED_CURRENCIES_KEY);
    const current = (doc?.value ?? SUPPORTED_CURRENCIES.join(","))
      .split(",")
      .map((v) => v.trim().toUpperCase())
      .filter((v) => SUPPORTED_CURRENCIES.includes(v));

    const set = new Set(current);
    if (SUPPORTED_CURRENCIES.includes(ccy)) {
      if (enabled) set.add(ccy);
      else set.delete(ccy);
    }
    const ordered = SUPPORTED_CURRENCIES.filter((c) => set.has(c));
    const value = ordered.join(",");

    if (doc) await db.patch(doc._id, { value });
    else await db.insert("settings", { key: DONATION_ENABLED_CURRENCIES_KEY, value });

    return ordered;
  },
});

export const isDonationCurrencyEnabled = query({
  args: { currency: v.string() },
  handler: async ({ db }, { currency }) => {
    const ccy = currency.trim().toUpperCase();
    if (!SUPPORTED_CURRENCIES.includes(ccy)) return false;
    const enabled = await db
      .query("settings")
      .withIndex("by_key", (q) => q.eq("key", DONATION_ENABLED_CURRENCIES_KEY))
      .unique();
    const raw = enabled?.value ?? SUPPORTED_CURRENCIES.join(",");
    const values = raw
      .split(",")
      .map((v) => v.trim().toUpperCase())
      .filter((v) => v.length > 0);
    return values.includes(ccy);
  },
});
