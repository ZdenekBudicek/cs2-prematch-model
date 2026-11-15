# Model card

**Headline: the model is clearly better than a team rating alone, but the market is still better and the model shows no edge.**

**Data correction, 14 Nov 2026:** the parser read overtime rounds from the wrong Liquipedia fields, so a map that went to overtime looked like 12-12 and was dropped. Only 11 of 24,262 maps had overtime. After the fix 3,128 of 27,375 do, which is 11.4%. The dropped maps were the reason for the wrong series formats and scores listed under Limits in the earlier version of this card. Round share in the ratings now uses the real round counts as well. All figures below are from the corrected data. Before the correction the model scored 0.6070 on 676 priced series against 0.5759 for Pinnacle.

## Data

Map results and event rosters from Liquipedia, S, A and B-tier events, October 2023 to November 2026. 14,319 series after parsing. Series format, final score and winner come from the maps recorded on Liquipedia.

Prices are the last saved Pinnacle prices before start, with a proportional margin removal. They are used only to measure the model.

## Model

Ridge logistic regression without an intercept, so swapping the teams flips the probability, with separate weights for BO1 and for BO3 and BO5.

| Input | Meaning |
|---|---|
| `elo` | Team Elo per map, K=32, scaled by round margin |
| `form` | Results over the last 10 maps |
| `pelo` | Mean player rating of the event roster, K=64, kept by a player across teams |
| `rest` | Days since the last series, capped at 30 |
| `pexp` | Maps played by the roster, on a log scale |
| `pfast` | Faster-moving player rating minus `pelo` |
| `prs` | Player rating based on share of rounds won |

The input list was carried over from an earlier private version of this project that used more data. It was not selected again here, so this version has no selection step of its own.

## Validation

Expanding walk-forward by folds. Results from each day reach the ratings only after that day. Tests are in `tests/test_model.py`.

| 770 priced series, 26 Apr to 5 Nov 2026 | Log loss | Brier | Accuracy |
|---|---|---|---|
| Elo only | 0.6361 | 0.2222 | 63.1% |
| Elo and form | 0.6382 | 0.2228 | 63.2% |
| **This model** | **0.6099** | 0.2105 | 66.4% |
| Pinnacle, margin removed | 0.5805 | 0.1977 | 70.8% |

Market advantage: 0.0294, 95% interval 0.0116 to 0.0484.

19 of the 770 series are from April, inside the window used for the earlier input choice, which never used market data. Without them, on 751 series from 1 May: model 0.6088 and 66.3%, Pinnacle 0.5837 and 70.6%, market advantage 0.0251, interval 0.0072 to 0.0435.

All 3,491 series from May 2026: log loss 0.5933, accuracy 67.9%, against Elo only at 0.6430 and 62.6%. The corrected data adds 585 series here, many of them close ones that had lost an overtime map, so this figure is higher than before the correction. Log loss is not comparable with the priced series, because the matches differ.

## Roster changes

Series from May 2026 where a team changed players (stability under 0.8, 458 series): 0.6202 for a team-only model, 0.5338 with player data, gain 0.0863, interval 0.0549 to 0.1168. Stable rosters (2,917 series): gain 0.0381, interval 0.0289 to 0.0473. These use event rosters, so they carry some hindsight about who played.

## Glicko-2: tested and rejected

Script: `cs2_glicko.py`, results in `cs2_glicko_results.json`, measured 15 Nov 2026. Glicko-2 gives each team a rating deviation that grows while it is inactive and shrinks as it plays, so it should help most for teams with little data.

Rules fixed before results were seen: each day is one rating period, so ratings stay frozen within a day. Settings were chosen on map log loss of Apr to Dec 2024, with the grid widened once because the first choice sat on its edge; the second choice (round-share scores, initial deviation 700, a quarter day per period) is also on its edge and was kept, as fixed. A Glicko input would join the model only with a gain of at least 0.0005 on May 2025 to Apr 2026. Later series and prices were read afterwards.

| | May 2025 to Apr 2026 | May 2026 onward |
|---|---|---|
| Model + Glicko rating and deviation term, gain | 0.0027 (0.0002 to 0.0052), passes the rule | -0.0007 (-0.0031 to 0.0016) |
| Glicko alone against Elo alone | -0.0016 (-0.0106 to 0.0075) | 0.6440 against 0.6428 |
| Teams with fewer than 30 earlier maps, model + Glicko | | -0.0026 (-0.0063 to 0.0010), 1,818 series |
| 770 priced series: model, with Glicko, Pinnacle | | 0.6105, 0.6069, 0.5805; gain 0.0035 (-0.0012 to 0.0080) |

It passed selection and did not hold up on later series, including the teams with little data, so it is not used. The player rating already carries much of what a deviation would add: a new team made of known players is not unknown. Map log loss pushed the deviation to its largest values and is a weak target for series inputs, but a different target was not tried, because it would be chosen after seeing these results.

## Limits

- Series format and score are still inferred from the maps held, not read from a schedule. In a check against complete series results from a second source, 0.7% of 9,166 series had the wrong format and 1.3% the wrong score. Before the overtime correction the same check gave 12.2% and 16.4%, and a third map looked rarer than it is (35.1% of BO3 series from May 2026, now 40.7%).
- Total maps, handicap and exact score are not priced in this version.
- The input list was chosen on the uncorrected data and was not selected again.
- Ratings come from results and rosters. There are no rounds, kills, ADR, economy, utility or CT and T sides.
- About six months of prices from one bookmaker, on the series that could be matched.
- Event rosters are known only after they are announced. A forward record started on 14 November 2026: prices for upcoming matches are saved to `forward_log.csv` before each match. It is too short to report.
- Lower-tier teams can hold inflated ratings when they rarely meet the top teams.

This is research, not a production price and not betting advice.
