import { mutation, query } from "./_generated/server";
import { v } from "convex/values";

const formatTimestamp = (ms: number) => {
  const d = new Date(ms);
  const pad = (n: number) => n.toString().padStart(2, "0");
  return `${d.getUTCFullYear()}-${pad(d.getUTCMonth() + 1)}-${pad(
    d.getUTCDate(),
  )} ${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}:${pad(d.getUTCSeconds())}`;
};

export const add = mutation({
  args: {
    user_id: v.number(),
    username: v.union(v.string(), v.null()),
    first_name: v.union(v.string(), v.null()),
  },
  handler: async ({ db }, { user_id, username, first_name }) => {
    const existing = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    if (existing) {
      return false;
    }
    const ms = Date.now();
    await db.insert("users", {
      user_id,
      username,
      first_name,
      language: null,
      preferred_referrer_id: null,
      joined_at: formatTimestamp(ms),
      joined_at_ms: ms,
    });
    return true;
  },
});

export const get = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const user = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    if (!user) return null;
    return {
      user_id: user.user_id,
      username: user.username,
      first_name: user.first_name,
      language: user.language,
      preferred_referrer_id: user.preferred_referrer_id,
    };
  },
});

export const listAllUserIds = query({
  args: {
    paginationOpts: v.object({
      numItems: v.number(),
      cursor: v.union(v.string(), v.null()),
    })
  },
  handler: async ({ db }, { paginationOpts }) => {
    const users = await db.query("users").paginate(paginationOpts);
    return {
      users: users.page.map((u) => u.user_id),
      continueCursor: users.continueCursor,
      isDone: users.isDone,
    };
  },
});

export const setLanguage = mutation({
  args: { user_id: v.number(), language: v.union(v.string(), v.null()) },
  handler: async ({ db }, { user_id, language }) => {
    const user = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    if (!user) return false;
    await db.patch(user._id, { language });
    return true;
  },
});

export const getLanguage = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const user = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    return user?.language ?? null;
  },
});

export const setPreferredReferrer = mutation({
  args: { user_id: v.number(), referrer_id: v.union(v.number(), v.null()) },
  handler: async ({ db }, { user_id, referrer_id }) => {
    const user = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    if (!user) return false;
    await db.patch(user._id, { preferred_referrer_id: referrer_id });
    return true;
  },
});

export const getPreferredReferrer = query({
  args: { user_id: v.number() },
  handler: async ({ db }, { user_id }) => {
    const user = await db
      .query("users")
      .withIndex("by_user_id", (q) => q.eq("user_id", user_id))
      .unique();
    return user?.preferred_referrer_id ?? null;
  },
});

