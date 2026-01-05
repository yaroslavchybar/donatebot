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
    const approved = await db
      .query("transactions")
      .withIndex("by_status", (q) => q.eq("status", "approved"))
      .collect();
    const pending = await db
      .query("transactions")
      .withIndex("by_status", (q) => q.eq("status", "pending_approval"))
      .collect();

    const total_raised = approved.reduce((sum: number, t: any) => sum + (t.amount ?? 0), 0);
    const donors = new Set(approved.map((t: any) => t.user_id));
    return {
      total_raised,
      pending_reviews: pending.length,
      total_donors: donors.size,
    };
  },
});

export const userTotalDonated = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const rows = await db
      .query("transactions")
      .withIndex("by_user_created_at_ms", (q) => q.eq("user_id", user_id))
      .collect();
    return rows
      .filter((t: any) => t.status === "approved")
      .reduce((sum: number, t: any) => sum + (t.amount ?? 0), 0);
  },
});

