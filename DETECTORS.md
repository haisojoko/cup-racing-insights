# Detector Catalog

Tracking file for the insight-detector library. Updated as detectors are
implemented, refined, or retired.

Each detector has a stable ID (e.g. `D-014`) so requests like
"implement D-023" or "tweak D-005's scoring" are unambiguous.

## Status legend

| Symbol | Meaning |
|---|---|
| ✅ | Shipped — detector + scoring + at least one template live |
| 🚧 | In progress — design or code underway |
| 📋 | Planned — designed, not started |
| 🔬 | Research / schema-blocked — needs new parsing or new data |
| ❌ | Rejected — explored, decided not to build |

## Cards

Insights are surfaced through **cards** — themed groupings. Each detector
below lists which card(s) consume its output. Run `cri cards` for the live
registry.

```
snapshot · streaks · records · venues · trajectory · peer-rank ·
firsts · splits · uniqueness · discipline · current-form · head-to-head
```

## Roll-up

| Status | Count |
|---|---|
| ✅ Shipped | 47 |
| 📋 Planned | 38 |
| 🔬 Research / Schema-blocked | 15 |
| **Total catalogued** | **100** |

---

## 1 · Streaks

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-001 | ✅ | `detect_top_n_streak` | `top3_streak`, `top5_streak`, `top10_streak` | streaks |
| D-002 | ✅ | `detect_consecutive_points_streak` | `points_streak` | streaks |
| D-003 | 📋 | `detect_winless_streak` | `winless_streak` | streaks |
| D-004 | 📋 | `detect_poleless_streak` | `poleless_streak` | streaks |
| D-005 | 📋 | `detect_podiumless_streak` | `podiumless_streak` | streaks |
| D-006 | ✅ | `detect_in_season_hot_streak` | `in_season_hot_streak` | streaks |
| D-007 | 📋 | `detect_in_season_cold_streak` | `in_season_cold_streak` | streaks |
| D-008 | ✅ | `detect_consecutive_season_bests` | `consecutive_season_bests` | streaks |
| D-009 | ✅ | `detect_seasons_always_scoring` | `seasons_always_scoring` | streaks |
| D-104 | ✅ | `detect_fastest_lap_streak` | `fastest_lap_streak` | streaks |
| D-105 | ✅ | `detect_consecutive_podium_weekends` | `consecutive_podium_weekends` | streaks |

## 2 · Records & Personal Bests

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-010 | ✅ | `detect_career_best_finish` | `career_best_finish` | snapshot, records |
| D-011 | ✅ | `detect_best_season` | `career_best_season` | snapshot, records |
| D-012 | ✅ | `detect_best_venue_weekend` | `best_venue_weekend` | records |
| D-013 | ✅ | `detect_concentrated_records` | `concentrated_{poles,fls,wins,podiums}`, `majority_{...}` | records |
| D-014 | ✅ | `detect_highest_single_race_points` | `highest_single_race_pts` | records |
| D-015 | ✅ | `detect_largest_win_margin` | `largest_win_margin` | records |
| D-016 | 📋 | `detect_career_high_low_finish` | `career_high_finish`, `career_low_finish` | records |
| D-095 | ✅ | `detect_league_record_wins_season` | `league_record_wins_season` | records |
| D-096 | ✅ | `detect_league_record_weighted_score` | `league_record_weighted_score` | records |

## 3 · Firsts, Lasts & Milestones

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-017 | ✅ | `detect_career_firsts` | `first_win`, `first_podium`, `first_pole`, `first_fl` | firsts |
| D-018 | ✅ | `detect_career_lasts` | `most_recent_win`, `most_recent_podium`, `most_recent_pole` | firsts, current-form |
| D-019 | 📋 | `detect_debut_race` | `debut_race` | firsts |
| D-020 | 📋 | `detect_race_count_milestone` | `race_milestone_{50,100,200}` | firsts |
| D-021 | 📋 | `detect_podium_count_milestone` | `podium_milestone_{25,50,100}` | firsts |
| D-022 | 📋 | `detect_points_milestone` | `points_milestone_{1000,5000,10000}` | firsts |
| D-023 | 📋 | `detect_first_threshold_season` | `first_50pct_top5_season`, `first_0_5_ws_season` | firsts |

