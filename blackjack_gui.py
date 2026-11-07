#!/usr/bin/env python3
"""
Browser GUI for the blackjack bot.

  python3 blackjack_gui.py              opens the table in your browser
  python3 blackjack_gui.py --h17 --decks 2 --port 9000 --no-browser

Two modes: play hands yourself (with the bot grading every decision),
or watch the bot play, one step at a time or on auto-play.
"""
import argparse
import json
import os
import random
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

from blackjack_bot import (ACTION_NAMES, Rules, Shoe, bet_units, decide,
                           is_blackjack, total, value)

SUITS = ['♠', '♥', '♦', '♣']
PAGE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'blackjack_gui.html')


def ranks(cards):
    return [c['rank'] for c in cards]


class Game:
    """Step-by-step blackjack game that a human or the bot can drive."""

    def __init__(self, rules, seed=None):
        self.rules = rules
        self.rng = random.Random(seed)
        self.counting = True
        self.reset()

    def reset(self):
        self.shoe = Shoe(self.rules, self.rng)
        self.bank = 0.0
        self.history = [0.0]
        self.stats = {'hands': 0, 'wagered': 0.0, 'wins': 0, 'losses': 0,
                      'pushes': 0, 'decisions': 0, 'matched': 0}
        self.phase = 'idle'          # idle -> player -> done
        self.hands, self.dealer = [], []
        self.hole_hidden = False
        self.round_net = 0.0
        self.message = 'Fresh shoe. Place a bet and deal.'
        self.feedback = ''
        self.shuffled = False

    # ---------------------------------------------------------------- helpers

    def _card(self, seen=True):
        return {'rank': self.shoe.draw(seen), 'suit': self.rng.choice(SUITS)}

    def _reveal(self):
        if self.hole_hidden:
            self.shoe.reveal(self.dealer[1]['rank'])
            self.hole_hidden = False

    def legal(self):
        if self.phase != 'player':
            return []
        h = self.hands[self.active]
        c = ranks(h['cards'])
        acts = ['H', 'S']
        if len(c) == 2 and (len(self.hands) == 1 or self.rules.das):
            acts.append('D')
        if (len(c) == 2 and len(self.hands) < self.rules.max_hands
                and value(c[0]) == value(c[1]) and not h['split_aces']):
            acts.append('P')
        return acts

    def advice(self):
        if self.phase != 'player':
            return None
        acts = self.legal()
        tc = self.shoe.true_count() if self.counting else None
        return decide(ranks(self.hands[self.active]['cards']), self.dealer[0]['rank'],
                      'D' in acts, 'P' in acts, self.rules, tc)

    # ---------------------------------------------------------------- actions

    def deal(self, bet, by_bot=False):
        if self.phase == 'player':
            raise ValueError('Finish the current hand first.')
        bet = max(1, min(int(bet), 100))
        self.shuffled = self.shoe.needs_shuffle()
        if self.shuffled:
            self.shoe.shuffle()
        self.feedback = ''
        player = [self._card()]
        up = self._card()
        player.append(self._card())
        hole = self._card(seen=False)
        self.dealer = [up, hole]
        self.hole_hidden = True
        self.base_bet = bet
        self.hands = [{'cards': player, 'bet': bet, 'split_aces': False,
                       'done': False, 'result': ''}]
        self.active = 0
        self.round_net = 0.0
        self.round_wagered = bet

        insurance = 0.0
        if up['rank'] == 'A' and by_bot and self.counting and self.shoe.true_count() >= 3:
            insurance = bet / 2
            self.round_wagered += insurance

        h = self.hands[0]
        if is_blackjack(ranks(self.dealer)):
            self._reveal()
            if is_blackjack(ranks(player)):
                h['result'] = 'Push'
            else:
                h['result'] = 'Lose'
                self.round_net -= bet
            self.round_net += insurance * 2
            return self._finish('Dealer has blackjack.' +
                                (' Insurance pays 2:1.' if insurance else ''))
        self.round_net -= insurance

        if is_blackjack(ranks(player)):
            self._reveal()
            h['result'] = 'Blackjack'
            self.round_net += bet * self.rules.bj_payout
            return self._finish('Blackjack!')

        self.phase = 'player'
        self.message = ('Bot took insurance (true count +3 or higher). ' if insurance else '') + \
            'Hit, stand, double or split?'

    def act(self, action, by_bot=False):
        if action not in self.legal():
            raise ValueError('That move is not allowed right now.')
        best = self.advice()
        if not by_bot:
            self.stats['decisions'] += 1
            if action == best:
                self.stats['matched'] += 1
                self.feedback = f'✓ {ACTION_NAMES[action].title()} was the right play.'
            else:
                self.feedback = (f'✗ You chose {ACTION_NAMES[action].lower()}; '
                                 f'the bot would {ACTION_NAMES[best].lower()}.')
        h = self.hands[self.active]
        if action == 'H':
            h['cards'].append(self._card())
        elif action == 'S':
            h['done'] = True
        elif action == 'D':
            self.round_wagered += h['bet']
            h['bet'] *= 2
            h['cards'].append(self._card())
            h['done'] = True
        elif action == 'P':
            aces = h['cards'][0]['rank'] == 'A'
            h['split_aces'] = aces
            self.hands.insert(self.active + 1, {'cards': [h['cards'].pop()], 'bet': self.base_bet,
                                                'split_aces': aces, 'done': False, 'result': ''})
            self.round_wagered += self.base_bet
        self._advance()

    def bot_step(self):
        """One bot move: deal a new round, or make the next decision."""
        if self.phase == 'player':
            self.act(self.advice(), by_bot=True)
        else:
            bet = bet_units(self.shoe.true_count()) if self.counting else 1
            self.deal(bet, by_bot=True)

    # ---------------------------------------------------------------- flow

    def _advance(self):
        while self.active < len(self.hands):
            h = self.hands[self.active]
            if len(h['cards']) == 1:          # split hand gets its second card
                h['cards'].append(self._card())
                if h['split_aces']:
                    h['done'] = True
            if h['done'] or total(ranks(h['cards']))[0] >= 21:
                h['done'] = True
                self.active += 1
                continue
            if len(self.hands) > 1:
                self.message = f'Playing hand {self.active + 1} of {len(self.hands)}.'
            return
        self._dealer_play()

    def _dealer_play(self):
        self._reveal()
        if any(total(ranks(h['cards']))[0] <= 21 for h in self.hands):
            while True:
                t, soft = total(ranks(self.dealer))
                if t < 17 or (t == 17 and soft and self.rules.h17):
                    self.dealer.append(self._card())
                else:
                    break
        dt = total(ranks(self.dealer))[0]
        for h in self.hands:
            pt = total(ranks(h['cards']))[0]
            if pt > 21:
                h['result'], delta = 'Bust', -h['bet']
            elif dt > 21 or pt > dt:
                h['result'], delta = 'Win', h['bet']
            elif pt < dt:
                h['result'], delta = 'Lose', -h['bet']
            else:
                h['result'], delta = 'Push', 0
            self.round_net += delta
        if all(h['result'] == 'Bust' for h in self.hands):
            msg = 'Bust.'
        else:
            msg = 'Dealer busts!' if dt > 21 else f'Dealer stands on {dt}.'
        self._finish(msg)

    def _finish(self, msg):
        self.phase = 'done'
        self.bank += self.round_net
        self.history.append(self.bank)
        s = self.stats
        s['hands'] += 1
        s['wagered'] += self.round_wagered
        if self.round_net > 0:
            s['wins'] += 1
        elif self.round_net < 0:
            s['losses'] += 1
        else:
            s['pushes'] += 1
        self.message = f'{msg} Round: {self.round_net:+g}.'

    # ---------------------------------------------------------------- view

    def state(self):
        tc = self.shoe.true_count()
        dealer = [None if (i == 1 and self.hole_hidden) else c for i, c in enumerate(self.dealer)]
        shown = [c['rank'] for c in dealer if c]
        dt, dsoft = total(shown) if shown else (0, False)
        hands = []
        for i, h in enumerate(self.hands):
            t, soft = total(ranks(h['cards']))
            hands.append({'cards': h['cards'], 'bet': h['bet'], 'total': t, 'soft': soft,
                          'result': h['result'],
                          'active': self.phase == 'player' and i == self.active})
        hist = self.history[-500:]
        return {
            'phase': self.phase,
            'dealer': dealer, 'dealer_total': dt, 'dealer_soft': dsoft,
            'hole_hidden': self.hole_hidden,
            'hands': hands,
            'legal': self.legal(), 'advice': self.advice(),
            'message': self.message, 'feedback': self.feedback, 'shuffled': self.shuffled,
            'count': {'running': self.shoe.running, 'true': round(tc, 1),
                      'decks_left': round(len(self.shoe.cards) / 52, 1),
                      'suggested_bet': bet_units(tc)},
            'counting': self.counting,
            'bank': self.bank, 'round_net': self.round_net,
            'stats': self.stats,
            'history': hist, 'history_start': len(self.history) - len(hist),
            'rules': {'decks': self.rules.decks, 'h17': self.rules.h17,
                      'payout': self.rules.bj_payout, 'das': self.rules.das},
        }


