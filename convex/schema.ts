import { defineSchema, defineTable } from "convex/server";
import { v } from "convex/values";

export default defineSchema({
  users: defineTable({
    user_id: v.number(),
    username: v.union(v.string(), v.null()),
    first_name: v.union(v.string(), v.null()),
    language: v.union(v.string(), v.null()),
    preferred_referrer_id: v.union(v.number(), v.null()),
    joined_at: v.string(),
    joined_at_ms: v.number(),
  }).index("by_user_id", ["user_id"]),

  transactions: defineTable({
    tx_id: v.number(),
    user_id: v.number(),
    amount: v.number(),
    currency: v.string(),
    status: v.string(),
    proof_image_id: v.union(v.string(), v.null()),
    created_at: v.string(),
    created_at_ms: v.number(),
    referrer_id: v.union(v.number(), v.null()),
  })
    .index("by_tx_id", ["tx_id"])
    .index("by_status", ["status"])
    .index("by_user_created_at_ms", ["user_id", "created_at_ms"]),

  settings: defineTable({
    key: v.string(),
    value: v.string(),
  }).index("by_key", ["key"]),

  cards: defineTable({
    card_id: v.number(),
    details: v.string(),
    currency: v.string(),
    is_active: v.boolean(),
    created_at: v.string(),
    created_at_ms: v.number(),
  })
    .index("by_card_id", ["card_id"])
    .index("by_currency_active_created_at_ms", [
      "currency",
      "is_active",
      "created_at_ms",
      "card_id",
    ]),

  counters: defineTable({
    key: v.string(),
    value: v.number(),
  }).index("by_key", ["key"]),
});