## 4 · Trajectory

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-024 | ✅ | `detect_best_vs_worst_season` | `best_vs_worst_season` | trajectory |
| D-025 | ✅ | `detect_consecutive_podium_seasons` | `consecutive_podium_seasons` | trajectory, streaks |
| D-026 | ✅ | `detect_personal_best_season_rank` | `best_season_rank` | snapshot, trajectory, records |
| D-027 | 📋 | `detect_biggest_yoy_jump` | `biggest_yoy_jump` | trajectory |
| D-028 | 📋 | `detect_biggest_yoy_decline` | `biggest_yoy_decline` | trajectory |
| D-029 | 📋 | `detect_late_career_resurgence` | `late_career_resurgence` | trajectory |
| D-030 | 📋 | `detect_first_half_vs_second_half` | `career_half_split` | trajectory |
| D-031 | 📋 | `detect_career_tenure` | `career_tenure` | trajectory |
| D-032 | ❌ | `detect_comeback_after_gap` | (removed — framed as a reminder of absence rather than a positive arc) |
| D-033 | 📋 | `detect_consecutive_improving_seasons` | `consecutive_improving_seasons` | trajectory |
| D-034 | 📋 | `detect_outperformance_season` | `outperformance_season` | trajectory |
| D-035 | 📋 | `detect_underperformance_season` | `underperformance_season` | trajectory |
| D-036 | 📋 | `detect_career_peak_year` | `career_peak_year` | trajectory |

## 5 · Splits & Specialisms

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-037 | ✅ | `detect_car_class_split` | `class_split_podium`, `class_split_ppr` | splits |
| D-038 | ✅ | `detect_specialist_car` | `specialist_car` | splits |
| D-039 | 📋 | `detect_multi_class_split` | `multi_class_split` | splits |
| D-040 | 📋 | `detect_recent_vs_early_career` | `recent_vs_early_split` | splits |
| D-041 | 📋 | `detect_race_position_split` | `r1_vs_r4_split` | splits |

## 6 · Pole / FL Conversion

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-042 | 📋 | `detect_pole_to_win_rate` | `pole_to_win_rate` | splits |
| D-043 | 📋 | `detect_pole_to_podium_rate` | `pole_to_podium_rate` | splits |
| D-044 | 📋 | `detect_wins_from_non_pole` | `wins_from_non_pole` | splits |
| D-045 | ✅ | `detect_hat_trick_races` | `hat_trick_races` | records |

## 7 · Peer Rankings

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-046 | ✅ | `detect_among_winless_peers` | `winless_rank_{pod_pct,top5_pct,pts_per_race}` | peer-rank |
| D-047 | ✅ | `detect_among_all_drivers` | `league_rank_{podiums,poles,points,races,top5}` | snapshot, peer-rank |
| D-048 | 📋 | `detect_league_rank_wins` | `league_rank_wins` | peer-rank |
| D-049 | 📋 | `detect_league_rank_fls` | `league_rank_fls` | peer-rank |
| D-050 | 📋 | `detect_league_rank_wdc` | `league_rank_wdc`, `league_rank_wcc` | peer-rank |
| D-051 | 📋 | `detect_among_active_peers` | `active_rank_{pod_pct,top5_pct,pts_per_race}` | peer-rank |
| D-052 | ✅ | `detect_distinct_venues_won` | `distinct_winning_venues` | peer-rank, venues |

## 8 · Venues

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-053 | ✅ | `detect_venue_pole_sweep` | `venue_pole_sweep`, `venue_pole_sweep_career` | venues |
| D-054 | ✅ | `detect_venue_repeat_wins` | `venue_repeat_wins`, `venue_repeat_wins_career` | venues |
| D-055 | ✅ | `detect_best_avg_venue` | `best_avg_venue` | venues |
| D-056 | ✅ | `detect_weekend_multi_podium` | `weekend_multi_podium`, `weekend_multi_podium_career` | venues |
| D-057 | 📋 | `detect_worst_avg_venue` | `worst_avg_venue` | venues |
| D-058 | 📋 | `detect_venue_total_podiums` | `venue_career_podiums` | venues |
| D-059 | 📋 | `detect_first_time_venue` | `first_time_venue_performance` | venues |
| D-060 | 📋 | `detect_venue_pole_sweep_streak` | `pole_sweep_weekend_streak` | venues |
| D-061 | 📋 | `detect_lowest_variance_venue` | `lowest_variance_venue` | venues |
| D-099 | ✅ | `detect_venue_multi_season_podium` | `venue_multi_season_podium`, `venue_multi_season_podium_career` | venues |

