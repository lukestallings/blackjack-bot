#!/usr/bin/env python3
"""
Blackjack bot: perfect basic strategy + optional Hi-Lo card counting.

Commands:
  python3 blackjack_bot.py play  [--hands 10] [--count]      watch the bot play hands
  python3 blackjack_bot.py sim   [--hands 200000] [--count]  simulate and report results
  python3 blackjack_bot.py advise A 7 --dealer 6 [--tc 2]    ask the bot what to do
"""
import argparse
import math
import random
from dataclasses import dataclass

RANKS = ['2', '3', '4', '5', '6', '7', '8', '9', '10', 'J', 'Q', 'K', 'A']
ACTION_NAMES = {'H': 'HIT', 'S': 'STAND', 'D': 'DOUBLE', 'P': 'SPLIT'}


def value(rank):
    if rank == 'A':
        return 11
    if rank in ('10', 'J', 'Q', 'K'):
        return 10
    return int(rank)


# Hi-Lo counting tags: 2-6 = +1, 7-9 = 0, 10-A = -1
HILO = {r: (1 if value(r) <= 6 else -1 if value(r) >= 10 else 0) for r in RANKS}


@dataclass
class Rules:
    decks: int = 6
    h17: bool = False          # dealer hits soft 17?
    bj_payout: float = 1.5     # 3:2
    das: bool = True           # double after split allowed
    max_hands: int = 4         # max hands after splitting
    penetration: float = 0.75  # fraction of shoe dealt before reshuffle


def total(cards):
    """Return (best total, is_soft)."""
    t = sum(value(c) for c in cards)
    aces = cards.count('A')
    while t > 21 and aces:
        t -= 10
        aces -= 1
    return t, aces > 0


def is_blackjack(cards):
    return len(cards) == 2 and total(cards)[0] == 21


# ---------------------------------------------------------------- strategy

def basic_strategy(cards, up, can_double, can_split, rules):
    d = value(up)  # dealer upcard 2..11
    t, soft = total(cards)

    def dbl(fallback='H'):
        return 'D' if can_double else fallback

    # Pairs
    if can_split and len(cards) == 2 and value(cards[0]) == value(cards[1]):
        p = value(cards[0])
        das = rules.das
        split = {
            11: True,
            10: False,
            9: d not in (7, 10, 11),
            8: True,
            7: d <= 7,
            6: d <= 6 if das else 3 <= d <= 6,
            5: False,
            4: d in (5, 6) if das else False,
            3: d <= 7 if das else 4 <= d <= 7,
            2: d <= 7 if das else 4 <= d <= 7,
        }[p]
        if split:
            return 'P'

    # Soft totals
    if soft:
        if t >= 20:
            return 'S'
        if t == 19:
            return dbl('S') if (rules.h17 and d == 6) else 'S'
        if t == 18:
            if 3 <= d <= 6 or (rules.h17 and d == 2):
                return dbl('S')
            return 'S' if d in (2, 7, 8) else 'H'
        if t == 17:
            return dbl() if 3 <= d <= 6 else 'H'
        if t in (15, 16):
            return dbl() if 4 <= d <= 6 else 'H'
        if t in (13, 14):
            return dbl() if 5 <= d <= 6 else 'H'
        return 'H'

    # Hard totals
    if t >= 17:
        return 'S'
    if t >= 13:
        return 'S' if d <= 6 else 'H'
    if t == 12:
        return 'S' if 4 <= d <= 6 else 'H'
    if t == 11:
        return dbl() if (d <= 10 or rules.h17) else 'H'
    if t == 10:
        return dbl() if d <= 9 else 'H'
    if t == 9:
        return dbl() if 3 <= d <= 6 else 'H'
    return 'H'


def count_deviation(cards, up, tc, can_double, can_split):
    """Key Illustrious-18 index plays. Returns an action or None."""
    d = value(up)
    t, soft = total(cards)
    if soft:
        return None
    if can_split and len(cards) == 2 and value(cards[0]) == value(cards[1]) == 10:
        if (d == 5 and tc >= 5) or (d == 6 and tc >= 4):
            return 'P'
        return None
    if t == 16 and d == 10:
        return 'S' if tc >= 0 else 'H'
    if t == 15 and d == 10 and tc >= 4:
        return 'S'
    if t == 12 and d == 3 and tc >= 2:
        return 'S'
    if t == 12 and d == 2 and tc >= 3:
        return 'S'
    if t == 12 and d == 4 and tc < 0:
        return 'H'
    if t == 13 and d == 2 and tc < -1:
        return 'H'
    if can_double and len(cards) == 2:
        if t == 11 and d == 11 and tc >= 1:
            return 'D'
        if t == 10 and d == 10 and tc >= 4:
            return 'D'
        if t == 10 and d == 11 and tc >= 4:
            return 'D'
        if t == 9 and d == 2 and tc >= 1:
            return 'D'
        if t == 9 and d == 7 and tc >= 3:
            return 'D'
    return None


