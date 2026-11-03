# Test Report — FireFlink 4.0 League Tracker
Run date: 3 Nov 2026 · `cd backend && .venv/bin/python -m pytest -v` → **50 passed, 0 failed** (incl. 5 live Google Sheet sync tests)

## Automated acceptance tests (Section 22)

| Area | Requirement | Test | Result |
|---|---|---|---|
| Demo counting | Completed + Qualified Yes counts; Completed + No/blank, Scheduled, No Show, Rescheduled, Cancelled, Awaiting Demo Date and Pipeline do not | `test_demo_counting_rules` (9 cases) | ✅ |
| | POC Initiated adds no count and doesn't erase an achieved demo | `test_poc_does_not_add_and_does_not_erase`, `test_scheduled_to_completed_counts_once_and_validation` | ✅ |
| | Scheduled → Completed counts once; editing a completed record doesn't duplicate it | `test_status_update_counts_once`, API test | ✅ |
| | Qualified = Yes only when Completed; invalid Demo Type rejected; a future-dated Completed demo is rejected | `test_scheduled_to_completed_counts_once_and_validation` | ✅ |
| Demo Type | F2F and Virtual stored; both count overall; only F2F counts for the challenge | `test_both_types_count_overall_only_f2f_counts_challenge` | ✅ |
| | Scheduled F2F reported separately from qualified completed F2F | `test_scheduled_f2f_separate_from_completed` | ✅ |
| | Demo Type filter works | `test_filtered_report_never_changes_official` | ✅ |
| Carry-forward | Section 6 Monday–Saturday example: every Required / Done / Pending value matches; official total = 7, not inflated | `test_spec_carry_forward_example` | ✅ |
| | Sunday creates no target; pending survives Sunday; Saturday has a target | `test_spec_carry_forward_example`, `test_pending_survives_sunday_and_saturday_has_target`, `test_sunday_shows_next_working_day_target` | ✅ |
| | Calculated independently per BD | `test_carry_forward_is_independent_per_bd` | ✅ |
| | Over-achieving creates no future credit | `test_over_achievement_creates_no_future_target` | ✅ |
| | An in-progress day is not marked missed; closing the day or passing the cutoff finalises it; Not Started / In Progress / Carry-Forward Pending states | `test_in_progress_day_not_marked_missed_and_closure_finalises`, `test_in_progress_and_carry_forward_pending_states` | ✅ |
| | No target after the final league day (20 Dec is a Sunday); outstanding carry-forward reported; 42 working days | `test_final_league_day_has_no_next_target` | ✅ |
| F2F challenge | Starts at 0; Scheduled, unqualified and Virtual don't count; +1 per valid record; never fabricated | `test_f2f_challenge_rules`, `test_f2f_progress_not_fabricated` | ✅ |
| | Region aliases (Dubai, Abu Dhabi, Soudi, Malasia, GCC…); any league date counts (admin decision) | `test_f2f_any_league_date_counts_and_regions` | ✅ |
| | F2F Champion tie flagged | `test_f2f_tie_flagged` | ✅ |
| Revenue | Signed uses the signed date and Credited uses the credited date; spec example totals ₹43 lakh | `test_revenue_dates_and_example_total` | ✅ |
| | Signed → Amount Credited not double-counted; duplicate opportunity blocked (409) | `test_signed_to_credited_not_double_counted`, `test_revenue_duplicate_blocked_and_status_change` | ✅ |
| | Below ₹10 lakh still visible; eligibility needs ₹10 lakh; gap to leader | `test_threshold_and_visibility` | ✅ |
| | A tie splits ₹1,00,000 equally | `test_revenue_tie_splits_prize` | ✅ |
| | Other currencies need a configured rate; pending conversion excluded from ranking; rate and date recorded | `test_currency_needs_configured_rate`, API test | ✅ |
| Awards | Weekly uses both types; exact week ranges; Week 1 = 1–8 Nov | `test_weekly_uses_both_types`, `test_weeks_have_exact_ranges_and_cover_league` | ✅ |
| | League awards can't be finalised before the league ends; Sunday or future days can't be closed | `test_day_close_and_award_finalize_rules` | ✅ |
| | A filtered report never changes the official standings | `test_filtered_report_never_changes_official` | ✅ |
| Import/export | The real workbook imports (43 demos, 7 BDs taken from its dropdown) | `test_real_workbook_import_reimport_incremental_and_export` | ✅ |
| | Re-importing the same file creates 0 duplicates | same | ✅ |
| | Incremental import: new row added, invalid row rejected, changed row **not** applied until ticked, blank cell keeps the stored value | same | ✅ |
| | Export keeps the exact headers and re-imports cleanly | same | ✅ |
| | Missing worksheet or headers reported | `test_import_rejects_missing_headers` | ✅ |
| Security / audit | Every data API requires sign-in; CSRF header enforced; Arena token is read-only and Arena-only | `test_auth_required_everywhere`, `test_csrf_header_required`, `test_arena_token` | ✅ |
| | Soft delete and restore; audit entries; activity feed (new leader, qualified demo) | `test_soft_delete_restore_and_audit` | ✅ |
| | Settings validated and audited | `test_settings_validation_and_audit` | ✅ |

## Live Google Sheet sync (`test_gsheet.py`)
| Requirement | Result |
|---|---|
| Re-syncing an unchanged sheet changes nothing | ✅ |
| Changing a Demo Date in the sheet updates the same demo instead of adding one; status and qualification are mirrored; blanking a cell clears the value | ✅ |
| A row removed from the sheet is soft-deleted; a new row is added | ✅ |
| An invalid row is reported and the stored record is left unchanged and not deleted | ✅ |
| Emptying the sheet by mistake deletes nothing (safety check) and raises an alert | ✅ |
| An unknown BD is rejected, not created | ✅ |
| Live mode locks sheet fields (409) but allows app-only POC remarks; interval must be at least 30 s | ✅ |
| Real fetch from the shared Google Sheet: 2.8 s; first run 1 added and 7 updated, the next run 44 unchanged | ✅ |

## Browser verification (Playwright, Chromium, on a copy of the real database)

| Check | Result |
|---|---|
| Login, then the dashboard renders with live data | ✅ |
| Real transition (a demo becomes qualified, so a BD hits today's target and a new leader appears): green glow, slide-in toast and NEW LEADER banner fire | ✅ (banner 1, glow 1, toasts 2) |
| Refreshing straight afterwards replays nothing | ✅ (banner 0, glow 0) |
| Leaderboard reorders with layout animation; crown on the leader | ✅ (visual) |
| League Arena at 1920×1080 shows no editing controls | ✅ (0 inputs / selects / edit buttons) |
| Import preview of the source workbook against the edited DB: flags the 1 changed row as an unticked update and keeps blank values | ✅ |
| No JavaScript errors (apart from the expected 401 on the login page) | ✅ |
| 390 px phone width: the one horizontal overflow (dashboard header button) was found and fixed | ✅ fixed |
| Reduced motion: the sidebar toggle and Settings option disable CSS and Framer animations and confetti | ✅ (code path; set via `data-reduced-motion`) |

## Known limitations / decisions to confirm
- Qualified demos dated on a **Sunday** count toward totals but aren't applied to any daily target, because the spec defines targets only for working days. Confirm whether they should reduce Monday's carry-in.
- There is no public-holiday calendar besides Sundays, since none was specified.
- The Weekly Demo Champion has no tie rule in the spec, so ties are flagged for review.
- The F2F "missed" and "achieved" animations depend on browser storage. A browser that blocks storage sees no celebrations, but every number is still correct.