## 9 · Consistency

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-062 | ✅ | `detect_tightest_season_range` | `tightest_season_range` | records |
| D-063 | ✅ | `detect_season_never_outside_top_n` | `season_never_outside_top_n` | streaks |

## 10 · Uniqueness (League-Wide)

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-064 | ✅ | `detect_only_to_pole_sweep` | `only_to_pole_sweep` | uniqueness |
| D-065 | ✅ | `detect_only_winless_with_long_streak` | `only_winless_with_long_streak` | uniqueness |
| D-066 | ✅ | `detect_sole_venue_winner` | `sole_venue_winner` | uniqueness |
| D-067 | ✅ | `detect_first_to_milestone` | `first_to_milestone_{wins,podiums,poles}` | uniqueness |
| D-068 | 📋 | `detect_only_with_combination` | `only_with_combination` | uniqueness |
| D-094 | ✅ | `detect_wins_without_poles` | `wins_without_poles` | uniqueness |
| D-098 | ✅ | `detect_won_both_classes` | `won_both_classes` | uniqueness |
| D-100 | 📋 | `detect_fl_every_season` | `fl_every_season` | uniqueness |
| D-101 | ✅ | `detect_multiple_wcc_club` | `multiple_wcc_club` | uniqueness |
| D-102 | ✅ | `detect_multiple_wdc_club` | `multiple_wdc_club` | uniqueness |
| D-103 | 🔬 | `detect_wcc_varied_teammates` | `wcc_varied_teammates` | uniqueness |
| D-106 | ✅ | `detect_only_race_week_sweep` | `only_race_week_sweep` | uniqueness |
| D-107 | ✅ | `detect_only_perfect_podium_venue` | `only_perfect_podium_venue` | uniqueness |

## 11 · Penalty / Discipline

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-069 | ✅ | `detect_penalty_summary` | `clean_career`, `worst_penalty_race`, `worst_penalty_season` | discipline |
| D-070 | 📋 | `detect_penalty_free_season` | `penalty_free_season` | discipline |
| D-071 | 📋 | `detect_high_penalty_venue` | `high_penalty_venue` | discipline |

## 12 · Margins (Championship Outcomes)

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-072 | 📋 | `detect_wdc_margin_won` | `wdc_margin_won` | trajectory |
| D-073 | 📋 | `detect_wdc_margin_lost` | `wdc_margin_lost` | trajectory |
| D-074 | ✅ | `detect_wcc_contribution` | `wcc_contribution` | head-to-head |
| D-075 | ✅ | `detect_decisive_wcc_year` | `decisive_wcc_year` | head-to-head |
| D-097 | 📋 | `detect_widest_wdc_margin` | `widest_wdc_margin` | records |

## 13 · Current Form

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-076 | 📋 | `detect_current_form_summary` | `current_form` | current-form |
| D-077 | 📋 | `detect_current_season_position` | `current_standings` | current-form |
| D-078 | 📋 | `detect_current_season_best` | `current_season_best_result` | current-form |
| D-079 | 📋 | `detect_recent_form_window` | `recent_form_summary` | current-form |

## 14 · Head-to-Head (schema-blocked — needs team-roster parsing)

| ID | Status | Detector | Insight kinds | Card(s) |
|---|---|---|---|---|
| D-080 | 🔬 | `detect_teammate_h2h` | `teammate_h2h_record` | head-to-head |
| D-081 | 🔬 | `detect_team_contribution` | `team_contribution_pct` | head-to-head |
| D-082 | 🔬 | `detect_wcc_seasons_summary` | `wcc_seasons_summary` | head-to-head |
| D-083 | 🔬 | `detect_team_roster_history` | `team_roster_history` | head-to-head |
| D-084 | 🔬 | `detect_h2h_vs_wdc_winners` | `h2h_vs_champion` | head-to-head |
| D-085 | 🔬 | `detect_h2h_vs_specific_driver` | `h2h_vs_driver` | head-to-head |
| D-086 | 🔬 | `detect_first_wcc_year` | `first_wcc_year` | head-to-head |
| D-087 | 🔬 | `detect_only_constant_team_member` | `only_constant_team_member` | head-to-head, uniqueness |

