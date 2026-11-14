# Crypto kill list (paper research; do not re-test without new data or a new mechanism)
Consolidated 2026-11-01 from crypto-tracker/strategies-2026-10-27.md, swing-scan-2026-10-27.md, crypto-strategies/alts/report.md,
known results, and out/screens/2026-11-01 (screen_batch.py, stress 90 bp/side, OOS from 2023-01-01).
## Earlier
- 90-day momentum rotation (top-N monthly); slow SMA200 basket filters; stablecoin-growth filter and Fear & Greed filter (failed after 2023)
- 20-day breakout / pullback / range rules on alts at ~2% RT cost (R1/R2/R3); 20/10 breakout without regime filter (= Turtle S1)
- RS top-5 28d rotation without regime; S5 alt-season / BTC-dominance rotation; S3b MR with BTC>SMA200; RSI(2) mean reversion at retail cost (fragile)
## Added 2026-11-01 (screen FAIL, OOS mean per trade <= 0 at stress cost)
g01 1-week TSMOM majors; g02 close>SMA20 BTC/ETH; g04 close>SMA50 majors4; g05 one-day abnormal-return momentum; g06/g21 buy -10% day (alts, with or
without BTC regime); g07 BB-width squeeze; g08 20d high + expanding ATR (BTC); g09 10d low inside SMA200 uptrend; g10 Monday effect; g11 Sunday dip;
g12 turn-of-month; g14 14d RS vs BTC (alts, regime on); g17 bull-market support band; g19 15-25% pullback in golden cross; g20 SMA65 + regime.
Watch, not killed: g16 ETH-vs-BTC 21d RS (OOS +1.1%/trade but null p 0.16). Insufficient: g13 Q4 seasonality, g18 volume washout.
## Added 2026-11-09 batch2 (screen FAIL, OOS stress 90 bp/side from 2023-01-01; paper-only)
rsi2-spy SPY RSI(2)<10 + SMA200; n02-btcd-alt-rotation alts when btcd<sma50 + BTC>SMA200 (pooled 5);
n03-realized-price-btc MVRV>1.03; t06-xlf-financials-rotation XLF>SMA50 & beats XLK 20d;
t08-gdx-metals-miners GDX>SMA50 & beats SPY 20d.
INSUFFICIENT (not killed; need more trades or data): n01-funding-neg-btc (0 trades), crown-a-rsp-breadth,
t03-uup-dollar-europe-stress, t04-xlu-event-defensive, t12-spy-vix-spike-fade, t13-smh-capitulation-snapback,
t14-kre-front-end-rates.

## Added 2026-11-09 batch2b-crypto (CRYPTO-only screen FAIL, stress 90 bp/side, OOS from 2023-01-01)
c03-funding-healthy-btc, c04-lowvol-trend-btc, c05-shallow-dip-btceth, c06-realizedcap-rising-btc.
INSUFFICIENT (not killed): c02-mvrv-cheap-btc.
PASS: c01-hashrate-trend-btc.

## Added 2026-11-09 batch-alts (ALTCOIN-only, no BTC/ETH targets; stress 90bp; OOS 2023-01-01 reused screening)
FAIL: a01-alts-hashrate-gate, a03-alts-vs-eth-rs, a04-alts-mid-dip, a05-alts-lowvol-trend.
INSUFFICIENT: a02-alts-rsi14-btc-regime.
PASS: a06-alts-vol-thrust.
Post sources (GMGN/Solana-MCP/TradingAgents/agent-kit/opentrade) not used for history: key/auth or execution-only; Coinbase alts CSV labeled substitute.
