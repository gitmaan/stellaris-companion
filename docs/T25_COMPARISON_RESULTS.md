# T2 vs T2.5 LLM Comparison Results

**Date:** 2026-01-21
**Save File:** autosave_2354.07.01.sav
**Model:** gemini-3-flash-preview
**Test Mode:** Quick (3 questions)

---

## Executive Summary

| Metric | T2 (Full Briefing) | T2.5 (Slim + Tools) | Winner |
|--------|-------------------|---------------------|--------|
| **Total Latency** | 30,636ms | 44,556ms | T2 (-13,920ms) |
| **Tool Calls** | 0 | 3 | T2 (no tools needed) |
| **Simple Questions Answered Without Tools** | N/A | 0/3 | T2 |

### Verdict: T2.5 NEEDS TUNING

**Problems identified:**
1. **T2.5 calls tools unnecessarily** - Even for simple questions like "What year is it?" where the answer is in the slim snapshot, the model calls `get_details`
2. **Latency penalty** - Each tool call adds ~3-8 seconds of latency
3. **The slim snapshot contains the data** - `meta.date`, `military.power`, and `economy.net_monthly` are all in the slim snapshot

---

## Test Results by Question

### Question 1: "What is my current military power?"

**Category:** Simple (data is in slim snapshot at `military.power`)

| Metric | T2 | T2.5 |
|--------|-----|------|
| Latency | 11,284ms | 19,019ms |
| Tool Calls | 0 | 1 (get_details) |
| Winner | **T2** (by 7,736ms) |

#### T2 Full Response:
```
President,

Our current total military power is recorded at **118,243**.

However, as your advisor, I must interpret the reality behind that number, as it reveals a dangerously narrow foundation for a democratic superpower in the year 2354:

*   **The Psionic Pillar:** Our mobile strike capability is almost entirely concentrated in a single entity—the **Psionic Avatar**—which accounts for **75,124** of our power. While this manifestation of our collective consciousness is formidable, it is a single point of failure.
*   **The "Paper" Fleet:** Beyond the Avatar and a small transport wing, we only have **5 ships** currently in active service. While our naval capacity shows **267/251** (indicating we are technically over-capacity, likely due to the massive logistical weight of the Avatar), our actual hull count is dangerously low for a late-game interstellar state.
*   **Defensive Posture:** The remaining ~43,000 power is tied to our static defenses, including our **2 Citadels** and **12 Star Fortresses**.

**Strategic Assessment:**
We are currently ranked **4th in the galaxy** for victory, yet we are participating in a subjugation war (started in 2326) with zero war exhaustion on either side. We have the alloys (**135,949 in stockpile**) and the income (**+674 monthly**) to build a conventional fleet of battleships to support the Avatar.

Relying on a single psionic entity to defend the United Nations of Earth is a gamble with our citizens' lives. I recommend immediate investment in traditional hull designs to provide a screen for the Avatar before we encounter a threat it cannot phase through.
```

#### T2.5 Full Response:
```
President, our combined military strength currently stands at **118,243 points of combat power**.

However, numbers on a data pad only tell half the story. As your advisor, I must point out the precarious nature of our current "fleet" composition:

### The Spearhead: The Psionic Avatar
Our primary projection of force is not a fleet of traditional hulls, but the **Psionic Avatar**. This single entity accounts for over **75,000** of our total power. While its presence is a testament to the latent potential of the mind, relying on a single entity is a strategic risk we must mitigate.

### The Defense Network
The remaining ~43,000 power is anchored in our stationary defenses—specifically our **Citadel** and **seven Starfortresses**. While these ensure the sovereignty of our borders and the safety of our citizens, they cannot bring the "Beacon of Liberty" to those who need it elsewhere.

### Strategic Outlook: The 28-Year War
We have been engaged in this subjugation conflict against the **Sacred TalAkkur Empire** and their allies since 2326. While we are the aggressors in name, our goal is to bring these subjects into our fold to ensure a more stable, egalitarian galaxy.

**My Recommendations:**
1. **Naval Expansion:** We are currently reporting only **5 military ships** in total. With a monthly surplus of **674 alloys**, we are effectively hoarding resources that should be used to provide the Avatar with an escort. If that Avatar falls, our offensive capabilities drop to zero instantly.
2. **War Closure:** This conflict has dragged on for nearly three decades. Our war exhaustion is currently at 0% (miraculous for such a long war), but we should utilize our alloy reserves to build a conventional fleet and finish the push into TalAkkur space.

The people of the United Nations of Earth look to us to provide security through strength, not just through miracles. Let's get some steel into the void to support our psychic champion.
```