def decide(cards, up, can_double, can_split, rules, tc=None):
    action = basic_strategy(cards, up, can_double, can_split, rules)
    if tc is not None and action != 'P':
        dev = count_deviation(cards, up, tc, can_double, can_split)
        if dev:
            return dev
    return action


def bet_units(tc):
    """Bet ramp (1-8 spread) keyed on true count."""
    tc = math.floor(tc)
    if tc <= 1:
        return 1
    return {2: 2, 3: 4, 4: 6}.get(tc, 8)


# ---------------------------------------------------------------- game engine

class Shoe:
    def __init__(self, rules, rng):
        self.rules, self.rng = rules, rng
        self.shuffle()

    def shuffle(self):
        self.cards = [r for r in RANKS for _ in range(4 * self.rules.decks)]
        self.rng.shuffle(self.cards)
        self.running = 0
        self.cut = int(len(self.cards) * (1 - self.rules.penetration))

    def draw(self, seen=True):
        c = self.cards.pop()
        if seen:
            self.running += HILO[c]
        return c

    def reveal(self, card):
        self.running += HILO[card]

    def needs_shuffle(self):
        return len(self.cards) <= self.cut

    def true_count(self):
        return self.running / max(len(self.cards) / 52, 0.5)


def fmt(cards):
    t, soft = total(cards)
    return f"[{' '.join(cards)}] = {'soft ' if soft else ''}{t}"


def play_round(shoe, rules, bet, counting, log=lambda *a: None):
    """Play one round. Returns (net win, total amount wagered)."""
    player = [shoe.draw()]
    up = shoe.draw()
    player.append(shoe.draw())
    hole = shoe.draw(seen=False)
    dealer = [up, hole]
    net, wagered = 0.0, bet
    log(f"  Bet {bet:g}. Player {fmt(player)}  |  Dealer shows {up}")

    # Insurance: only worth it at true count >= +3
    insurance = 0.0
    if up == 'A' and counting and shoe.true_count() >= 3:
        insurance = bet / 2
        wagered += insurance
        log(f"  Bot takes insurance ({insurance:g})")

    if is_blackjack(dealer):
        shoe.reveal(hole)
        log(f"  Dealer has blackjack {fmt(dealer)}")
        net = 0.0 if is_blackjack(player) else -bet
        net += insurance * 2
        return net, wagered
    net -= insurance

    if is_blackjack(player):
        shoe.reveal(hole)
        log("  BLACKJACK!")
        return net + bet * rules.bj_payout, wagered

    hands = [{'cards': player, 'bet': bet, 'split_aces': False}]
    i = 0
    while i < len(hands):
        h = hands[i]
        c = h['cards']
        while True:
            if len(c) == 1:  # second card for a split hand
                c.append(shoe.draw())
                if h['split_aces']:
                    break
            t, _ = total(c)
            if t >= 21:
                break
            first_two = len(c) == 2
            can_double = first_two and (len(hands) == 1 or rules.das)
            can_split = (first_two and len(hands) < rules.max_hands
                         and value(c[0]) == value(c[1]) and not h['split_aces'])
            tc = shoe.true_count() if counting else None
            a = decide(c, up, can_double, can_split, rules, tc)
            log(f"  Hand {i + 1}: {fmt(c)} -> {ACTION_NAMES[a]}")
            if a == 'S':
                break
            if a == 'H':
                c.append(shoe.draw())
            elif a == 'D':
                wagered += h['bet']
                h['bet'] *= 2
                c.append(shoe.draw())
                break
            elif a == 'P':
                aces = c[0] == 'A'
                h['split_aces'] = aces
                hands.insert(i + 1, {'cards': [c.pop()], 'bet': bet, 'split_aces': aces})
                wagered += bet
        log(f"  Hand {i + 1} final: {fmt(c)}")
        i += 1

    shoe.reveal(hole)
    if any(total(h['cards'])[0] <= 21 for h in hands):
        while True:
            t, soft = total(dealer)
            if t < 17 or (t == 17 and soft and rules.h17):
                dealer.append(shoe.draw())
            else:
                break
    dt = total(dealer)[0]
    log(f"  Dealer: {fmt(dealer)}{'  BUST' if dt > 21 else ''}")

    for h in hands:
        pt = total(h['cards'])[0]
        if pt > 21 or (dt <= 21 and pt < dt):
            net -= h['bet']
        elif dt > 21 or pt > dt:
            net += h['bet']
    return net, wagered


# ---------------------------------------------------------------- commands

