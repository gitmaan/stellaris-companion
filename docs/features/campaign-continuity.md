# Campaign continuity and Chronicle reliability

Advisor automatically restores the latest local chat for the loaded campaign. New Chat creates another saved conversation; the Chats menu opens earlier conversations. Completed question/answer pairs, original save dates, source hashes and provider metadata are stored in the existing history database. The archive is included in database backups and campaign deletion. Trash preserves it.

The reader shows 150 exchanges at a time. Earlier messages pages through the complete archive; Return to latest restores the current page before asking a follow-up. A failed history read or write is disclosed while live advice remains usable. Stable request IDs make a repeated successful request return its original saved reply.

Readable history and model context have different lifetimes. Advisor restores only a bounded recent suffix in the requested language, using the existing five-turn and twelve-game-month limits and inactivity expiry. A date rewind, including one within the same month, clears tactical context. Current recorded game state always takes precedence over prior replies, and questions are not automatically converted into player commitments. Durable chats do not consume the older campaign-wide topic cache, even when storage is unavailable.

This increment archives completed exchanges. It does not persist or replay unfinished provider requests, synthesize goals or build a semantic memory system.

Chronicle displays the last source date actually covered by written prose, separately from the newest ingested save. Legacy or externally supplied prose without a verifiable source uses unknown coverage. Exported current-era dates follow the same rule. Reading position is a local preference scoped to campaign and language, anchored to a chapter and paragraph; rewritten text falls back to the chapter start.

Chapter actions contains native Edit text, the existing confirmed AI rewrite, and Undo latest change when available. Edits retain their original coverage rather than claiming newer evidence. Saving a draft checks the revision captured when editing began. A conflict leaves the draft in place and offers recovery through reopening the current chapter. Undo restores that chapter without rolling back other chapters.

All Chronicle writers use shared revision checks. Automatic generation, regeneration, native editing and MCP patches cannot overwrite a newer archive, recreate a reset archive or resurrect a deleted campaign. Generated history uses bounded events and retained period-specific source context. New chapters keep compact source bundles for later rewrites; legacy rewrites use recorded period evidence rather than today's political identities. Edited passages and externally edited current-era prose remain protected during routine refreshes.

Manual is part of the existing Story updates setting. Ingestion continues to collect history, while opening Chronicle, changing tabs, focus/visibility events, timers and ingestion notifications remain cache reads. Update story explicitly requests new writing. Relaxed and Sooner retain their existing behavior.

Validation uses synthetic campaign data and provider doubles. Database tests cover restart, deduplication, provenance, pagination, rewind, lifecycle and overlapping writers. Desktop tests cover restoration, minimal menus, native edit/undo, conflict recovery, reading position, refresh controls and existing history/refresh flows. No paid model calls are required for these checks.
