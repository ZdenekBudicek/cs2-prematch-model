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

## Limits

- Series format and score are still inferred from the maps held, not read from a schedule. In a check against complete series results from a second source, 0.7% of 9,166 series had the wrong format and 1.3% the wrong score. Before the overtime correction the same check gave 12.2% and 16.4%, and a third map looked rarer than it is (35.1% of BO3 series from May 2026, now 40.7%).
- Total maps, handicap and exact score are not priced in this version.
- The input list was chosen on the uncorrected data and was not selected again.
- Ratings come from results and rosters. There are no rounds, kills, ADR, economy, utility or CT and T sides.
- About six months of prices from one bookmaker, on the series that could be matched.
- Event rosters are known only after they are announced. No live forward test has been run on this version.
- Lower-tier teams can hold inflated ratings when they rarely meet the top teams.

This is research, not a production price and not betting advice.
