"""Registry of confirmed, fixed user reports and the tests that guard them.

Every entry names the deterministic layer where the fix lives and at least one
test that fails if the reported misreading returns. ``new`` cases live in this
directory and start from a hand-built synthetic save; ``referenced`` cases are
existing focused tests elsewhere in ``tests/`` that already encode the reported
situation precisely. ``test_registry.py`` runs every registered node ID and
fails if any is missing, skipped or failing, so this file cannot silently rot.

``verified_against_revert`` records whether the case was seen to fail with the
fix reverted locally (``None`` means not attempted).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ISSUE_URL = "https://github.com/gitmaan/stellaris-companion/issues/{}"
_HERE = "tests/report_regressions"


@dataclass(frozen=True)
class Case:
    node_id: str
    origin: Literal["new", "referenced"]
    verified_against_revert: bool | None = None
    note: str = ""


@dataclass(frozen=True)
class Report:
    summary: str
    root_cause: str
    fixed_by: tuple[str, ...]
    layer: str
    cases: tuple[Case, ...]


REPORTS: dict[int, Report] = {
    135: Report(
        summary="No save loads in 1.1.2: the worker stops with KeyError 'relation_current'.",
        root_cause=(
            "Since PR #110 a Fallen Empire's opinion of the player is read from "
            "relation_current in its relation entry for the player. That read allowed for "
            "a malformed score but not for an entry that has no score, and nothing between "
            "it and the worker catches the error, so one such entry failed the whole save. "
            "The reporter's saves were not available; which entries lack the score in "
            "their games is not confirmed."
        ),
        fixed_by=("PR #136",),
        layer="diplomacy extractor",
        cases=(
            Case(
                f"{_HERE}/test_report_diplomacy.py"
                "::test_issue_135_a_fallen_empire_without_an_opinion_score_does_not_stop_the_save",
                "new",
                True,
                "Fails with the reported traceback when the fix is reverted.",
            ),
        ),
    ),
    125: Report(
        summary="The Advisor's info panel shows no Origin and no Ethics for the empire.",
        root_cause=(
            "The save keeps the empire's origin in the country's government block, beside "
            "the authority and civics, and the identity extractor never read it. The "
            "Advisor's empire identity, the info panel and the report dialog all had a "
            "place for the origin and received nothing. Ethics: Cygnus 4.5 writes them as "
            "one list, ethos.ethics, where earlier versions repeat ethos.ethic, and only the "
            "earlier form was read. This was first recorded as not reproduced, because the "
            "22 local saves were taken for 4.5.3 saves; they are from 4.2.4 to 4.4.6. A "
            "public 4.5.2 save (attached to #79) has the form the reporter described."
        ),
        fixed_by=("PR #127", "PR #139"),
        layer="identity extractor",
        cases=(
            Case(
                f"{_HERE}/test_report_campaign_evidence.py"
                "::test_issue_125_the_empires_origin_is_read_with_its_ethics",
                "new",
                True,
            ),
            Case(
                f"{_HERE}/test_report_campaign_evidence.py"
                "::test_issue_125_ethics_are_read_as_cygnus_writes_them",
                "new",
                True,
                "Fails with no ethics read when the fix is reverted.",
            ),
        ),
    ),
    104: Report(
        summary="A research option is shown under an ID that looks like another technology.",
        root_cause=(
            "The save lists research options by internal ID and the Advisor received no "
            "names, so tech_cryostasis_1 (Automated Colony Ships) read as a different "
            "technology and the one the game showed looked missing. For external AI "
            "clients the MCP summary also cut each field to four options without saying "
            "so and showed names made up from the IDs. Separately, the researched list "
            "was read from every technology= key under the country, which includes the "
            "research queues, so technologies in progress counted as researched."
        ),
        fixed_by=("PR #105", "PR #106"),
        layer="Rust lookup + technology extractor + name catalog + model_context + events + MCP",
        cases=(
            Case(
                f"{_HERE}/test_report_technology.py"
                "::test_issue_104_research_options_carry_their_in_game_names",
                "new",
                True,
                "Names checked against the installed Cygnus 4.5.3 game files; no 4.5.3 save "
                "was available, so the save layout is the 4.4.6 one.",
            ),
            Case(
                f"{_HERE}/test_report_technology.py"
                "::test_issue_104_technologies_still_in_research_are_not_reported_as_researched",
                "new",
                True,
                "Queue contamination, repeatable levels and the special-project queue head "
                "were confirmed on real 4.2.4, 4.4.6 and 4.5.2 saves before and after the fix.",
            ),
            Case(
                "tests/test_events.py"
                "::TestComputeEvents::test_technology_researched_uses_in_game_names",
                "referenced",
                True,
            ),
            Case(
                "tests/test_mcp_context.py"
                "::test_external_clients_get_every_research_option_under_its_in_game_name",
                "referenced",
                True,
                "External AI clients: five options were cut to four, under names made up "
                'from the IDs ("Cryostasis I").',
            ),
        ),
    ),
    79: Report(
        summary="Advisor treats a Nomad economy as a failing settled mining economy.",
        root_cause=(
            "Nothing marked the empire as Nomadic, so the maintained Nomad rules never applied, "
            "and the briefing had no Operational Reserves, Waystation stockpile or Logistic Ship "
            "data. Negative Mineral lines without a production entry read as failing mining."
        ),
        fixed_by=("PR #98", "PR #113"),
        layer="nomads extractor + briefing identity + model_context rules + knowledge retrieval",
        cases=(
            Case(
                f"{_HERE}/test_report_nomads.py"
                "::test_issue_79_nomad_economy_is_read_as_operational_reserves",
                "new",
                True,
                "Synthetic layout from real 4.4 save structures; no real Nomad save checked yet.",
            ),
            Case(
                f"{_HERE}/test_report_nomads.py"
                "::test_issue_79_history_reports_reserve_stages_not_resource_swings",
                "new",
                True,
                "Campaign history: reserve stages replace pooled Energy/Mineral swings.",
            ),
            Case(
                f"{_HERE}/test_report_nomads.py"
                "::test_issue_79_festival_upkeep_is_not_the_reserves_monthly_change",
                "new",
                True,
                "From the game's situation definition (4.5.3); no real Festival save checked.",
            ),
            Case(
                "tests/test_game_knowledge.py"
                "::test_nomad_identity_brings_reserves_rules_to_generic_questions",
                "referenced",
                True,
            ),
        ),
    ),
    95: Report(
        summary="Chronicle and Advisor lose the story when the player changes empire.",
        root_cause=(
            "Empire keys correctly include the player country, but no explicit narrative "
            "ancestry connected different countries in the same galaxy."
        ),
        fixed_by=("codex/issue-95-story-continuation",),
        layer="ingestion identity + story continuity + native Advisor/Chronicle + MCP",
        cases=(
            Case(
                f"{_HERE}/test_report_story.py"
                "::test_issue_95_country_change_continues_story_with_separate_empire_evidence",
                "new",
                True,
                note="Fails when source identity registration is disabled before ingestion.",
            ),
            Case(
                "tests/test_story_continuity.py"
                "::test_rewind_detaches_ancestry_even_after_dates_catch_up",
                "referenced",
            ),
            Case(
                "tests/test_api_story_continuity.py"
                "::test_api_choice_keeps_current_identity_and_previous_chat_separate",
                "referenced",
            ),
        ),
    ),
    11: Report(
        summary="Advisor thinks I lost battles I won (allied battles counted as mine).",
        root_cause=(
            "Battle results were attributed to the whole war coalition, so engagements fought "
            "only by allies counted as the player's victories or defeats."
        ),
        fixed_by=("a21210b",),
        layer="extractor (military._extract_battle_stats participation filter)",
        cases=(
            Case(
                f"{_HERE}/test_report_wars.py"
                "::test_issue_11_allied_only_battles_are_not_counted_as_player_defeats",
                "new",
                True,
            ),
            Case(
                "tests/test_military.py::test_extract_battle_stats_uses_parent_war_side_fixture",
                "referenced",
                True,
            ),
        ),
    ),
    44: Report(
        summary="Advisor reports 0:47 defeats while every enemy capital is occupied.",
        root_cause=(
            "attacker_victory and attacker/defender losses refer to the parent war sides, but "
            "were read relative to each battle's tactical attacker/defender lists, which can "
            "be in the opposite order. Wins and losses were inverted."
        ),
        fixed_by=("PR #45", "3ca961f"),
        layer="extractor (military battle orientation) + model briefing war semantics",
        cases=(
            Case(
                f"{_HERE}/test_report_wars.py"
                "::test_issue_44_won_battles_in_reversed_tactical_order_reach_advisor_as_victories",
                "new",
                True,
            ),
            Case(
                "tests/test_military.py::test_extract_battle_stats_outcome_matrix_uses_parent_war_side",
                "referenced",
                True,
            ),
            Case(
                "tests/test_military.py::test_summarize_war_control_includes_capital_and_system_evidence",
                "referenced",
            ),
            Case(
                "tests/test_model_briefing.py"
                "::test_model_briefing_adds_explicit_war_side_semantics_and_aliases",
                "referenced",
            ),
            Case(
                "tests/test_chat_memory.py"
                "::test_save_memory_prompt_cannot_override_current_empire_state",
                "referenced",
            ),
        ),
    ),
    12: Report(
        summary="Advisor thinks a long-completed Grand Archive is still under construction.",
        root_cause=(
            "Megastructure status was inferred from numbered type suffixes (_0, _1...). The "
            "Grand Archive's only type is grand_archive_0, so it never looked complete; "
            "history also derived lifecycle from suffixes and never recorded completion."
        ),
        fixed_by=("a21210b", "459b536"),
        layer="extractor (megastructure status) + signals/events (status-driven history)",
        cases=(
            Case(
                f"{_HERE}/test_report_megastructures.py"
                "::test_issue_12_completed_grand_archive_is_complete_for_advisor_and_history",
                "new",
                True,
            ),
            Case(
                "tests/test_military.py"
                "::test_classify_megastructure_status_uses_live_state_not_stage_suffix",
                "referenced",
            ),
            Case(
                "tests/test_signals.py::TestExtractMegastructureSignals"
                "::test_uses_literal_suffix_stage_and_authoritative_status",
                "referenced",
            ),
            Case(
                "tests/test_events.py::TestComputeEvents"
                "::test_detects_megastructure_construction_completed_without_stage_change",
                "referenced",
            ),
        ),
    ),
    15: Report(
        summary="Advisor treats current naval capacity usage as the naval cap.",
        root_cause=(
            "Saves store only used_naval_capacity; the briefing exposed it without a cap or "
            "semantics, so the model read usage as the ceiling and called the empire full."
        ),
        fixed_by=("2cba6a9 (0.7.1 sync: naval-cap analysis and claim-safety rules)",),
        layer="extractor (player.get_naval_capacity) + Advisor prompt policy",
        cases=(
            Case(
                f"{_HERE}/test_report_naval_capacity.py"
                "::test_issue_15_naval_usage_below_cap_is_not_presented_as_full",
                "new",
                True,
            ),
            Case(
                "tests/test_player.py"
                "::test_get_naval_capacity_downgrades_to_estimated_when_unresolved_sources_exist",
                "referenced",
            ),
            Case(
                "tests/test_companion_dlc_context.py"
                "::test_naval_cap_policy_block_returns_estimated_status_for_uncertain_cap",
                "referenced",
            ),
            Case(
                "tests/test_companion_dlc_context.py"
                "::test_production_prompt_preserves_naval_capacity_claim_safety",
                "referenced",
            ),
        ),
    ),
    16: Report(
        summary="Advisor thinks completed Dyson Swarms are still under construction.",
        root_cause=(
            "Same suffix inference as #12: a finished dyson_swarm_3 looked like a construction "
            "stage. Status now comes from the build queue and active upgrade state."
        ),
        fixed_by=("a21210b", "e6522c5 (Dyson Swarm coverage)"),
        layer="extractor (military._classify_megastructure_status)",
        cases=(
            Case(
                "tests/test_military.py::test_completed_dyson_swarm_final_stage_is_complete",
                "referenced",
                True,
            ),
            Case(
                "tests/test_military.py"
                "::test_dyson_swarm_upgrading_to_sphere_is_under_construction",
                "referenced",
                False,
                note=(
                    "Guards the opposite direction: an active swarm-to-sphere upgrade must "
                    "stay under construction. It passes with the suffix revert by design."
                ),
            ),
        ),
    ),
    81: Report(
        summary="Advisor denies the observed Rogue Servitor civic because of a 'missing' DLC.",
        root_cause=(
            "missing_dlcs was a set difference between known packs and the save's requirement "
            "list. It ignored packs integrated into the base game (Synthetic Dawn since 4.3.6) "
            "and was presented to the model as proof that features did not exist."
        ),
        fixed_by=("PR #84", "90115e4"),
        layer="metadata extractor + campaign_evidence/evidence_policy + Advisor prompt",
        cases=(
            Case(
                f"{_HERE}/test_report_campaign_evidence.py"
                "::test_issue_81_observed_rogue_servitor_is_not_denied_for_unreported_dlc",
                "new",
                True,
            ),
            Case(
                "tests/test_campaign_evidence_consumers.py"
                "::test_full_request_preserves_observed_identity_across_providers",
                "referenced",
            ),
            Case(
                "tests/test_campaign_evidence.py::test_metadata_records_dlc_parse_evidence",
                "referenced",
            ),
            Case(
                "tests/test_model_briefing.py"
                "::test_model_briefing_preserves_source_and_recomputes_legacy_evidence",
                "referenced",
            ),
        ),
    ),
    83: Report(
        summary="Chronicle dates are wrong after loading an older save (2308 then 2303).",
        root_cause=(
            "Capture order defined the Chronicle start date, so a rewound campaign had a "
            "future start; sparse captures re-selected the starting snapshot as a chapter "
            "boundary and stayed pending forever."
        ),
        fixed_by=("PR #89", "aa01af9"),
        layer="Chronicle generator + database snapshot ranges (real SQLite)",
        cases=(
            Case(
                "tests/test_chronicle_continuity.py"
                "::test_chronicle_can_start_after_loading_a_save_before_first_capture",
                "referenced",
                True,
            ),
            Case(
                "tests/test_chronicle_continuity.py"
                "::test_sparse_snapshots_finalize_at_real_boundaries_without_getting_stuck",
                "referenced",
                True,
            ),
            Case(
                "tests/test_chronicle_continuity.py"
                "::test_future_events_do_not_satisfy_first_chapter_threshold",
                "referenced",
                True,
            ),
        ),
    ),
}

# Reports deliberately left out, with the reason.
NOT_COVERED: dict[int, str] = {
    86: "ChatGPT 'Errno 2' provider error; that code path is being changed separately.",
}