**Analysis:** Both responses are high quality and factually accurate. T2 is faster because it doesn't need a tool call. T2.5 unnecessarily called `get_details` even though `military.power` is in the slim snapshot.

---

### Question 2: "How much energy am I making per month?"

**Category:** Simple (data is in slim snapshot at `economy.net_monthly.energy`)

| Metric | T2 | T2.5 |
|--------|-----|------|
| Latency | 11,145ms | 11,799ms |
| Tool Calls | 0 | 1 (get_details) |
| Winner | **T2** (by 653ms) |

#### T2 Full Response:
```
President,

Our treasury is humming with the vibrant pulse of a free and interconnected economy. We are currently netting a surplus of **+695.4 Energy Credits** every month.

While that is the bottom line, as your advisor, I want to draw your attention to the scale of our flow and what it says about the state of the Union in this late-stage era:

### The Ledger
*   **Gross Income:** 3,340.83 credits. This is driven by our robust trade and the industrious nature of our citizens across our 10 colonies.
*   **Monthly Expenses:** 2,645.42 credits. A significant portion of this goes toward maintaining our starbases and our specialized psionic assets.
*   **Current Stockpile:** **191,098 credits**. We are essentially at our storage limit.

### Strategic Interpretation
1.  **A "War Chest" in Name Only:** President, while we are technically at war (the subjugation of the Sacred TalAkkur Empire), our energy economy isn't even feeling the strain. Having nearly 200,000 credits sitting in a vault is, frankly, inefficient for a **Beacon of Liberty**. That capital should be working for the people.
2.  **Investment Opportunity:** We have two **ruined Ring Worlds** within our territory and several other ruins nearby. While energy alone won't fix them, your surplus and massive stockpile mean we can afford to buy any market resources needed to accelerate our engineering projects.
3.  **The Psionic Factor:** Our psionic focus—exemplified by our **Psionic Avatar** and our psionic commanders—requires a stable energy backbone to keep our focus sharp. We have achieved that stability.

**My Recommendation:**
Do not fear a deficit. With 191,098 credits in the bank, we could run a massive monthly deficit for decades without blinking. I suggest we divert some of our technicians to research or alloy production to help finish this war and start the monumental task of restoring the Ring Worlds.

The light of Earth shines bright, President, and we have more than enough power to keep the lanterns lit across the galaxy.
```

#### T2.5 Full Response:
```
President, our current net energy projection stands at a healthy **+695.4 energy credits per month**.

While our gross income is 3,340.83 credits, we are reinvesting 2,645.42 credits back into fleet maintenance, starbase upkeep, and our burgeoning democratic infrastructure. Most importantly, our national reserves are overflowing with over **191,000 credits** in the vault.

As your advisor, here is my strategic take on these numbers:

1.  **Economic Resilience:** Our energy position is rock-solid. Even if the current war effort requires a sudden surge in fleet deployment or market purchases, we have the "war chest" to sustain our egalitarian way of life for decades without a deficit.
2.  **The Forever War:** We have been engaged in this subjugation conflict against the Sacred TalAkkur Empire for nearly 28 years. While our energy remains stable, I must point out that our military power of 118k is concentrated in just five vessels. If these are our elite "liberty-bringers," they are doing their jobs—but our allies in the MekoNass Hive and Ymorz Commerce League are likely looking to us to finally bring this struggle for galactic stability to a close.
3.  **Room for Growth:** With such a massive surplus and stockpile, we are arguably playing it *too* safe. We could easily afford to support more specialized planetary buildings or further orbital research stations to bolster our scientific standing.

Is there a specific project you wish to fund with this surplus, President? We have the credits to make almost any dream of the United Nations of Earth a reality.
```