def make_handler(game):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, code, data, ctype):
            if isinstance(data, str):
                data = data.encode()
            self.send_response(code)
            self.send_header('Content-Type', ctype)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(data)

        def _json(self, obj, code=200):
            self._send(code, json.dumps(obj), 'application/json')

        def do_GET(self):
            if self.path in ('/', '/index.html'):
                with open(PAGE_PATH, encoding='utf-8') as f:
                    self._send(200, f.read(), 'text/html; charset=utf-8')
            elif self.path == '/api/state':
                self._json(game.state())
            else:
                self._send(404, 'Not found', 'text/plain')

        def do_POST(self):
            length = int(self.headers.get('Content-Length') or 0)
            try:
                body = json.loads(self.rfile.read(length) or b'{}')
            except json.JSONDecodeError:
                body = {}
            cmd = self.path.rsplit('/', 1)[-1]
            try:
                if cmd == 'deal':
                    game.deal(body.get('bet', 1))
                elif cmd == 'act':
                    game.act(body.get('action'))
                elif cmd == 'bot':
                    game.bot_step()
                elif cmd == 'counting':
                    game.counting = bool(body.get('on'))
                elif cmd == 'reset':
                    game.reset()
                else:
                    return self._send(404, 'Not found', 'text/plain')
            except ValueError as e:
                return self._json({'error': str(e)}, 400)
            self._json(game.state())

    return Handler


