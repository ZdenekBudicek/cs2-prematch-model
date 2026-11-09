# Model card

**Headline: the model is clearly better than a team rating alone, but the market is still better and the model shows no edge.**

## Data

Map results and event rosters from Liquipedia, S, A and B-tier events, October 2023 to November 2026. 12,750 series after parsing. Series format, final score and winner come from the maps recorded on Liquipedia.

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

| 676 priced series, 26 Apr to 5 Nov 2026 | Log loss | Brier | Accuracy |
|---|---|---|---|
| Elo only | 0.6368 | 0.2225 | 63.6% |
| Elo and form | 0.6419 | 0.2244 | 62.7% |
| **This model** | **0.6070** | 0.2088 | 67.2% |
| Pinnacle, margin removed | 0.5759 | 0.1955 | 71.7% |

Market advantage: 0.0311, 95% interval 0.0093 to 0.0533.

17 of the 676 series are from April, inside the window used for the earlier input choice, which never used market data. Without them, on 659 series from 1 May: model 0.6047 and 67.2%, Pinnacle 0.5782 and 71.6%, market advantage 0.0265, interval 0.0052 to 0.0467.

All 2,906 series from May 2026: log loss 0.5747, accuracy 69.7%, against Elo only at 0.6341 and 63.5%. Log loss is not comparable with the priced series, because the matches differ.

## Roster changes

Series from May 2026 where a team changed players (stability under 0.8, 394 series): 0.6074 for a team-only model, 0.4988 with player data, gain 0.1086, interval 0.0742 to 0.1416. Stable rosters (2,412 series): gain 0.0457, interval 0.0348 to 0.0567. These use event rosters, so they carry some hindsight about who played.

## Limits

- Map records can miss maps. In a check against complete results, about 8% of series had the wrong format and 11% the wrong score, and a third map looked rarer than it is (34.8% against 36.3% of BO3 series). For that reason total maps, handicap and exact score are not priced.
- BO1 and BO3 weights are affected by the same format errors.
- Ratings come from results and rosters. There are no rounds, kills, ADR, economy, utility or CT and T sides.
- About six months of prices from one bookmaker, on the series that could be matched.
- Event rosters are known only after they are announced. No live forward test has been run on this version.
- Lower-tier teams can hold inflated ratings when they rarely meet the top teams.

This is research, not a production price and not betting advice.