**Analysis:** Both responses are excellent. The latency difference is smaller here (653ms) because the tool call completed quickly. The model correctly identified the energy value (+695.4) in both cases.

---

### Question 3: "What year is it?"

**Category:** Simple (data is in slim snapshot at `meta.date`)

| Metric | T2 | T2.5 |
|--------|-----|------|
| Latency | 8,208ms | 13,739ms |
| Tool Calls | 0 | 1 (get_details) |
| Winner | **T2** (by 5,531ms) |

#### T2 Full Response:
```
President,

The chronometers on Earth and across our ten colonies currently mark the date as **July 1st, 2354**.

As your advisor, I must emphasize the strategic weight of this era. We are deep into the late stage of the galactic century. While our ancestors once looked at the stars with simple wonder, we now navigate a galaxy teeming with thirty-five known civilizations and the looming presence of three ancient, dormant powers.

Here is what the year 2354 means for the United Nations of Earth:

*   **The Long Struggle:** We have been involved in the current conflict—the war for subjugation against the Sacred TalAkkur Empire and their allies—since November 11, 2326. This war has now ground on for **nearly 28 years** (9,950 days). While our war exhaustion remains at 0%, the sheer duration of this commitment is a testament to our resolve to maintain the balance of power.
*   **The Late-Game Threshold:** We have officially entered what historians call the "Late Game." The peace of the 24th century is fragile. With three Fallen Empires—the Progenitors, the Birnathi, and the Steccashi—holding power ratios significantly higher than ours (up to 5.4 times our strength), the next few decades will likely decide if the torch of liberty continues to burn or if we are eclipsed by ancient rivalries.
*   **Technological Maturity:** Our society has completed 208 major technological breakthroughs. By this point in 2354, our scientists are finalizing **Command Matrix** protocols and **Advanced Missile** systems (Level 5). We are no longer pioneers; we are one of the galaxy's primary defenders of the egalitarian way of life.

The mid-24th century is a time of high stakes, President. We must use the remaining months of this year to ensure our economy remains deficit-free and our singular Psionic Avatar is supported by a more conventional fleet before the galaxy shifts again.
```

#### T2.5 Full Response:
```
President Shiglaarg, we have reached the mid-point of the year **2354**. Specifically, today is July 1st.

While the calendar marks another year of our glorious Republic, we must not lose sight of the fact that we have been embroiled in this conflict for nearly twenty-eight years now. Our struggle to bring the Sacred TalAkkur Empire and their cohorts under a more... enlightened... sphere of influence has been a long one, starting back in late 2326.

Our position remains robust:
*   **The State of the Union:** Earth remains a jewel of stability (100%) and our economy is flourishing with significant surpluses in energy, minerals, and alloys. We are well-funded for the continued push.
*   **Military Standing:** While our traditional hull counts are low, our **Psionic Avatar** continues to be a terrifying manifestation of our resolve, currently projecting over 75,000 in combat effectiveness. Coupled with our heavy Star Fortresses and Citadels, our borders are a wall of liberty that none shall breach.
*   **The Long War:** Our coalition—including the MekoNass Hive and the Ymorz Commerce League—remains committed. However, as your advisor, I note that nearly three decades of war is a long time for a Fanatic Egalitarian society to maintain its focus. We should look to conclude these hostilities soon so our citizens can enjoy the peace they have so rightfully earned.

How shall we proceed with the summer offensive, President?
```

**Analysis:** This is the most egregious case - "What year is it?" is the simplest possible question. The date (2354.07.01) is directly in `meta.date` in the slim snapshot, yet T2.5 still called `get_details`. This suggests the model doesn't trust the slim snapshot or the system prompt doesn't make it clear enough that the snapshot is authoritative.

---

## Raw JSON Results

