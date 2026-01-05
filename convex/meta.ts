import { mutation } from "./_generated/server";

const DEFAULT_CURRENCIES = ["UAH", "RUB", "USD"];

export const initDefaults = mutation({
  args: {},
  handler: async ({ db }) => {
    const currenciesKey = "donation_enabled_currencies";
    const existingCurrencies = await db
      .query("settings")
      .withIndex("by_key", (q) => q.eq("key", currenciesKey))
      .unique();
    if (!existingCurrencies) {
      await db.insert("settings", {
        key: currenciesKey,
        value: DEFAULT_CURRENCIES.join(","),
      });
    }

    const ensureCounter = async (key: string) => {
      const existing = await db
        .query("counters")
        .withIndex("by_key", (q) => q.eq("key", key))
        .unique();
      if (!existing) {
        await db.insert("counters", { key, value: 0 });
      }
    };

    await ensureCounter("transactions");
    await ensureCounter("cards");

    return true;
  },
});