def cmd_play(args, rules):
    rng = random.Random(args.seed)
    shoe = Shoe(rules, rng)
    bank = 0.0
    for n in range(1, args.hands + 1):
        if shoe.needs_shuffle():
            shoe.shuffle()
            print("  ** shuffle **")
        tc = shoe.true_count()
        bet = bet_units(tc) if args.count else 1
        extra = f" (running {shoe.running}, true {tc:+.1f})" if args.count else ""
        print(f"Hand #{n}{extra}")
        net, _ = play_round(shoe, rules, bet, args.count, log=print)
        bank += net
        print(f"  Result: {net:+g}   Bankroll: {bank:+g}\n")


def cmd_sim(args, rules):
    rng = random.Random(args.seed)
    shoe = Shoe(rules, rng)
    net_total = wagered_total = sq = 0.0
    bank = peak = max_dd = 0.0
    for _ in range(args.hands):
        if shoe.needs_shuffle():
            shoe.shuffle()
        bet = bet_units(shoe.true_count()) if args.count else 1
        net, wagered = play_round(shoe, rules, bet, args.count)
        net_total += net
        wagered_total += wagered
        sq += net * net
        bank += net
        peak = max(peak, bank)
        max_dd = max(max_dd, peak - bank)
    n = args.hands
    mean = net_total / n
    sd = math.sqrt(sq / n - mean * mean)
    edge = net_total / wagered_total * 100
    err = sd / math.sqrt(n) / (wagered_total / n) * 100
    print(f"Rules: {rules.decks} decks, dealer {'hits' if rules.h17 else 'stands on'} soft 17, "
          f"BJ pays {rules.bj_payout:g}:1, DAS={'yes' if rules.das else 'no'}, "
          f"penetration {rules.penetration:.0%}")
    print(f"Mode:  {'Hi-Lo counting, 1-8 bet spread + index plays' if args.count else 'basic strategy, flat bet'}")
    print(f"Hands played:     {n:,}")
    print(f"Units wagered:    {wagered_total:,.0f}")
    print(f"Net result:       {net_total:+,.1f} units")
    print(f"Player edge:      {edge:+.3f}%  (± {2 * err:.3f}% at 95% confidence)")
    print(f"Win per hand:     {mean:+.4f} units  (SD {sd:.3f})")
    print(f"Max drawdown:     {max_dd:,.1f} units")


def cmd_advise(args, rules):
    cards = [c.upper() for c in args.cards]
    up = args.dealer.upper()
    for c in cards + [up]:
        if c not in RANKS:
            raise SystemExit(f"Unknown card '{c}'. Use 2-10, J, Q, K, A.")
    first_two = len(cards) == 2
    can_split = first_two and value(cards[0]) == value(cards[1])
    a = decide(cards, up, first_two, can_split, rules, args.tc)
    basic = basic_strategy(cards, up, first_two, can_split, rules)
    print(f"You: {fmt(cards)}   Dealer: {up}")
    print(f"Bot says: {ACTION_NAMES[a]}")
    if args.tc is not None:
        if a != basic:
            print(f"  (count deviation at TC {args.tc:+g}; basic strategy would {ACTION_NAMES[basic]})")
        print(f"  Suggested bet at TC {args.tc:+g}: {bet_units(args.tc)} unit(s)"
              + ("; take insurance" if up == 'A' and args.tc >= 3 else ""))


def main():
    ap = argparse.ArgumentParser(description="Blackjack playing bot")
    ap.add_argument('--decks', type=int, default=6)
    ap.add_argument('--h17', action='store_true', help="dealer hits soft 17")
    ap.add_argument('--payout', type=float, default=1.5, help="blackjack payout (1.5 = 3:2, 1.2 = 6:5)")
    ap.add_argument('--no-das', action='store_true', help="no double after split")
    ap.add_argument('--pen', type=float, default=0.75, help="shoe penetration")
    sub = ap.add_subparsers(dest='cmd', required=True)

    p = sub.add_parser('play', help="watch the bot play")
    p.add_argument('--hands', type=int, default=10)
    p.add_argument('--count', action='store_true', help="use Hi-Lo counting")
    p.add_argument('--seed', type=int)

    s = sub.add_parser('sim', help="simulate many hands")
    s.add_argument('--hands', type=int, default=200_000)
    s.add_argument('--count', action='store_true', help="use Hi-Lo counting")
    s.add_argument('--seed', type=int)

    a = sub.add_parser('advise', help="get the right play for a hand")
    a.add_argument('cards', nargs='+', help="your cards, e.g. A 7")
    a.add_argument('--dealer', required=True, help="dealer upcard")
    a.add_argument('--tc', type=float, help="current true count (enables index plays)")

    args = ap.parse_args()
    rules = Rules(decks=args.decks, h17=args.h17, bj_payout=args.payout,
                  das=not args.no_das, penetration=args.pen)
    {'play': cmd_play, 'sim': cmd_sim, 'advise': cmd_advise}[args.cmd](args, rules)


if __name__ == '__main__':
    main()
