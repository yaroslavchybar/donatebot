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
    const id = await db.insert("counters", { key, value: 1 });
    return { id, value: 1 };
  }
  const next = (doc.value ?? 0) + 1;
  await db.patch(doc._id, { value: next });
  return { id: doc._id, value: next };
};

const getTxById = async (db: any, tx_id: number) => {
  return await db
    .query("transactions")
    .withIndex("by_tx_id", (q: any) => q.eq("tx_id", tx_id))
    .unique();
};

export const create = mutation({
  args: {
    user_id: v.number(),
    amount: v.number(),
    referrer_id: v.union(v.number(), v.null()),
    currency: v.string(),
  },
  handler: async ({ db }, { user_id, amount, referrer_id, currency }) => {
    const { value: tx_id } = await nextCounterValue(db, "transactions");
    const ms = Date.now();
    await db.insert("transactions", {
      tx_id,
      user_id,
      amount,
      currency,
      status: "pending_proof",
      proof_image_id: null,
      created_at: formatTimestamp(ms),
      created_at_ms: ms,
      referrer_id,
    });
    return tx_id;
  },
});

export const updateProof = mutation({
  args: { tx_id: v.number(), proof_image_id: v.string() },
  handler: async ({ db }, { tx_id, proof_image_id }) => {
    const tx = await getTxById(db, tx_id);
    if (!tx) return false;
    await db.patch(tx._id, { proof_image_id, status: "pending_approval" });
    return true;
  },
});

export const updateStatus = mutation({
  args: { tx_id: v.number(), status: v.string() },
  handler: async ({ db }, { tx_id, status }) => {
    const tx = await getTxById(db, tx_id);
    if (!tx) return false;

    // Maintain aggregates when status changes
    if (tx.status !== "approved" && status === "approved") {
      // 1. Update Global Stats
      const stats = await db.query("aggregates").withIndex("by_key", q => q.eq("key", "stats")).unique();
      if (stats) {
        await db.patch(stats._id, {
          total_raised: stats.total_raised + tx.amount,
          // Note: total_donors is harder to maintain perfectly accurate in O(1) without a set, 
          // but we can check if this is user's first approved tx. 
          // For simplicity/performance, we might skip accurate unique donor count here or do a check:
          // total_donors: stats.total_donors + (isNewDonor ? 1 : 0)
        });
      }

      // 2. Update User Stats
      const user = await db.query("users").withIndex("by_user_id", q => q.eq("user_id", tx.user_id)).unique();
      if (user) {
        await db.patch(user._id, {
          total_donated: (user.total_donated ?? 0) + tx.amount
        });
      }
    }

    await db.patch(tx._id, { status });
    return true;
  },
});

export const get = query({
  args: { tx_id: v.number() },
  handler: async ({ db }, { tx_id }) => {
    const tx = await getTxById(db, tx_id);
    if (!tx) return null;
    return {
      tx_id: tx.tx_id,
      user_id: tx.user_id,
      amount: tx.amount,
      currency: tx.currency,
      status: tx.status,
      proof_image_id: tx.proof_image_id,
      created_at: tx.created_at,
      referrer_id: tx.referrer_id,
    };
  },
});

export const history = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const rows = await db
      .query("transactions")
      .withIndex("by_user_created_at_ms", (q) => q.eq("user_id", user_id))
      .order("desc")
      .take(10);
    return rows.map((tx: any) => ({
      tx_id: tx.tx_id,
      amount: tx.amount,
      status: tx.status,
      created_at: tx.created_at,
    }));
  },
});

export const deleteTx = mutation({
  args: { tx_id: v.number() },
  handler: async ({ db }, { tx_id }) => {
    const tx = await getTxById(db, tx_id);
    if (!tx) return false;
    await db.delete(tx._id);
    return true;
  },
});

export const stats = query({
  args: {},
  handler: async ({ db }) => {
    const stats = await db.query("aggregates").withIndex("by_key", q => q.eq("key", "stats")).unique();
    return {
      total_raised: stats?.total_raised ?? 0,
      pending_reviews: stats?.pending_reviews ?? 0, // Note: pending_reviews needs maintenance too if we want it O(1)
      total_donors: stats?.total_donors ?? 0,
    };
  },
});

export const userTotalDonated = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const user = await db.query("users").withIndex("by_user_id", q => q.eq("user_id", user_id)).unique();
    return user?.total_donated ?? 0;
  },
});

