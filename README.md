# Blackjack Bot

A blackjack-playing bot in plain Python (no dependencies). It plays perfect basic strategy and can optionally count cards with the Hi-Lo system, raising its bets and making key index plays when the count favours the player.

## GUI

```bash
python3 blackjack_gui.py
```

This opens a blackjack table in your browser. Two modes:

- **You play**: bet, then hit / stand / double / split (keys `H` `S` `D` `P`, `Space` to deal). The bot grades every decision and tracks your accuracy. Tick **Show bot's advice** to highlight its move.
- **Bot plays**: step through the bot's moves one at a time, or auto-play at up to turbo speed.

The sidebar shows the live Hi-Lo count, the bot's suggested bet, session stats and a bankroll chart. Toggle **Card counting** to compare counting against flat-bet basic strategy. The same rule flags as the command-line tool work here too, e.g. `python3 blackjack_gui.py --h17 --decks 2`.

## Command line

Watch the bot play:

```bash
python3 blackjack_bot.py play --hands 10 --count
```

Ask what to do with a hand (your cards, then the dealer's upcard; `--tc` adds count-based plays):

```bash
python3 blackjack_bot.py advise A 7 --dealer 6
python3 blackjack_bot.py advise 10 6 --dealer 10 --tc 1
```

Simulate many hands:

```bash
python3 blackjack_bot.py sim --hands 1000000 --count
```

### Table rules

| Flag | Meaning | Default |
|---|---|---|
| `--decks N` | decks in the shoe | 6 |
| `--h17` | dealer hits soft 17 | stands |
| `--payout X` | blackjack payout (1.5 = 3:2, 1.2 = 6:5) | 1.5 |
| `--no-das` | no double after split | DAS allowed |
| `--pen F` | fraction of shoe dealt before reshuffle | 0.75 |

## Results (1,000,000 hands, default rules)

| Mode | Player edge |
|---|---|
| Basic strategy, flat bet | −0.32% ± 0.20% |
| Hi-Lo counting, 1–8 bet spread | +0.47% ± 0.28% |
