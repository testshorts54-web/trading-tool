# X-sourced prediction-market strategies (math / structure only)

Paper research, 2026-11-14, America/New_York. Public X posts via Grok Bot X read tools, plus a read-only Gamma API check of live BTC/ETH Up/Down markets around 1:25–1:30 PM ET the same day. No accounts, wallets, or orders. Kalshi was not used.

Filter (Kennedy, this turn): keep only edges from pricing math, market structure, fees/rebates, or mechanical inconsistencies. Drop forecasting, news/sentiment, whale/copy trading, and “picks.” Ranked by how mechanical and math-verifiable the edge is, then by whether we can paper-test it with current tools.

Compared against `similar_strategies.md`: maker complement, rebate market-making, negRisk baskets, strike/date ladders, crypto strike vs spot, near-resolution buys, taker complement, cross-venue.

Official fee reminder (from our same-day docs read, not from X): taker fee is `C × rate × p × (1-p)`; makers pay 0. Crypto 0.07, sports 0.05, geopolitics 0. Several popular X posts still use a stale sports rate (0.03) or a different formula `C × 0.25 × (p(1-p))²` (max ~1.56% at 50¢). Do not use those X formulas.

## Ranked list (keep)

### 1. Staggered maker complement, including sports inventory — useful new detail, not a new strategy

Same math as our #1: rest bids so YES + NO ≤ 1 − margin, pay no taker fee, merge or hold to $1 when both legs fill.

