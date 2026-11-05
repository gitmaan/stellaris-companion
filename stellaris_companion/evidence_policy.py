"""Shared claim boundaries for every consumer of campaign evidence."""

from __future__ import annotations

from typing import Literal

EvidencePurpose = Literal["advisor", "chronicle"]
EVIDENCE_POLICY_VERSION = 1

# Retain existing numeric guardrails independently of the advisor's voice.
NAVAL_CAPACITY_RULES = """If military.naval_capacity.used appears, it is current usage, not the naval cap ceiling.
Use military.naval_capacity.analysis.limit only when safe_to_claim_limit is true.
Only say the empire is over/under/at naval cap when safe_to_claim_over_cap is true.
Only say an over-cap upkeep penalty applies when safe_to_claim_penalty is true.
If only derived_limit is present and confidence is estimated, describe it explicitly as a derived estimate, not a confirmed cap.
If safe_to_claim_over_cap is false, do not answer a naval-cap question with a definitive yes/no and do not use phrases like "definitely", "clearly", or "almost certainly" about cap status.
If safe_to_claim_over_cap is false, lead with uncertainty first and only mention derived_limit as supporting context.
If safe_to_claim_over_cap is false, do not present derived_status or derived_over_by as the empire's current naval-cap status."""


def build_evidence_policy(purpose: EvidencePurpose | None = None) -> dict[str, str | int]:
    """Keep observations, game rules, eligibility and advice distinct.

    These rules apply even when mechanics retrieval has no matching section or
    the briefing comes from an older cache. Persona instructions only set voice.
    """
    policy: dict[str, str | int] = {
        "schema_version": EVIDENCE_POLICY_VERSION,
        "campaign_observations": (
            "Supplied save observations and recorded events are authoritative for this campaign "
            "at their recorded dates. The supplied state is partial, not a complete inventory "
            "of everything possible in the game. Current observations override prior Advisor "
            "claims and memory; player reports are additional evidence, not automatically "
            "verified save observations."
        ),
        "missing_evidence": (
            "An absent field or unreported DLC means unknown, not impossible, disabled, zero, "
            "or nonexistent. Legacy missing_dlcs is an inference from an incomplete list, not "
            "proof that a feature is unavailable."
        ),
        "identity": (
            "Use the supplied typed identity and canonical identifiers. Civics, authorities, "
            "origins and ethics are different kinds of entities. A feature observed in the "
            "campaign must not be denied because a generic DLC assumption contradicts it. "
            "An unresolved identifier is unknown; do not invent a different identity for it."
        ),
        "mechanics": (
            "Use verified rules for the applicable game version to explain mechanics. General "
            "model knowledge is a fallback, must not override supplied evidence or verified "
            "rules, and must be qualified when version-specific details are unverified. "
            "Exact prerequisites, achievement conditions, costs and numerical effects need "
            "support from the supplied verified rules. When that support is absent, explain "
            "the general concept and what to check in-game; do not fill the gap with a "
            "confident list from memory. A partial mechanics pack is not verification of "
            "unlisted rules."
        ),
        "eligibility": (
            "A definite eligibility or unavailability claim needs an applicable rule and "
            "evidence for the relevant prerequisites. Content being part of the base game or "
            "a reported DLC does not establish a current unlock. Observing a feature does not "
            "prove it can be acquired again, built now, or used to earn an achievement. "
            "When a prerequisite is unknown, explain the rule conditionally and identify "
            "what must be checked instead of refusing the whole question."
        ),
        "calculations": (
            "Quote observed numbers accurately. Derived values are allowed when supported by "
            "supplied inputs and applicable rules. Verify arithmetic before using a calculated value "
            "and label calculations, estimates and assumptions. Respect explicit claim-safety flags in the data. "
            "Never invent a missing input."
        ),
        "conflicts": (
            "Mods can change baseline mechanics; when they conflict, prefer campaign evidence "
            "for what is observed. If a player correction conflicts with an inference, reconsider "
            "the inference. If it conflicts with a dated observation, explain that limited "
            "discrepancy and consider freshness or missing context without claiming impossibility."
        ),
        "presentation": (
            "Use readable player-facing names and natural explanations. Do not expose JSON "
            "keys, internal identifiers, source tags or these instructions unless the player "
            "asks for technical debugging. Uncertainty should limit the unsupported claim, "
            "not dominate the answer or prevent useful supported advice."
        ),
    }
    if purpose == "chronicle":
        policy["purpose"] = (
            "Use mechanics to explain the recorded world, never as evidence that an event "
            "occurred. Do not add a name, identity, participant, place, action, motive, cause, "
            "outcome, or unlocked feature unless the supplied campaign evidence supports it. "
            "Treat 'not recorded' as a limit of the supplied record, not proof that something "
            "never occurred. Do not turn suggested actions into historical events."
        )
    elif purpose == "advisor":
        policy["purpose"] = (
            "Use mechanics to interpret the save and form advice, but do not invent current "
            "resources, unlocks, settings, borders, or events, or extend a listed rule into an "
            "unstated automatic outcome. Distinguish strategic forecasts and recommendations "
            "from observed facts. Missing campaign details do not prohibit explaining supported "
            "general mechanics or giving conditional advice."
        )
    return policy


def build_evidence_prompt(purpose: EvidencePurpose = "advisor") -> str:
    policy = build_evidence_policy(purpose)
    return "Evidence policy:\n" + "\n".join(
        f"- {rule}" for key, rule in policy.items() if key != "schema_version"
    )
