# Command Test Map

Keep this file in sync when bot commands or listener-driven command behavior changes.

Update checklist:

1. Add or update focused tests in `tests/test_tinki_bot.py`
2. Run `python3 -m pytest --collect-only -q`
3. Refresh the command-to-test mapping below
4. Run the narrowest relevant pytest slice, then `python3 -m pytest -q` when the change is broad

This map is intentionally strict: it lists tests that directly call command methods or `.callback` paths. Broader helper or listener coverage may exist separately.

Shared smoke coverage: `test_all_registered_commands_have_smoke_cases_and_invoke_cleanly` runs every registered text command through a safe mocked invocation path and fails if a new command is added without a smoke case.

## Admin

| Command | Direct tests |
| --- | --- |
| `!restart` | `test_restart_sends_message_and_invokes_systemctl` |
| `!deploy` | `test_deploy_dirs_excludes_repo_only_branding_assets`, `test_deploy_reports_check_without_aws_cost_message`, `test_deploy_aborts_truncated_archive`, `test_deploy_fails_when_archive_extracts_no_root_directory` |
| `!awscost` | `test_awscost_command_sends_summary`, `test_awscost_command_denies_non_whiptail` |
| `!runtests` | `test_runtests_reports_start_and_summary` |
| `!testurls` | `test_testurls_reports_each_result_and_summary` |

## Bowling

| Command | Direct tests |
| --- | --- |
| `!pb` | `test_pb_empty_scores`, `test_pb_returns_max` |
| `!avg` | `test_avg_empty_scores`, `test_avg_correct_value` |
| `!median` | `test_median_odd_list`, `test_median_even_list`, `test_median_empty_scores` |
| `!all` | `test_all_scores_splits_long_output` |
| `!delete` | `test_delete_score_reports_multiple_matches` |
| `!add` | `test_add_score_reports_invalid_timestamp` |
| `!bowlinggraph` | `test_graph_scores_sends_generated_file` |
| `!bowlingdistgraph` | `test_distribution_graph_sends_generated_file` |

## Emotes

| Command | Direct tests |
| --- | --- |
| `!spinny` | `test_spinny_activate_stores_user_id` |
| `!stopspinny` | `test_stopspinny_removes_user_by_mention`, `test_stopspinny_not_found_sends_error` |
| `!silentspinny` | `test_silentspinny_denied_for_non_whiptail` |
| `!allemotes` | `test_allemotes_reports_empty_server_list`, `test_allemotes_starts_menu_for_guild_emojis` |
| `!emote` | `test_emote_command_opens_picker_for_single_result`, `test_emote_command_opens_picker_for_single_exact_match`, `test_emote_command_rejects_invalid_x_size`, plus the 7TV browser helper tests |

## Reminders

| Command | Direct tests |
| --- | --- |
| `!remind` | `test_remind_shows_usage` |
| `!remindme` | `test_remindme_without_entries_reports_none`, `test_remindme_lists_upcoming_and_past`, `test_remindme_relative_time_creates_reminder_with_reply_link`, `test_remindme_invalid_time_unit_reports_error` |
| `!deletereminder` | `test_deletereminder_deletes_owned_reminder`, `test_deletereminder_reports_missing_reminder` |
| `!currenttime` | `test_currenttime_returns_timestamp_string` |

## Tracking

| Command | Direct tests |
| --- | --- |
| `!sussy` | `test_count_commands_report_totals` |
| `!sussygraph` | `test_sussy_graph_sends_generated_file` |
| `!explode` | `test_count_commands_report_totals` |
| `!explodegraph` | `test_explode_graph_accepts_mixed_naive_and_aware_timestamps` |
| `!grindcount` | `test_count_commands_report_totals` |
| `!grindgraph` | `test_grind_graph_sends_generated_file` |

## Uma

| Command | Direct tests |
| --- | --- |
| `!gacha` | `test_gacha_deletes_non_ssr_results_after_timeout`, `test_gacha_sends_ssr_media_for_ssr_hits`, `test_gacha_adds_repull_reaction`, `test_gacha_reaction_repulls_same_count` |
| `!pity` | No dedicated command-path test yet |
| `!uma` | `test_uma_assign_uses_target_member_and_rarity_prefix` |
| `!race` | `test_race_requires_at_least_two_members`, `test_race_sends_narration_and_gif` |
| `!umagif` | `test_umagif_sends_fallback_when_giphy_empty`, `test_umagif_sends_gif_when_available` |

## Utility

| Command | Direct tests |
| --- | --- |
| `!purge` | `test_purge_denies_non_whiptail`, `test_purge_deletes_matching_messages` |
| `!gif` | `test_gif_command_sends_url_from_giphy` |
| `!random` | `test_random_command_reports_no_pins` |
| `!roulette` | `test_roulette_command_sends_url_from_giphy` |
| `!cat` | No dedicated command-path test yet |
| `!dog` | `test_dog_command_reports_unexpected_api_payload` |
| `!dogbark` | `test_dogbark_command_sends_figlet_bark` |
| `!ss` | `test_ss_command_sends_static_image_url` |
| `!github` | `test_github_command_sends_repo_url` |
| `!changelog` | `test_changelog_command_uses_entries`, `test_changelog_command_handles_empty_results` |
| `!commands` | `test_commands_dm_mentions_current_reminder_and_retired_commands`, `test_commands_handles_dm_forbidden` |
| retired server placeholders | `test_retired_server_commands_send_removed_message` |