New detail from X:
- Accumulate the two legs at different times, when each side gets cheap after a move, rather than only posting both bids at once. [RetroValix, 2026-08-14](https://x.com/RetroValix/status/2088381733313900834) describes this on 15-minute Up/Down (“average Up + Down cost = $0.99038”). That average is the poster’s claim; the quoted account is given as `0xAAAAA` and the post pitches a paid trial, so treat the PnL as unverified.
- When both limits fill, merge the pair back into $1 and stack liquidity rewards / rebates on top. [Solidmag3, 2026-11-01](https://x.com/Solidmag3/status/2117006160687497258)
- Sports books refresh every night, so the same complement scan has more inventory than politics. [Cartel_Degen, 2026-11-06](https://x.com/Cartel_Degen/status/2118552136376336832) (X Article): use VWAP across intended size, not top-of-book; size to the thinner leg; FOK does not make two outcome orders atomic. Public 30-day sports leaderboard snapshot that day: wallet `ghostorder` (`0x55b9e6a1dcca2defb01636ba41e9f76a0883a814`) +$36,060.50 on $5,665,588.47 volume (~0.64% PnL/volume). That footprint is consistent with a high-turnover system, not proof that every fill was complement arb.

Realistic edge: still about 1–3¢ a filled pair, only if both legs fill; sports taker fees (~2.5¢ a pair near 50¢ at rate 0.05) still kill most take-both attempts, which is why the maker path matters.

Main risk: one-leg (legging) exposure, queue position, stale quotes, void/ties. Sports flow can move one book before the other fills.

Vs our list: detail on maker complement. Paper-testable now with `predict_maker_sim.py`; a time-sliced “buy the cheap leg when it appears, wait for the other” mode would be the useful extension.

### 2. Market-making that stacks maker rebates and liquidity rewards — useful new detail, not a new strategy

Same idea as our #2 (rest two-sided quotes, earn spread + a share of taker fees). X adds a second, separate payout stream that our writeup did not spell out.

[AlterEgo_eth, 2026-05-16](https://x.com/AlterEgo_eth/status/2055622140704297302): two programs on the same resting order.
- Liquidity rewards: paid for quotes near mid, fill not required. Score every minute as `size × (1 − |price − midpoint|)²`; share of a per-market daily pool.
- Maker rebates: paid when you are hit, from the taker-fee pool, daily USDC, $1 minimum.

[shtanga0x, 2026-07-29](https://x.com/shtanga0x/status/2082586696403538323) self-reported one Fed-rate market (51 hours, ~500-share average inventory, ~$40k volume, 68× turnover): +$76 trading, +$84 maker rebates, a couple of dollars in LP rewards, about +$160 total. That is a first-party anecdote, not an audited series.

Risk add-on: [AgentBotega, 2026-08-20](https://x.com/AgentBotega/status/2090423173300793783) says some large takers get off-book taker rebates, which can shrink or zero the maker rebate when they hit your quotes. Unverified as a program fact, but rebate income should not be treated as guaranteed.

Realistic edge: rebate + LR can dominate trading PnL on a busy book (our earlier profile read already showed ~$18.1k all-time maker rebate). LR size varies by market pool and competition; many X “I got $1–8 today” posts are tiny.

Main risk: inventory and adverse selection (worse after the Feb 18, 2026 removal of the 500ms taker delay — makers can no longer cancel in that window), fee-holiday markets, rebate/LR rule changes, hidden taker-rebate leakage.

Vs our list: detail on rebate MM. Paper-testable next by attributing a conservative rebate on sim fills (already planned) and, if a public rewards endpoint exists, an LR score from our quote distance to mid. Do not count either as locked arb profit.

### 3. TWAP settlement vs displayed spot — new

On 2026-08-07, Polymarket changed crypto Up/Down resolution from a single last price to a Chainlink TWAP. August posts said 5-minute markets use a 30-second TWAP and 15-minute / 4-hour markets use a 60-second TWAP, and that both the price-to-beat and the settlement print come from that feed. ([13_niakris, 2026-08-05](https://x.com/13_niakris/status/2084922431764939067), [kinexbtdev, 2026-08-06](https://x.com/kinexbtdev/status/2085432591168225339), [HaileSelasie13, 2026-08-07](https://x.com/HaileSelasie13/status/2085653402009186714))

The mechanical edge: the book and the UI “current price” can still be reacting to last tick, while the contract pays on the TWAP path versus price-to-beat. If you compute the live TWAP and it already disagrees with spot, the fair binary price is not the last-tick implied probability.

Live check, 1:25 PM ET today: Gamma `resolutionSource` on current 5-minute and 15-minute BTC markets is `https://data.chain.link/streams/btc-usd-twap-60s-streams` (ETH analogous). That 60s URL on 5-minute markets may mean the August 30s/60s split was later unified, or the path name is generic. Verify the actual window against the live feed before coding a sim. [kinexbtdev](https://x.com/kinexbtdev/status/2085432591168225339) also noted the 30-second window “is not a pure trailing T-29 → T average (a small offset exists).”

This is the formula version of our near-resolution idea (#6) and is closer to settlement mechanics than to a “looks settled” judgment. It is distinct from our longer-dated lognormal strike-vs-spot flag (#5).

Realistic edge: maybe 1–5¢ near expiry when TWAP and last tick disagree and the book has not caught up; often none if books adapted after August. Taker fees on crypto still eat a 3¢ gap near 50¢; prefer maker or only take when net edge after the official fee formula is clearly positive, usually near the extremes.

Main risk: wrong TWAP window/offset, books already efficient, last-second liquidity holes, crypto taker fees, dispute/void.

Vs our list: new (settlement-oracle mechanics). Paper-testable with public Chainlink/RTDS (or recorded TWAP) plus CLOB books and official resolution; a book-based last-minutes path is already noted as a next step in `similar_strategies.md`.

### 4. Hidden “Other” via NegRisk Convert — new execution path

[NightShifter132, 2026-05-30](https://x.com/NightShifter132/status/2060721280106582384) documents an official CTF operation, not a trade: in a `negRisk: true` event, Convert turns NO shares of one outcome into YES shares of every remaining outcome, including an “Other” token that may not appear in the UI. Sell the unwanted YES legs and keep Other (or the reverse), instead of tying up capital as NO on every listed name.

The edge is still complete-set / implied-Other math: only trade if the synthetic Other (or the residual basket) is cheaper than the same payoff bought the obvious way, after fees and depth. [OrdiaxSocial, 2026-10-22](https://x.com/OrdiaxSocial/status/2103409447347327123) notes that converted/consumed NO can show up as a fake “whale” at a burn address in raw API data; the UI correctly hides it.

Realistic edge: situational, usually none; the same incomplete-set / placeholder problem we already see in `predict_scan.py` still applies.

Main risk: selling residual YES (legging), convert costs, rule text vs “Other” definition, augmented events that are not a true complete set.

Vs our list: new detail on negRisk baskets (#3). Paper-testable if Gamma/CLOB exposes the hidden token and its book.

### 5. Same-event duplicate / related-market bounds (Polymarket only) — new

When two Polymarket listings are the same payoff (or one logically dominates the other) and prices disagree, the cheaper equivalent or the broken bound can be traded like a ladder arb.

[CSP_Trading, 2025-10-07](https://x.com/CSP_Trading/status/1975408334103548414): two Nobel Peace Prize markets, one neg-risk and one not, described as “free yield to close the gap.” That is a same-platform related-market spread, not a forecast. Posts that pair “near-duplicate” wordings with embeddings ([m7e7m7e7, 2026-02-27](https://x.com/m7e7m7e7/status/2028247381893099525)) are the same idea, but only if resolution rules actually match.

Realistic edge: rare cents, and only after confirming identical (or nested) resolution text. [Predictive_Labs, 2026-06-17](https://x.com/Predictive_Labs/status/2067070024624578818) shows the failure mode on cross-venue wording; the same risk exists on-platform if the two markets are not truly the same event.

Main risk: rule mismatch, different end dates or “Other” clauses, legging, fees.

Vs our list: new, in the same family as strike/date ladders (#4). Paper-testable by pairing Polymarket events and checking payoff identity, then running the existing monotonicity / dutch-book checks. Cross-venue (Kalshi and others) stays out: Kalshi’s terms still block that use, and wording/oracle differences can make an apparent lock not a lock.

### 6. Taker complement remains usually dead; measure net edge on asks and official fees — useful confirmation

Not a new strategy. X is consistent with our #7 and with Punisher’s own fee guide.

[Cartel_Degen, 2026-11-06](https://x.com/Cartel_Degen/status/2118552136376336832) works a sports “97¢ trap”: YES 48¢ + NO 49¢ looks like 3¢, but sports taker fees at rate 0.05 take about 2.5¢ near 50¢, leaving a fraction of a cent before slippage and unmatched legs. That sports rate matches our official table, not the 0.03 in Punisher’s October guide.

[w1nklerr, 2026-02-25](https://x.com/w1nklerr/status/2026768846120792336) and [cryptovcdegen, 2026-02-23](https://x.com/cryptovcdegen/status/2025900197016908081) argue the Feb 18, 2026 removal of the 500ms taker delay, plus crypto taker fees, killed most take-now latency and complement bots. Directionally useful; their printed fee formula is not the official one (see header).

Realistic edge: usually none as a taker; maker complement is the surviving version.

Vs our list: confirmation. Already testable with `predict_maker_sim.py --taker-once` and `predict_scan.py`.

## Checked and rejected as a lock (still math-themed)

### 5-minute / 15-minute “overlap arb” — claim does not hold

[kinexbtdev, 2026-02-14](https://x.com/kinexbtdev/status/2022793626879943026) describes buying 15m Up + 5m Down (or the reverse) in the last five minutes of a 15-minute window, on the claim that both markets share the same price-to-beat, so the pair is a mechanical complement when asks sum under ~0.99.

Live Gamma check today, America/New_York:

| Market | Window (ET) | priceToBeat |
|---|---|---|
| 15m `btc-updown-15m-1794679200` | 1:00–1:15 PM | $65,827.10 |
| Overlapping 5m `btc-updown-5m-1794679800` | 1:10–1:15 PM | $65,887.77 |

The strikes differ. A 15m Up + 5m Down pair is therefore not a locked complete set. A 15m and a 5m that start together may share an opening TWAP, but they expire at different times, which is also not a lock. Each new 5-minute window’s price-to-beat in this sample equals the prior 5-minute window’s `finalPrice`, which is consistent with a rolling TWAP open, not with inheriting the 15-minute strike.

Do not paper-test this as guaranteed arb unless a later, verified identity of payoffs appears.

### CEX / oracle-lead latency (taker) — mechanical, mostly dead, hard with our tools

Binance (or Pyth) moves, the Polymarket book lags, buy the indicated side. Open-source examples are widely listed ([AlterEgo_eth, 2026-05-06](https://x.com/AlterEgo_eth/status/2052003002857431211): `JLowo/gengar_polymarket_bot`). [morpphhhaw, 2026-04-30](https://x.com/morpphhhaw/status/2049777341514019035) applies the same idea to gold/silver/oil/stocks after Pyth became the data provider, claiming ~200ms Pyth vs a 1-second Polymarket sample.

After the 500ms taker-delay removal and crypto taker fees, multiple posts call the taker version dead; remaining edge would be a low-latency maker quote, which we cannot honestly simulate without WebSocket and queue data. TWAP settlement (#3) further weakens last-tick sniping. Not a priority paper test.

## Dropped (not “less prediction, more math”)

These showed up often in the same X search and were excluded from the ranked list:

- Cheap-ticket / underdog / “lottery” buys on 5m/15m crypto (1–30¢), Markov or mystery “models,” lean-and-hedge with conviction: [ridark_eth](https://x.com/ridark_eth/status/2056044153998385382), [me_cool_off](https://x.com/me_cool_off/status/2061170165367050618), [BimbaCrypto](https://x.com/BimbaCrypto/status/2108786200907510053) / [gabigol writeup](https://x.com/BimbaCrypto/status/2110481238095986795), [merlin_future](https://x.com/merlin_future/status/2049860496141230483)
- Mean reversion, panic-wick fades, news-overreaction fades, momentum / VWAP / MACD bots
- Copy trading, “smart money,” and whale following
- “Nothing ever happens” (buy NO on everything) and other base-rate directional bets
- Weather models vs NOAA/GFS (forecasting; also mostly Kalshi)
- Combinatorial V2 markets (mentioned in October protocol-upgrade posts; too early to treat as a testable structure edge)

## Scams, shills, or unverifiable PnL

- Repeated Telegram “PolyCop” copy-trade spam from clone accounts (e.g. [VinceCarte61867](https://x.com/VinceCarte61867/status/2044615475116888485) and near-identical posts).
- [Shelpid_WI3M, 2026-02-17](https://x.com/Shelpid_WI3M/status/2023794118887944431): “$906,000 monthly PnL” Clawdbot / copy-trade thread, engagement-farm tone, not treated as evidence.
- [slash1sol](https://x.com/slash1sol/status/2044802619672072656) PredictEngineAI “non-developer made $20k”; [adiix_official](https://x.com/adiix_official/status/2026634072924053608) explicitly marked promotional.
- “AI built a bot that prints $X/day” posts ([Dan1ro0](https://x.com/Dan1ro0/status/2107193915053133913), [bored2boar](https://x.com/bored2boar/status/2083642393320919281), similar). [bankrbot, 2026-05-12](https://x.com/bankrbot/status/2054154607056814103) already flagged the “comment GUIDE for access” pattern as likely engagement farming with no verified wallet.
- [RetroValix](https://x.com/RetroValix/status/2088381733313900834) mechanism (staggered complement) is usable; the +$278,867 claim and `0xAAAAA` placeholder are not.
- [0x_Punisher](https://x.com/0x_Punisher/status/2121247151040684079) still points at Telegram and a GitHub; we already checked the linked profile’s public stats (~$40k all-time trade PnL, not a verified $35k/month machine). The fee/spread guide itself remains useful.
- Repo-roundup posts ([eamoncress](https://x.com/eamoncress/status/2097033654249873815), [AlterEgo_eth](https://x.com/AlterEgo_eth/status/2052003002857431211), [ridark_eth](https://x.com/ridark_eth/status/2092635656866459701)) are handy catalogs; star counts and “replaces $3k/yr SaaS” claims are marketing. Paper-trade any fork first and never paste keys into a stranger’s template.
- Paid “arb of the day” tools and cross-venue scanners that require Kalshi use are out of scope.

## Search notes

Queries used `search_posts_all` (relevancy, mostly 2025-06 or 2026-01 onward, `-is:retweet lang:en`) plus `get_posts_by_id(s)` for the Punisher source post (`2121247151040684079`, 2026-11-13 9:21 AM ET) and truncated threads. Themes: polymarket arbitrage/maker/rebates, negRisk/complete set, copy trading (then dropped), 5m/15m bots, Kalshi spreads, overlap / price-to-beat / liquidity rewards, news/fair-value (then mostly dropped). Full archive was not exhaustively paged; this is a relevancy-ranked sample, not a complete census.
