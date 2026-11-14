# Yield scan (paper only)

Read-only public rates for stablecoin lending, yield-bearing dollars, tokenized T-bills, Pendle fixed yields, ETH staking, CEX USDC rewards, and a live funding-carry snapshot. No wallets, keys, deposits, or sign-ups.

```text
cd /workspace/trading-tool
python3 -m unittest tests/test_yield_scan.py
python3 yield_scan.py              # refresh (DefiLlama cache 6h) -> yields/latest.md and yields/latest.json
python3 yield_scan.py --offline    # reuse a stale DefiLlama cache
```

## Sources

- DefiLlama yields API `https://yields.llama.fi/pools`, cached under `out/cache/yields` by `tt/sources/yields.py` (same allowlisted HTTPS + disk-cache pattern as `tt/sources/series.py`).
- FRED public CSVs for 1- and 3-month Treasury constant-maturity yields (`DGS1MO`, `DGS3MO`).
- Coinbase public USDC page for the advertised Coinbase One rewards rate.
- Hyperliquid public `metaAndAssetCtxs` and Kraken Futures public funding, via `tt/sources/perps.py`.
- Historical funding-carry figures are cited from `carry-futures-sims/RESULTS.md`, not re-estimated here.

APY above 15% is flagged as likely incentive- or risk-driven. US-access notes are a research summary of public terms, not legal advice. Official protocol pages win if they disagree with DefiLlama.
