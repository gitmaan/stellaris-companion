# Campaign continuity and Chronicle reliability

Advisor automatically restores the latest local chat for the loaded campaign. New Chat creates another saved conversation; the Chats menu opens earlier conversations. Completed question/answer pairs, original save dates, source hashes and provider metadata are stored in the existing history database. The archive is included in database backups and campaign deletion. Trash preserves it.

The reader shows 150 exchanges at a time. Earlier messages pages through the complete archive; Return to latest restores the current page before asking a follow-up. A failed history read or write is disclosed while live advice remains usable. Stable request IDs make a repeated successful request return its original saved reply.

Readable history and model context have different lifetimes. Advisor restores only a bounded recent suffix in the requested language, using the existing five-turn and twelve-game-month limits and inactivity expiry. A date rewind, including one within the same month, clears tactical context. Current recorded game state always takes precedence over prior replies, and questions are not automatically converted into player commitments. Durable chats do not consume the older campaign-wide topic cache, even when storage is unavailable.

This increment archives completed exchanges. It does not persist or replay unfinished provider requests, synthesize goals or build a semantic memory system.

Chronicle displays the last source date actually covered by written prose, separately from the newest ingested save. Legacy or externally supplied prose without a verifiable source uses unknown coverage. Exported current-era dates follow the same rule. Loading an earlier save keeps the recorded story and quietly explains when its coverage is ahead of the loaded save. Reading position is a local preference scoped to campaign and language, anchored to a chapter and paragraph; rewritten text falls back to the chapter start.

Before any story exists, Chronicle starts at the earliest recorded game date, even if the first captured save was later. Loading 2308, then 2303 and 2304 can therefore produce a 2303–2304 current era. The latest captured snapshot still defines the endpoint; future-dated observations do not count toward chapter triggers or enter the earlier prose. Empty older caches with a start date ahead of the loaded save recover the same way. Existing prose with later coverage remains protected.

If snapshots jump across a chapter's time threshold, the chapter closes at an actual advancing snapshot. For example, captures in 2303 and 2310 produce a chapter ending at the recorded 2310 source instead of repeatedly trying to close it at its own starting row. Both dates and snapshot IDs remain attached to their source rows, and repeated refreshes do not create duplicate chapters.

Loading an earlier save starts a new branch of the campaign. That capture is compared with the latest recorded snapshot at or before its date, so returning from 2308 to 2304 does not record lost colonies, ended wars or departed leaders. Captures dated after the loaded save belong to the abandoned branch. Their events, and legacy events compared against them, stay out of later chapters, the current era and MCP summaries, and they cannot become a chapter boundary. Chapters already written from that branch keep their recorded sources.

Regression tests reproduce these failures with synthetic data based on the date sequence in issue #83; the reporter's database and save were not available, so the exact reported case remains unverified. This follow-up is separate from the 1.1.2-beta.1 tag.

Chapter actions contains native Edit text, the existing confirmed AI rewrite, and Undo latest change when available. Edits retain their original coverage rather than claiming newer evidence. Saving a draft checks the revision captured when editing began. A conflict leaves the draft in place and offers recovery through reopening the current chapter. Undo restores that chapter without rolling back other chapters.

All Chronicle writers use shared revision checks. Automatic generation, regeneration, native editing and MCP patches cannot overwrite a newer archive, recreate a reset archive or resurrect a deleted campaign. Generated history uses bounded events and retained period-specific source context. New chapters keep compact source bundles for later rewrites; legacy rewrites use recorded period evidence rather than today's political identities. Edited passages and externally edited current-era prose remain protected during routine refreshes.

Manual is part of the existing Story updates setting. Ingestion continues to collect history, while opening Chronicle, changing tabs, focus/visibility events, timers and ingestion notifications remain cache reads. Update story explicitly requests new writing. Relaxed and Sooner retain their existing behavior.

Validation uses synthetic campaign data and provider doubles. Database tests cover restart, deduplication, provenance, pagination, rewind, lifecycle and overlapping writers. Desktop tests cover restoration, minimal menus, native edit/undo, conflict recovery, reading position, refresh controls and existing history/refresh flows. No paid model calls are required for these checks.