## 15 · Data-Limited (out of scope without new data)

| ID | Status | Detector | Reason |
|---|---|---|---|
| D-088 | 🔬 | `detect_comeback_drive` | Needs qualifying-vs-race position (we only have pole flag) |
| D-089 | 🔬 | `detect_pole_margin` | Needs qualifying time gaps |
| D-090 | 🔬 | `detect_wet_weather_specialist` | No conditions data |
| D-091 | 🔬 | `detect_pit_strategy_pattern` | No pit-stop data |
| D-092 | 🔬 | `detect_lap_pace_anomaly` | No lap times |
| D-093 | 🔬 | `detect_sector_specialist` | No sector data |

---

## Change log

- **Renamed D-045 `triple_crown_weekends` → `hat_trick_races`.** Aligns with
  F1 usage: a *hat-trick* is pole + fastest lap + win in the same race (what
  this detector measures); the *triple crown* is wins at three landmark
  events, which we do not model. Function, insight kind, snippet template,
  scoring rule, card mapping and docs all updated.
- **Batch +6 shipped (race-week, streak & league-record focus).**
  D-104 (`fastest_lap_streak`, streaks), D-105
  (`consecutive_podium_weekends`, streaks — consecutive race weeks with ≥1
  podium; distinct from D-025's consecutive *seasons*), D-106
  (`only_race_week_sweep`, uniqueness — league-only to win every race in a
  venue weekend), D-107 (`only_perfect_podium_venue`, uniqueness — 100%
  podium rate at ≥1 venue with min-4 starts, cohort-framed), plus pulled
  forward D-095 (`league_record_wins_season`) and D-096
  (`league_record_weighted_score`) — both records, fire only for the
  all-time mark holder. League records carry a `historic_first` scoring
  bonus.
- **Batch +5 shipped (uniqueness focus).** D-094 (`wins_without_poles`),
  D-098 (`won_both_classes`), D-099 (`venue_multi_season_podium` + aggregate
  `_career` variant), D-101 (`multiple_wcc_club`), D-102 (`multiple_wdc_club`).
  All four uniqueness detectors use a cohort framing (driver count in the
  qualifying set) and adjust headline copy when the cohort is just one.
- **Bug fix: `detect_seasons_always_scoring` (D-009)** now requires zero DNS
  and full attendance — previously a missed weekend with otherwise-perfect
  scoring still qualified.
- **Batch +10 planned (uniqueness focus).** D-094 (`wins_without_poles`),
  D-095 (`league_record_wins_season`), D-096 (`league_record_weighted_score`),
  D-097 (`widest_wdc_margin`), D-098 (`won_both_classes`),
  D-099 (`venue_multi_season_podium`), D-100 (`fl_every_season`),
  D-101 (`multiple_wcc_club`), D-102 (`multiple_wdc_club`) — all 📋 Planned.
  D-103 (`wcc_varied_teammates`) marked 🔬 (requires cross-referencing team
  rosters across seasons to identify distinct teammate configurations).
- **Batch +15 shipped.** D-006, D-008, D-009 (streaks);
  D-014, D-015, D-045 (records); D-017, D-018 (firsts);
  D-032 (trajectory); D-038 (splits); D-052 (peer-rank);
  D-066, D-067 (uniqueness); D-074, D-075 (margins).
  Foundation for the margins detectors required a new
  `team_standings` table parsed from each season's
  "### Team Standings (WCC)" subsection.
- **Cards architecture introduced.** Detector outputs now flow through
  themed cards; the `Card(s)` column shows the mapping.
- **Detectors numbered.** Stable IDs (`D-001`–`D-093`) assigned for
  reference in future work.
- _Initial catalog created._ Captures shipped detectors and the brainstorm.
