import { internalMutation } from "./_generated/server";
import { v } from "convex/values";

export const backfillStats = internalMutation({
    args: {},
    handler: async ({ db }) => {
        // 1. Calculate Global Stats
        const approved = await db
            .query("transactions")
            .withIndex("by_status", (q) => q.eq("status", "approved"))
            .collect();

        const pending = await db
            .query("transactions")
            .withIndex("by_status", (q) => q.eq("status", "pending_approval"))
            .collect();

        const total_raised = approved.reduce((sum, t) => sum + (t.amount ?? 0), 0);
        const donors = new Set(approved.map((t) => t.user_id));

        // Update Aggregates
        const existingStats = await db
            .query("aggregates")
            .withIndex("by_key", (q) => q.eq("key", "stats"))
            .unique();

        if (existingStats) {
            await db.patch(existingStats._id, {
                total_raised,
                total_donors: donors.size,
                pending_reviews: pending.length,
            });
        } else {
            await db.insert("aggregates", {
                key: "stats",
                total_raised,
                total_donors: donors.size,
                pending_reviews: pending.length,
            });
        }

        // 2. Calculate User Stats
        const users = await db.query("users").collect();
        for (const user of users) {
            const userTxs = await db
                .query("transactions")
                .withIndex("by_user_created_at_ms", (q) => q.eq("user_id", user.user_id))
                .collect();

            const userTotal = userTxs
                .filter((t) => t.status === "approved")
                .reduce((sum, t) => sum + (t.amount ?? 0), 0);

            await db.patch(user._id, {
                total_donated: userTotal,
            });
        }

        return "Migration Complete";
    },
});
