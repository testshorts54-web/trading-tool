# trading-tool (paper-only research; not financial advice)
Never places orders, holds no keys, reads no accounts. `tests/test_no_live_code.py` fails if order/wallet/key code
or any POST other than the allowlisted Hyperliquid public info call appears. Risk defaults: 10% max position, 1% max risk.

    pip install -r requirements.txt            # Python 3.13; yfinance is the only third-party package used
    python3 sense.py                           # Part A: regime readout -> out/YYYY-MM-DD.md/.json
    python3 pipeline.py collect                # Part B: ideas + watch notes (scanner hits, volume flags, funding)
    python3 pipeline.py validate <id>          # costs (base/stress), IS/OOS, buy-and-hold, random-entry null, DSR, IC
    python3 pipeline.py risk <id> --entry P --equity E
    python3 pipeline.py log  <id> --entry P --equity E   # appends a paper row to trade-journal/paper-trades.csv
    python3 -m unittest discover -s tests -t .

**Part A** scores 9 equity rules (E1-E9) and BTC trend (C1); ETH, ADX/BB/TTM/Hurst, perp funding/OI/premium,
Hyperliquid-Kraken funding spread, Fear & Greed, 30-day stablecoin change and venue spread sanity are info rows.
Missing or stale data shows as UNKNOWN with the reason; nothing is estimated.
**Part B** ideas live in `ideas.json` (entry conditions, stop, target and/or time exit). Verdicts: INSUFFICIENT
(< 30 trades in IS or OOS), PASS (stress-cost OOS mean > 0, null p < 0.05, DSR >= 0.95 if variants > 1), else FAIL.
Risk needs a PASS, a written exit and a stop below entry; it warns on a risk-off regime and stops at a -4% paper day.
The simulator and stats guard live in `/workspace/backtest/btlib/{trades,stats}.py` (stdlib), per the plan.

Layout: `tt/{http,config,indicators,validate,risk,journal,predict}.py`, `tt/sources/` (equities, crypto, fred,
history, perps, sentiment, venues), `tt/regime/`, `tt/ideas/{schema,scanners}.py`, `tests/` (+ fixtures).
`tt/predict.py` (Kelly, dutch book, Polymarket parse) is P4 groundwork, not wired in. Ported from flow; see
/workspace/flow-review/refactor-notes.md.