def main():
    ap = argparse.ArgumentParser(description="Blackjack bot GUI")
    ap.add_argument('--decks', type=int, default=6)
    ap.add_argument('--h17', action='store_true', help="dealer hits soft 17")
    ap.add_argument('--payout', type=float, default=1.5, help="blackjack payout (1.5 = 3:2)")
    ap.add_argument('--no-das', action='store_true', help="no double after split")
    ap.add_argument('--pen', type=float, default=0.75, help="shoe penetration")
    ap.add_argument('--port', type=int, default=8765)
    ap.add_argument('--seed', type=int)
    ap.add_argument('--no-browser', action='store_true', help="don't open a browser tab")
    args = ap.parse_args()

    rules = Rules(decks=args.decks, h17=args.h17, bj_payout=args.payout,
                  das=not args.no_das, penetration=args.pen)
    game = Game(rules, args.seed)
    try:
        server = HTTPServer(('127.0.0.1', args.port), make_handler(game))
    except OSError:
        server = HTTPServer(('127.0.0.1', 0), make_handler(game))  # port busy: pick any free one
    url = f'http://127.0.0.1:{server.server_address[1]}/'
    print(f'Blackjack table running at {url}  (Ctrl+C to quit)')
    if not args.no_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print('\nBye!')


if __name__ == '__main__':
    main()
