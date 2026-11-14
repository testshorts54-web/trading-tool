# Similar strategies (paper research, 2026-11-14)

Sources: Polymarket fee and rebate docs (docs.polymarket.com/trading/fees and /programs/maker-rebates, read this day); Data API v2 public profile reads; this repo’s predict_scan, arb-carry-study (2026-11-10), and straddle-cut-study; public writeups cited below. No orders. Kalshi was not used.

Official taker fee is C × rate × p × (1-p), makers pay 0. Category rates: crypto 0.07; sports / economics / culture / weather / other / combos 0.05; politics / finance / tech / mentions 0.04; geopolitics 0. The post’s sports 0.03 is stale versus the current table (some markets may still publish 0.03 on feeSchedule). Rebates are 15–25% of the fee curve for makers, not subtracted in our paper P&L.

## Ranked list

1. **Maker complement (YES+NO bids sum to ≤ 1 − margin)** — this paper sim. Edge is the margin (default 2c/share) plus optional rebates, with no taker fee. Realistic edge: 1–3c a filled pair on liquid books, only if *both* legs fill. Risks: one-leg (legging) exposure, queue position (our at-or-through fill model is optimistic), stale quotes, void/ties. Paper-testable now: `predict_maker_sim.py`.

2. **Market-making for rebates** — rest bids/asks, earn a share of taker fees when you are taken (crypto 20%, sports 15%, most others 25%; geopolitics none). Edge is rebate income minus inventory/legging losses and adverse selection. The checked public profile shows ~$18.1k all-time maker_rebate versus ~$37.9k realized market PnL, so rebates can be a large share of a high-volume book’s economics. Risks: inventory, fee-holiday markets pay 0, rebate rules can change, needs real size and many fills. Paper-testable next: attribute a conservative rebate estimate on sim fills (do not count it as locked arb profit).

3. **Multi-outcome (negRisk) YES basket, sum of asks < $1** — already in `predict_scan.py`. After fees and a 1% / depth filter, today’s scan flagged 0 of 4 raw candidates; a 2026-11-10 scan also flagged 0; an independent Oct 2026 scan (polytrading.app/research/full-set-arbitrage) found almost all large “gaps” were incomplete/augmented events. Realistic edge: usually none after fees; rare complete-set leftovers are cents on capital locked until resolution. Risks: incomplete sets, Other/placeholder outcomes, oracle/void. Paper-testable now: `predict_scan.py --once`.

4. **Strike-ladder / nested-date logical arbs** — buy the cheaper-but-more-likely contract and sell the tighter one when monotonicity breaks (higher strike must not cost more than a lower strike; an earlier deadline must not price above a later one on the same event). After two taker fees a small violation is often just a cheap option, not a locked profit (see libertasveritasprosperitas.com/research/no-arbitrage-bounds-event-contracts). arb-carry-study checked 206 adjacent strike pairs on 2026-11-10 and found no executable locks. Risks: different resolution sources/rounding, legging, fees. Paper-testable next: reuse arb-carry-study’s monotonicity check on a live poll, same as this sim.

5. **Crypto strike vs spot** — already in `predict_scan.py` (driftless lognormal, 100% vol, flags only when model p ≥ 0.99 and ≥ 2c after fee). Today: 91 evaluated, 0 flagged. Realistic edge: rare, model-dependent, not a locked arb. Risks: basis vs the market’s resolution source, vol assumption, fees at short dates still bite. Paper-testable now: the same scanner.

6. **Endgame / near-resolution “safe” buys** — buy a 0.97–0.99 share when the outcome looks settled. At p=0.97 crypto fee is only ~0.2c, so a truly certain 97c share still has ~2.8c gross; sports/politics less fee. Realistic edge: small, and only if the “certain” outcome actually pays. Risks: late reversals, void, UMA disputes, last-look spreads. Paper-testable next: watch books in the last minutes of 5m/15m up/down and mark to official resolution (straddle-cut-study already has a 60s mid path; a book-based version would be better).

7. **Taker complement (buy both asks when sum + fees < $1)** — the post’s taker path. On this run’s 20 liquid binaries, after-fee costs started at ~1.028 and none flagged (need ≥ 1% gap and depth). Crypto at 50/50 costs 1.75c/share per leg, so a 3c raw gap is often a loss. Realistic edge: usually none. Risks: you pay the ask and the fee; depth disappears. Paper-testable now: `predict_maker_sim.py --taker-once` and the dutch-book leg of `predict_scan.py`.

8. **Cross-venue (Polymarket vs Kalshi or others)** — same event, different prices. Not tested: Kalshi’s terms restrict this use, so the gap stays UNKNOWN. Paper-testable with current tools: no.

## $40k profile claim

Address `0xbd0f6c867e2a852807ef8fcdd76d696053da48fd`, public Data API v2 reads at about 11:59 AM–12:00 PM America/New_York on 2026-11-14. Use `time_period=all` on `/v2/leaderboard` (`window=all` returned a different, much smaller number and should not be used).

- All-time realized market PnL / leaderboard PnL: **$37,863.76**
- `trade_pnl`: **$40,127.45** (closest to a rounded “$40k”)
- `economic_pnl`: **$56,173.36** (adds rebate/other income)
- Maker rebate: **$18,099.78**; taker rebate $71.66; fees_paid (net) **−$2,262.97**
- This month (`time_period=month`): **−$1,546.59**; this week: **+$3,788.58**
- Portfolio value: about **$130**; volume about **$3.06M USDC** / 216k trade rows; account created 2025-11-08
- A short recent-trade sample showed buys of both outcomes in the same market at prices that summed under $1 (e.g. 0.43 + 0.51), which is consistent with complement trading, but public data cannot attribute the full PnL to that strategy alone.

The $40k figure is in the same range as official all-time `trade_pnl` / realized market PnL. It is not independently audited, and recent monthly PnL is negative.
