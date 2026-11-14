# trading-tool
Quick use: readout `python3 sense.py` | validate `python3 pipeline.py validate <id>` | risk `python3 pipeline.py risk <id> --entry P --equity E` | log `python3 pipeline.py log <id> ...` (paper-only research; not financial advice)
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

Layout: `tt/{http,config,indicators,validate,risk,journal,predict,volprofile}.py`, `tt/sources/` (equities, crypto, fred,
history, perps, sentiment, venues), `tt/regime/`, `tt/ideas/{schema,scanners}.py`, `tests/` (+ fixtures).
`tt/predict.py` (Kelly, dutch book, Polymarket parse) is P4 groundwork, not wired in. Ported from flow; see
/workspace/flow-review/refactor-notes.md.

## Prediction-market scan (P4, paper only)
    python3 predict_scan.py --once                    # one scan; summary JSON to stdout, new signals -> out/predict/signals.jsonl
    python3 predict_scan.py --interval 300            # loop; heartbeat out/predict/heartbeat
    while sleep 120; do ./predict_watchdog.sh; done & # restart if dead or heartbeat stale (price-alert watchdog pattern)
    python3 predict_scan.py --once --log --equity E   # also log NEW flagged dutch_book/crypto_spot leads as paper rows
Data (GET only, no keys): Polymarket Gamma `/events` (top 100 by 24h volume + top 100 crypto) and CLOB `/book` for
candidates; spot from the Binance.US public websocket (flow's approach; read-only, nothing sent) with Binance.US/Coinbase/
Kraken REST median as fallback. Signals: `dutch_book` (neg-risk set, YES asks + taker fee rate*p*(1-p) from each market's
feeSchedule, >= 1% gap, >= 10 sets and >= $1 at the best ask level; Other/placeholder/augmented sets never flag),
`crypto_spot` ("price of X above/below $K on DATE" only; driftless lognormal with 100% annual vol; flags when side
prob >= 0.99 and edge >= 2c after fee with >= 10 shares at the ask; basis risk vs the market's resolution source),
`large_move` (|1h move| >= 10 pts, liquidity >= $10k, spread <= 5c, not near 0/1, one per event; info only, never logged).
Cross-venue gaps are UNKNOWN: Kalshi is not used (its Developer Agreement limits API data to members' own trading and its
data terms bar collecting/storing). Missing fee/price/spot -> UNKNOWN, never flagged. Paper size: 1% max loss
(`predict.size_binary`, binary contract can go to 0, so 1% binds before the 10% cap), capped by visible depth; journal
row has stop 0 / target 1. Terms: Polymarket ToS bars scraping/data-mining tools and redistribution to capital-markets
clients or data distributors; this is low-rate personal research on documented public endpoints, nothing redistributed.
polymarket.com trading is blocked for US persons (polymarket.us is the US venue), so leads are paper-only by design.


## Maker complement paper sim (paper only)
    python3 predict_maker_sim.py --minutes 45 --interval 60   # virtual bids on both sides; ledger in predict_paper/run-*/
    python3 predict_maker_sim.py --v2 --rebate --minutes 60 --interval 8 --shares 10
    python3 predict_maker_sim.py --v2 --universe 5m15m --minutes 45 --interval 2 --reprice-any --quiet-before-end 90
    python3 predict_maker_sim.py --v2 --universe 1h4h --minutes 45 --interval 3 --reprice-any --quiet-before-end 90
    python3 predict_maker_sim.py --taker-once                 # snapshot: YES+NO asks after taker fees
Flags: `--v2` (conservative fills, stagger first, stale pull 3¢, complete exit 300s, loss cap $0.50, prefer sports/politics/geopolitics),
`--universe slow|5m15m|1h4h` (market selection: 5m15m caps ~10 live windows, 1h4h caps ~15, slow keeps sports/politics/geopolitics),
`--reprice-any` (pull/reprice resting virtual quote on visible tick move of best bid),
`--quiet-before-end SEC` (pull fresh quotes and stop posting/repricing within SEC seconds of end; one-leg positions may complete or exit),
`--twap-window-end SEC` (default 120s; logs twap_log ledger row per market within window of expiry),
`--stale 0.03`, `--stagger first|both-small`, `--complete-sec 300`, `--loss-cap 0.50`, `--rebate` (runs second virtual book for maker rebates,
tracking spread_pnl, inventory_mark, est_rebate, liq_score separately), `--inv-cap 10`. Interval allows 2 or 3s (sleep min 2s when interval >= 2).
Exit fee uses feeSchedule rate; missing fee_rate falls back to 0.07 only for 5m15m/1h4h with ledger note (UNKNOWN otherwise).

## TWAP settlement & post-window analysis (paper only)
    python3 predict_twap_settle.py predict_paper/<run>
Reads `twap_log` rows from a 5m/15m or 1h/4h run, queries public Gamma events by slug and /v2/resolutions, logs book mids in last 60-120s,
event priceToBeat/finalPrice, implied outcome, and after-fee gap (executable ask vs mid mark). Writes `twap_settle.json` and `.jsonl`.

## Logical scan (paper only)
    python3 predict_logical_scan.py --once
    python3 predict_scan.py --logical
One-shot scan over Gamma events and CLOB books: (1) negRisk YES baskets (complete executable sets vs hidden-Other/incomplete sets,
plus informational NO-basket convert sketch), (2) strike-ladder and nested-deadline monotonicity, (3) duplicate same-event listings.
Writes to `predict_paper/logical-<timestamp>/{summary.json, signals.jsonl}`.
Rests a virtual bid on both outcomes of liquid binary markets so the pair sums to at most 1 minus a
margin (default 2c). Maker fee is 0. Fills are decided from public Data API v2 trades (taker SELL at
or through the bid) or a CLOB book print whose best ask is at or through the bid; at-touch fills are
optimistic on queue position. One-leg fills stay marked to mid until the other side fills or the
market settles. Rebates are not counted. Public GET only; no keys or live orders. Official taker
fee is C × rate × p × (1-p) (docs.polymarket.com/trading/fees, read 2026-11-14): crypto 0.07,
sports/economics/culture/weather/other 0.05, politics/finance/tech/mentions 0.04, geopolitics 0;
the post’s sports 0.03 is stale versus the current table (individual markets still use feeSchedule).
Gamma /events returns 406 for limit>50, so fetch_events pages with offset.

## Volume profile (info only)
    python3 sense.py --vp BTC ALGO                     # 30 days of 1h candles, 50 bins (default)
    python3 sense.py --vp BTC --interval 15m --days 10 --bins 50
Prints, per symbol: last close vs POC and value area (ABOVE/INSIDE/BELOW) and the nearest low-volume node. Data:
Binance public spot klines `{SYM}USDT` from data-api.binance.vision (GET, no key; still-open candle dropped; max 1000
candles per run, so 1h caps near 41 days and 15m near 10). `tt/volprofile.py`: each candle's volume goes to the bin of
its typical price (H+L+C)/3; POC = fullest bin; value area = smallest contiguous bin range around POC with >= 70% of
volume; HVN/LVN = bins >= 1.5x / <= 0.5x mean bin volume. Missing/zero volume or < 100 candles -> UNKNOWN.
Volume is Binance-only (exchange-specific); the profile is a price-acceptance map, not a signal on its own.

## Batch screen (paper only)
    python3 screen_batch.py [--ids a,b] [--oos-from 2023-01-01] [--draws 100]   # -> out/screens/DATE/{summary.md,results.json}
Pools each idea's trades over `coins` (list or ["ALL"] = every local crypto CSV, incl. 62 Coinbase alts), same exits/costs/30-trade guard/null/DSR as
validate, fixed-date IS/OOS, plus OOS daily-return correlation with other ideas and BTC. New entry metrics: hh_N, ll_N, dd_N, rv_N, volr_N, bbwp_N,
dow, dom, month, and cross-asset "SYM:metric" (tt/ideas/extras.py). Kill list: kill_list.md. Idea mining notes: out/idea-mining/DATE/.

## Parameter search and tearsheets (paper only, optional deps: optuna, quantstats)
    python3 optimize.py <id> [--trials 50] [--oos-from 2023-01-01]   # -> out/optuna/<id>-DATE.json, study in out/optuna/optuna.db
    python3 tearsheet.py <id> | --btc-filter 100 [--oos-from ...]    # QuantStats HTML vs BTC hold, OOS window -> out/tearsheets/
optimize.py tunes the numbers already in the rule (lookbacks, thresholds, stop, target, time exit; 0.5x-2x) on IN-SAMPLE bars only
(objective: t-stat of pooled stress-cost IS trades, >= 30 trades), then screens the best set ONCE on full data with
variants = trials in the study + written variants, so DSR gets stricter with every trial. Reruns add to the same sqlite study.
tearsheet.py strips the template's remote favicon link and passes BTC as a series (QuantStats never downloads).

## External daily series for rules (tt/sources/series.py, GET only, no keys, disk cache out/cache/series)
Use in entry rules as "ext:NAME" (lagged one day): funding_BTCUSDT (Binance Vision monthly funding zips, daily mean of 8h rates,
from 2020-01), mvrv / realized_cap / mcap / hashrate (Coin Metrics community, BTC from 2010), stables (DefiLlama, from 2017-11),
btcd (BTC dominance PROXY from 2017-12: BTC / (BTC + 8 coins + stablecoins), no BNB/SOL/TRX), any with ".sma_N".
Host allowlist (series.ALLOWED_HOSTS, tested): data.binance.vision, community-api.coinmetrics.io, stablecoins.llama.fi.
Not usable from this box: Binance fapi (451) and Bybit (403) geo-blocked; OKX funding ~3 months, OI/long-short 180 days;
CoinGecko free = 365 days, global history is PRO-only.

## Pooled mode
`python3 pipeline.py pooled <id> --symbols A,B,C [--oos-from 2023-01-01] [--draws 200]` runs one rule across symbols via screen_batch.screen: per-symbol and pooled IS/OOS stress-cost means, random-entry null, 30-trade minimum, DSR when variants>1. Writes out/validations/<id>.json (mode "pooled") so `risk`/`log` accept a pooled PASS. Test: tests/test_pooled.py.

## Yield scan (paper only)
    python3 yield_scan.py                 # public rates -> yields/latest.md and yields/latest.json
    python3 yield_scan.py --offline       # reuse a stale DefiLlama cache
Read-only GETs, no keys or deposits. DefiLlama `yields.llama.fi/pools` via `tt/sources/yields.py` (cached, allowlisted), FRED T-bill CSVs, Coinbase's public USDC page, and live Hyperliquid/Kraken funding. Flags APY > 15%. See yields/README.md.