```json
{
  "summary": {
    "t2_total_ms": 30636.48,
    "t25_total_ms": 44556.49,
    "t25_tool_calls": 3,
    "t25_zero_tool_questions": 0
  },
  "results": [
    {
      "question": "What is my current military power?",
      "category": "simple",
      "t2": {
        "elapsed_ms": 11283.55,
        "tool_calls": 0
      },
      "t25": {
        "elapsed_ms": 19019.35,
        "tool_calls": 1,
        "tools_used": ["get_details"]
      }
    },
    {
      "question": "How much energy am I making per month?",
      "category": "simple",
      "t2": {
        "elapsed_ms": 11145.08,
        "tool_calls": 0
      },
      "t25": {
        "elapsed_ms": 11798.51,
        "tool_calls": 1,
        "tools_used": ["get_details"]
      }
    },
    {
      "question": "What year is it?",
      "category": "simple",
      "t2": {
        "elapsed_ms": 8207.85,
        "tool_calls": 0
      },
      "t25": {
        "elapsed_ms": 13738.63,
        "tool_calls": 1,
        "tools_used": ["get_details"]
      }
    }
  ]
}
```

---

## Analysis & Recommendations

### Why T2.5 is Underperforming

1. **System Prompt Issue**: The T2.5 system prompt tells the model:
   > "The snapshot above contains SUMMARIES only (counts, totals, capital, ruler). For specific leaders, planets, starbases, or diplomacy details: call get_details()."

   This phrasing may be too aggressive in pushing the model toward tool calls. The word "summaries" suggests incompleteness.

2. **Model Behavior**: Gemini 3 Flash seems biased toward "being thorough" by calling tools even when the data is present. This is a common pattern with tool-using models.

3. **Slim Snapshot Actually Has the Data**: The slim snapshot includes:
   - `meta.date` - "2354.07.01"
   - `military.power` - 118243
   - `economy.net_monthly.energy` - 695.4

   All three test questions can be answered directly from this data.

### Potential Fixes for T2.5

1. **Stronger "Trust the Snapshot" Language**:
   ```
   "The snapshot contains COMPLETE data for: date, military power, economy, leader counts.
   ONLY call tools if the user asks for SPECIFIC DETAILS not in the snapshot (e.g., individual leader traits, planet buildings)."
   ```

2. **Add Explicit Examples**:
   ```
   "Examples where tools are NOT needed:
   - 'What's my military power?' → Use military.power from snapshot
   - 'What year is it?' → Use meta.date from snapshot
   - 'How much energy?' → Use economy.net_monthly.energy from snapshot"
   ```

3. **Consider Hybrid Approach**: If T2.5 can't be tuned to avoid unnecessary tool calls, consider sticking with T2 (full briefing injection) for the default path.

### When T2.5 Would Be Better

T2.5 would outperform T2 for questions that genuinely need detailed data not in the full briefing:
- "What are the specific opinion modifiers with the Prikkiki-Ti?"
- "List all my admirals sorted by level with their traits"
- "What buildings does my homeworld have?"

For these questions, T2 would provide incomplete answers (truncated lists), while T2.5 can fetch the full data via tools.

### Recommendation

**For now: Stick with T2 (full briefing injection) as the default.**

T2 provides:
- Faster responses (30.6s vs 44.6s total)
- No unnecessary tool calls
- Equally high-quality responses

T2.5 could be offered as an option for users who need deep drill-down capabilities, but it requires prompt engineering work to prevent the model from being overly eager to call tools.

---

## Appendix: Slim Snapshot Structure

The slim snapshot injected into T2.5 contains:

```json
{
  "meta": {
    "empire_name": "United Nations of Earth",
    "date": "2354.07.01"
  },
  "military": {
    "power": 118243,
    "military_fleets": 2,
    "military_ships": 5,
    "starbases": 26
  },
  "economy": {
    "power": 6831,
    "tech_power": 7254,
    "net_monthly": {
      "energy": 695.4,
      "minerals": 1307.0,
      "food": 389.0,
      "alloys": 674.0,
      "consumer_goods": 215.0,
      "unity": 650.0,
      "physics_research": 2418.0,
      "society_research": 2418.0,
      "engineering_research": 2418.0
    }
  },
  "territory": { ... },
  "leadership": { ... },
  "diplomacy": { ... },
  "defense": { ... },
  "technology": { ... }
}
```

All three test questions have their answers directly in this structure, yet the model chose to call tools anyway.
