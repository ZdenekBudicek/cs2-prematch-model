# CS2 Prematch Model

Pre-match win probabilities for professional Counter-Strike 2, built from public Liquipedia results and compared with the Pinnacle market.

**Result:** the model is not as accurate as the market, and it shows no edge. On 770 series with pre-match prices, log loss is 0.610 for the model and 0.580 for Pinnacle.

| 770 priced series, 26 Apr to 5 Nov 2026 | Log loss | Brier | Accuracy |
|---|---|---|---|
| Elo only | 0.636 | 0.222 | 63.1% |
| First model, Elo and form | 0.638 | 0.223 | 63.2% |
| **This model** | **0.610** | 0.210 | 66.4% |
| Pinnacle, margin removed | 0.580 | 0.198 | 70.8% |

19 of these series are from April, inside the window where the inputs were chosen, which never used market data. Without them, on 751 series, the model has log loss 0.609 and accuracy 66.3%, and Pinnacle 0.584 and 70.6%.

Figures are from data corrected on 14 November 2026: the parser had dropped maps that went to overtime. The model card has the details.

The [expert dashboard](https://zdenekbudicek.github.io/cs2/) shows team trends, player ratings, roster changes, map pool shifts and a match price tool. Method and limits are in [MODEL_CARD.md](MODEL_CARD.md).

## What it does

- Rates teams with round-margin Elo and rates players across teams, so a transfer carries a player's rating.
- Adds recent form, rest, player experience and recent player trends.
- Predicts the series winner before the veto, with separate weights for BO1 and for BO3 and BO5.
- Tests on later months with expanding walk-forward validation.

## Keeping the future out

`tests/test_model.py` checks that future and same-day results cannot reach a prediction, that qualifiers do not inherit rosters of teams that advanced, that one known roster gives no signal, and that live features match training features.

## Project layout

| File | Purpose |
|---|---|
| `cs2_core.py` | Data loading, ratings, features, fitting, scoring |
| `cs2_model.py` | Model training and evaluation, writes `results.json` |
| `cs2_expert_data.py`, `cs2_expert_prices.py` | Aggregates and prices for the dashboard |
| `dashboard/` | The expert dashboard page and its aggregated data |
| `cs2_liquipedia_maps.py`, `cs2_event_features.py`, `cs2_team_aliases.py` | Liquipedia collection and parsing |
| `cs2_odds_download.py` | Downloads prices for the market comparison, private output |

## Running it

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements.txt
.venv/Scripts/python -m pytest -q tests
```

The tests use synthetic data and need nothing else. The model needs data you collect yourself, because this repository includes none:

1. Put your contact address in `contact.txt`, which Liquipedia's API terms require in the User-Agent.
2. Run `cs2_liquipedia_maps.py`, `cs2_team_aliases.py` and `cs2_event_features.py`. These are paced to Liquipedia's limits.
3. Run `cs2_model.py`, then `cs2_expert_data.py` and `cs2_expert_prices.py`.

The market comparison also needs `ODDSPAPI_KEY` and `cs2_odds_download.py`. Without that file, `cs2_model.py` skips the comparison.

## How it was built

Built by Zdeněk Budíček with Claude Code as a coding and review assistant.

## Data and credits

Map results and rosters come from [Liquipedia](https://liquipedia.net/counterstrike/), under CC-BY-SA 3.0. Figures derived from them are shared under the same licence. Pinnacle prices are used only in aggregated comparisons, and no individual price is published. Raw data is not published here.

The code is under the MIT License. This is a research project, not betting advice.
