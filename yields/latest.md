# Stablecoin and DeFi yields (paper scan)

Data as of **2026-11-14 3:22 PM ET**. Public sources only. Not an offer, not advice, no deposits or sign-ups were made.

## Benchmarks

- 1-month T-bill (FRED DGS1MO, constant maturity): **4.12%** as of 2026-11-12 (FRED public CSV [DGS1MO]). US-accessible, low risk — the cash benchmark.
- 3-month T-bill (FRED DGS3MO, constant maturity): **4.32%** as of 2026-11-12 (FRED public CSV [DGS3MO]). US-accessible, low risk — the cash benchmark.

- Coinbase USDC rewards: see the CEX row below (public page https://www.coinbase.com/usdc).
- Historical paper funding carry (BTC/ETH always-on, Coinbase-cost out-of-sample, carry-futures-sims, collected 2026-11-11): **~5–6% net on notional**, about **4.6–4.8% on posted cash** after overnight margin. Live funding (below) is a different regime today.

## Live rows

| Category | Name | Chain | APY (base + rewards) | 30d mean | TVL | Risk | US access | Why |
|---|---|---|---:|---:|---:|---|---|---|
| CEX earn (US) | Coinbase USDC rewards (Coinbase One) | Coinbase custody (off-chain) | 3.75% (3.75%) | n/a | n/a | low-med | yes, eligible US Coinbase One members (rate can vary by account) | Custodial, uninsured (not FDIC/SIPC) Coinbase counterparty rewards, not a bank account. One membership ($4.99/mo and up) is required in the US, so net APY shrinks on small balances and trails T-bills at any size. |
| stablecoin lending | aave-v3 USDC | Ethereum | 3.80% (3.80%) | 4.28% | $173.7M | med | protocol open; official UI may geo-restrict US persons | Blue-chip lending market; smart-contract and utilization risk, rate moves with demand. |
| stablecoin lending | aave-v3 USDT | Ethereum | 3.41% (3.41%) | 4.01% | $295.8M | med | protocol open; official UI may geo-restrict US persons | Same Aave v3 market as USDC; plus USDT issuer/custody concentration. |
| stablecoin lending | aave-v3 USDC | Base | 5.11% (5.11%) | 6.19% | $16.3M | med | protocol open; official UI may geo-restrict US persons | Smaller TVL than Ethereum; headline APY is utilization-driven and can fall quickly. |
| stablecoin lending | compound-v3 USDC | Ethereum | 3.22% (3.22%) | 4.32% | $37.4M | med | protocol open; official UI may geo-restrict US persons | Established lending market; smart-contract and utilization risk. |
| stablecoin lending | compound-v3 USDT | Ethereum | 3.23% (3.23%) | 5.24% | $15.7M | med | protocol open; official UI may geo-restrict US persons | Same Compound III market; plus USDT issuer risk. |
| stablecoin lending | morpho-blue STEAKUSDC | Ethereum | 4.50% (4.50%) | 4.96% | $132.2M | med | protocol open; official UI may geo-restrict US persons | Steakhouse-curated Morpho vault; curator + Morpho + underlying market risk. |
| stablecoin lending | morpho-blue STEAKUSDC | Base | 4.50% (4.50%) | 5.21% | $130.1M | med | protocol open; official UI may geo-restrict US persons | Same Steakhouse USDC vault on Base; pick the larger-TVL listing if two appear. |
| stablecoin lending | morpho-blue GTUSDCP | Base | 4.50% (4.50%) | 5.21% | $398.5M | med | protocol open; official UI may geo-restrict US persons | Gauntlet-curated Morpho USDC vault; curator and smart-contract risk. |
| stablecoin lending | morpho-blue SPARKUSDC | Base | 4.04% (4.04%) | 4.67% | $379.9M | med | protocol open; official UI may geo-restrict US persons | Spark-curated Morpho USDC vault; Sky/Spark + Morpho stack. |
| stablecoin lending | sparklend DAI | Ethereum | 3.58% (3.58%) | 3.08% | $52.0M | med | protocol open; official UI may geo-restrict US persons | SparkLend DAI supply; Sky-related smart-contract risk. |
| Sky savings | sky-lending SUSDS | Ethereum | 3.80% (3.80%) | 3.80% | $3.74B | low-med | protocol open; official UI may geo-restrict US persons | Governance-set Sky Savings Rate paid from protocol surplus; USDS/Sky contract and depeg risk. |
| Sky savings | spark-savings USDT | Ethereum | 4.25% (4.25%) | 3.89% | $369.0M | low-med | protocol open; official UI may geo-restrict US persons | Spark savings on USDT, routed into the Sky rate stack; plus USDT issuer risk. |
| Sky savings | spark-savings USDC | Ethereum | 3.80% (3.80%) | 3.80% | $228.9M | low-med | protocol open; official UI may geo-restrict US persons | Spark savings on USDC into the Sky rate stack. |
| Sky savings | sky-lending SDAI | Ethereum | 1.25% (1.25%) | 1.25% | $184.0M | low-med | protocol open; official UI may geo-restrict US persons | Legacy DAI savings; rate has lagged sUSDS since the Sky migration. |
| Sky savings | sky-lending STUSDS (Expert Mode) | Ethereum | 13.05% (13.05%) | 7.11% | $161.6M | high | protocol open; official UI may geo-restrict US persons | Sky 'Expert Mode' stUSDS; higher rate reflects credit/loss exposure, not a savings-rate equivalent. |
| yield-bearing stable | ethena-usde SUSDE (7 days unstaking) | Ethereum | 5.24% (5.24%) | 5.04% | $1.20B | high | no — Ethena ToS and staking contract restrict US persons | sUSDe yield comes from delta-neutral funding; exchange, custody, depeg and funding-regime risk. 7-day unstake. |
| tokenized T-bills | ondo-yield-assets USDY (US Dollar Yield) | Ethereum | 3.75% (3.75%) | 3.73% | $1.29B | low-med | no — Regulation S, non-US persons only | Short-term Treasuries + deposits via Ondo; issuer/KYC and transfer-restriction risk. Tracks T-bills minus fees. |
| tokenized T-bills | ondo-yield-assets OUSG (Short-term US Government Securities) | Ethereum | 3.70% (3.70%) | 3.72% | $127.1M | low-med | US accredited investors who are also qualified purchasers, via Ondo KYC | Tokenized short-term Treasuries (often via BUIDL); private-fund eligibility and transfer locks. |
| tokenized T-bills | blackrock-buidl BUIDL (Institutional) | Ethereum | 3.87% (3.87%) | 3.47% | $239.1M | low | US qualified purchasers only (Securitize; typical $5M minimum) | BlackRock USD Institutional Digital Liquidity Fund; underlying T-bill/cash risk is low, access is institutional. |
| tokenized T-bills | invesco-ustb USTB | Ethereum | 3.51% (3.51%) | 3.60% | $448.5M | low-med | typically qualified / KYC institutional; confirm on the issuer page | Tokenized T-bill fund; tracks bills minus fees, with issuer and transfer-restriction risk. |
| yield-bearing stable | frax SFRXUSD | Ethereum | 5.30% (5.30%) | 5.09% | $39.4M | med | protocol open; official UI may geo-restrict US persons | Frax sUSDe-style yield on frxUSD; smart-contract and Frax/strategy risk. |
| yield-bearing stable | frax SFRAX | Ethereum | 1.25% (1.25%) | 0.62% | $65.2M | med | protocol open; official UI may geo-restrict US persons | Legacy sFRAX; rate has been low versus sUSDS and sfrxUSD. |
| private credit | maple USDC (Syrup USDC) | Ethereum | 5.22% (5.22%) | 5.12% | $2.23B | med-high | KYC; often limited to accredited or institutional users — confirm Maple terms | Maple syrupUSDC is underwritten private credit, not risk-free lending; borrower default and lockup risk. |
| Pendle fixed | pendle-v2 SUSDE (For buying PT-sUSDe-26NOV2026) | Ethereum | 5.32% (5.32%) | 4.94% | $5.0M | high | protocol open; official UI may geo-restrict US persons; underlying sUSDe is US-restricted | Fixed PT until maturity, but you still hold Ethena/sUSDe credit, depeg and liquidity risk. |
| Pendle fixed | pendle-v2 SIUSD (For buying PT-siUSD-07JAN2027) | Ethereum | 9.78% (9.78%) | 9.64% | $17.9M | high | protocol open; official UI may geo-restrict US persons | Fixed PT on a smaller, less-known USD product; credit and liquidity risk, modest TVL. |
| ETH staking | lido STETH | Ethereum | 2.26% (2.26%) | 2.68% | $17.99B | med | protocol open; official UI may geo-restrict US persons | ETH price risk plus Lido/validator and stETH-discount risk; this is not a dollar yield. |
| ETH staking | rocket-pool RETH | Ethereum | 1.80% (1.80%) | 1.98% | $892.0M | med | protocol open; official UI may geo-restrict US persons | ETH price risk plus Rocket Pool/node-operator risk. |
| ETH staking | ether.fi-stake WEETH | Ethereum | 2.53% (2.53%) | 2.54% | $4.07B | med-high | protocol open; official UI may geo-restrict US persons | Liquid restaking on top of ETH staking; extra protocol and slashing-stack risk. |
| ETH staking | coinbase-wrapped-staked-eth CBETH | Ethereum | 2.45% (2.45%) | 2.53% | $369.2M | med | yes for eligible Coinbase customers (ETH price risk remains) | Coinbase-wrapped staked ETH; custody plus ETH price and validator risk. |

## Live funding (delta-neutral carry, snapshot)

Positive APR means a long-spot / short-perp book would be *paid* funding; negative means it would *pay*. These are one-hour annualized snapshots, not a forecast.

| Venue | Coin | Funding APR | As of |
|---|---|---:|---|
| Hyperliquid | BTC | 2.75% | 2026-11-14T20:22+00:00 |
| Hyperliquid | ETH | -6.66% | 2026-11-14T20:22+00:00 |
| Hyperliquid | SOL | -16.03% | 2026-11-14T20:22+00:00 |
| Kraken Futures | BTC | 5.60% | 2026-11-14T20:00:00Z |
| Kraken Futures | ETH | -5.08% | 2026-11-14T20:00:00Z |

## Top options, ranked by risk-adjusted dollar yield

ETH staking, US-blocked names, >15% APYs, high-risk rows, and pools under $50M TVL are omitted. Cash benchmark is the latest 1-month T-bill, 4.12%. Qualified-purchaser and accredited-only products (BUIDL, OUSG) are footnoted, not ranked as retail options. US Treasuries are state-tax exempt; a 4% T-bill can beat a 4.5% DeFi yield after state tax. DeFi and Sky rates are floating.

1. **US 1-month T-bill 4.12%** — low risk, fully US-accessible cash benchmark (official 4-week / 13-week coupon-equivalent on 2026-11-13: 4.02% / 4.23%).
2. **spark-savings USDT 4.25%** (low-med risk) — 4.25% on $369.0M, Ethereum. Spark savings on USDT, routed into the Sky rate stack; plus USDT issuer risk. US: protocol open; official UI may geo-restrict US persons.
3. **sky-lending SUSDS 3.80%** (low-med risk) — 3.80% on $3.74B, Ethereum. Governance-set Sky Savings Rate paid from protocol surplus; USDS/Sky contract and depeg risk. US: protocol open; official UI may geo-restrict US persons.
4. **morpho-blue GTUSDCP 4.50%** (med risk) — 4.50% on $398.5M, Base. Gauntlet-curated Morpho USDC vault; curator and smart-contract risk. US: protocol open; official UI may geo-restrict US persons.
5. **Coinbase USDC rewards (Coinbase One) 3.75%** (low-med risk) — 3.75% on n/a, Coinbase custody (off-chain). Custodial, uninsured (not FDIC/SIPC) Coinbase counterparty rewards, not a bank account. One membership ($4.99/mo and up) is required in the US, so net APY shrinks on small balances and trails T-bills at any size. US: yes, eligible US Coinbase One members (rate can vary by account).
6. **aave-v3 USDC 3.80%** (med risk) — 3.80% on $173.7M, Ethereum. Blue-chip lending market; smart-contract and utilization risk, rate moves with demand. US: protocol open; official UI may geo-restrict US persons.
7. **sparklend DAI 3.58%** (med risk) — 3.58% on $52.0M, Ethereum. SparkLend DAI supply; Sky-related smart-contract risk. US: protocol open; official UI may geo-restrict US persons.

Institutional / qualified-purchaser only (not ranked as retail):

- **blackrock-buidl BUIDL (Institutional) 3.87%** (low risk) — 3.87% on $239.1M, Ethereum. BlackRock USD Institutional Digital Liquidity Fund; underlying T-bill/cash risk is low, access is institutional. US: US qualified purchasers only (Securitize; typical $5M minimum).
- **ondo-yield-assets OUSG (Short-term US Government Securities) 3.70%** (low-med risk) — 3.70% on $127.1M, Ethereum. Tokenized short-term Treasuries (often via BUIDL); private-fund eligibility and transfer locks. US: US accredited investors who are also qualified purchasers, via Ondo KYC.
- **maple USDC (Syrup USDC) 5.22%** (med-high risk) — 5.22% on $2.23B, Ethereum. Maple syrupUSDC is underwritten private credit, not risk-free lending; borrower default and lockup risk. US: KYC; often limited to accredited or institutional users — confirm Maple terms.
- **invesco-ustb USTB 3.51%** (low-med risk) — 3.51% on $448.5M, Ethereum. Tokenized T-bill fund; tracks bills minus fees, with issuer and transfer-restriction risk. US: typically qualified / KYC institutional; confirm on the issuer page.

## Versus funding carry and the prediction-market test

Funding carry remains the best *tested* crypto yield in our paper work (~5–6% net on notional historically), but today's live funding is mixed: Hyperliquid BTC is 2.75% and ETH is -6.66% annualized, so an always-on ETH or SOL book would currently pay funding, not earn it. Plain dollar yields (T-bills ~4%, Coinbase USDC ~3.75% only if Coinbase One is already paid for, Sky sUSDS 3.80%, large Morpho/Aave USDC around 3.8–4.5%) are the more reliable cash park today; T-bills also have a state-tax edge. Do not size into Ethena, stUSDS Expert, or high Pendle PTs for a 'safer than carry' sleeve. The prediction-market maker test is still negative on paper — it is not a substitute for either sleeve.

## Notes

- Source: [https://yields.llama.fi/pools](https://yields.llama.fi/pools), plus FRED public CSVs, https://www.coinbase.com/usdc, Hyperliquid public info, and Kraken Futures public funding.
- FRED DGS1MO/DGS3MO are constant-maturity yields and can lag the latest business day. Official Treasury coupon-equivalent bill rates (a closer cash-APY comparison) are at home.treasury.gov daily Treasury bill rates; they were 4.02% (4-week) and 4.23% (13-week) on 2026-11-13, the last session before this Saturday scan.
- The shortlist drops high-risk rows, US-blocked names, APY > 15%, ETH staking, and pools under $50M TVL (thin utilization spikes). Reward-token APY is halved in the score.
- APY > 15% is flagged as likely incentive- or risk-driven. Reward-token APY can go to zero when emissions stop.
- DefiLlama TVL and APY can lag or double-count across chains and vault wrappers. Official protocol pages win if they disagree.
- US-access labels are a research summary of public terms, not legal advice. Frontends change geo-rules without notice.
- This scan does not hold custody, sign up, deposit, or place quotes.

