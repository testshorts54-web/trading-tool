#!/usr/bin/env python3
"""Paper-only public yield scan. Read-only GETs, no keys, custody, deposits, or sign-ups.

Usage:
  python3 yield_scan.py              # fetch (cached), write yields/latest.md and yields/latest.json
  python3 yield_scan.py --offline    # reuse the on-disk DefiLlama cache even if stale
"""
from __future__ import annotations
import argparse, datetime as dt, json, re, sys
from pathlib import Path
from zoneinfo import ZoneInfo

from tt.http import get
from tt.sources import fred, perps, yields as llama

ROOT = Path(__file__).resolve().parent
OUT_DIR = ROOT / "yields"
ET = ZoneInfo("America/New_York")
INCENTIVE_APY = 15.0  # flag headline APY above this as likely incentive- or risk-driven

# Curated live pools to pull from DefiLlama. meta=None prefers a pool with no poolMeta
# (core market). meta="..." matches a case-insensitive substring of poolMeta.
# risk/us_access/reason are research labels, not advice.
WATCH = [
    # stablecoin lending
    dict(id="aave-v3-eth-usdc", category="stablecoin lending", project="aave-v3", chain="Ethereum", symbol="USDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Blue-chip lending market; smart-contract and utilization risk, rate moves with demand."),
    dict(id="aave-v3-eth-usdt", category="stablecoin lending", project="aave-v3", chain="Ethereum", symbol="USDT",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Same Aave v3 market as USDC; plus USDT issuer/custody concentration."),
    dict(id="aave-v3-base-usdc", category="stablecoin lending", project="aave-v3", chain="Base", symbol="USDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Smaller TVL than Ethereum; headline APY is utilization-driven and can fall quickly."),
    dict(id="compound-v3-eth-usdc", category="stablecoin lending", project="compound-v3", chain="Ethereum", symbol="USDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Established lending market; smart-contract and utilization risk."),
    dict(id="compound-v3-eth-usdt", category="stablecoin lending", project="compound-v3", chain="Ethereum", symbol="USDT",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Same Compound III market; plus USDT issuer risk."),
    dict(id="morpho-steak-usdc-eth", category="stablecoin lending", project="morpho-blue", chain="Ethereum", symbol="STEAKUSDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Steakhouse-curated Morpho vault; curator + Morpho + underlying market risk."),
    dict(id="morpho-steak-usdc-base", category="stablecoin lending", project="morpho-blue", chain="Base", symbol="STEAKUSDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Same Steakhouse USDC vault on Base; pick the larger-TVL listing if two appear."),
    dict(id="morpho-gauntlet-usdc-base", category="stablecoin lending", project="morpho-blue", chain="Base", symbol="GTUSDCP",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Gauntlet-curated Morpho USDC vault; curator and smart-contract risk."),
    dict(id="morpho-spark-usdc-base", category="stablecoin lending", project="morpho-blue", chain="Base", symbol="SPARKUSDC",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Spark-curated Morpho USDC vault; Sky/Spark + Morpho stack."),
    dict(id="sparklend-eth-dai", category="stablecoin lending", project="sparklend", chain="Ethereum", symbol="DAI",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="SparkLend DAI supply; Sky-related smart-contract risk."),
    # Sky / sUSDS / sDAI
    dict(id="sky-susds-eth", category="Sky savings", project="sky-lending", chain="Ethereum", symbol="SUSDS",
         risk="low-med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Governance-set Sky Savings Rate paid from protocol surplus; USDS/Sky contract and depeg risk."),
    dict(id="spark-savings-usdt", category="Sky savings", project="spark-savings", chain="Ethereum", symbol="USDT",
         risk="low-med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Spark savings on USDT, routed into the Sky rate stack; plus USDT issuer risk."),
    dict(id="spark-savings-usdc", category="Sky savings", project="spark-savings", chain="Ethereum", symbol="USDC",
         risk="low-med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Spark savings on USDC into the Sky rate stack."),
    dict(id="sky-sdai-eth", category="Sky savings", project="sky-lending", chain="Ethereum", symbol="SDAI",
         risk="low-med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Legacy DAI savings; rate has lagged sUSDS since the Sky migration."),
    dict(id="sky-stusds-eth", category="Sky savings", project="sky-lending", chain="Ethereum", symbol="STUSDS",
         meta="Expert", risk="high", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Sky 'Expert Mode' stUSDS; higher rate reflects credit/loss exposure, not a savings-rate equivalent."),
    # yield-bearing stables / RWA
    dict(id="ethena-susde", category="yield-bearing stable", project="ethena-usde", chain="Ethereum", symbol="SUSDE",
         risk="high", us_access="no — Ethena ToS and staking contract restrict US persons",
         reason="sUSDe yield comes from delta-neutral funding; exchange, custody, depeg and funding-regime risk. 7-day unstake."),
    dict(id="ondo-usdy-eth", category="tokenized T-bills", project="ondo-yield-assets", chain="Ethereum", symbol="USDY",
         risk="low-med", us_access="no — Regulation S, non-US persons only",
         reason="Short-term Treasuries + deposits via Ondo; issuer/KYC and transfer-restriction risk. Tracks T-bills minus fees."),
    dict(id="ondo-ousg-eth", category="tokenized T-bills", project="ondo-yield-assets", chain="Ethereum", symbol="OUSG",
         risk="low-med", us_access="US accredited investors who are also qualified purchasers, via Ondo KYC",
         reason="Tokenized short-term Treasuries (often via BUIDL); private-fund eligibility and transfer locks."),
    dict(id="buidl-eth-inst", category="tokenized T-bills", project="blackrock-buidl", chain="Ethereum", symbol="BUIDL",
         meta="Institutional", risk="low", us_access="US qualified purchasers only (Securitize; typical $5M minimum)",
         reason="BlackRock USD Institutional Digital Liquidity Fund; underlying T-bill/cash risk is low, access is institutional."),
    dict(id="invesco-ustb", category="tokenized T-bills", project="invesco-ustb", chain="Ethereum", symbol="USTB",
         risk="low-med", us_access="typically qualified / KYC institutional; confirm on the issuer page",
         reason="Tokenized T-bill fund; tracks bills minus fees, with issuer and transfer-restriction risk."),
    dict(id="frax-sfrxusd", category="yield-bearing stable", project="frax", chain="Ethereum", symbol="SFRXUSD",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Frax sUSDe-style yield on frxUSD; smart-contract and Frax/strategy risk."),
    dict(id="frax-sfrax", category="yield-bearing stable", project="frax", chain="Ethereum", symbol="SFRAX",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Legacy sFRAX; rate has been low versus sUSDS and sfrxUSD."),
    dict(id="maple-syrup-usdc", category="private credit", project="maple", chain="Ethereum", symbol="USDC",
         meta="Syrup", risk="med-high", us_access="KYC; often limited to accredited or institutional users — confirm Maple terms",
         reason="Maple syrupUSDC is underwritten private credit, not risk-free lending; borrower default and lockup risk."),
    # Pendle fixed (PT buy)
    dict(id="pendle-pt-susde-eth", category="Pendle fixed", project="pendle-v2", chain="Ethereum", symbol="SUSDE",
         meta="buying PT", risk="high", us_access="protocol open; official UI may geo-restrict US persons; underlying sUSDe is US-restricted",
         reason="Fixed PT until maturity, but you still hold Ethena/sUSDe credit, depeg and liquidity risk."),
    dict(id="pendle-pt-siusd-eth", category="Pendle fixed", project="pendle-v2", chain="Ethereum", symbol="SIUSD",
         meta="buying PT", risk="high", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Fixed PT on a smaller, less-known USD product; credit and liquidity risk, modest TVL."),
    # ETH staking / LSTs
    dict(id="lido-steth", category="ETH staking", project="lido", chain="Ethereum", symbol="STETH",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="ETH price risk plus Lido/validator and stETH-discount risk; this is not a dollar yield."),
    dict(id="rocket-reth", category="ETH staking", project="rocket-pool", chain="Ethereum", symbol="RETH",
         risk="med", us_access="protocol open; official UI may geo-restrict US persons",
         reason="ETH price risk plus Rocket Pool/node-operator risk."),
    dict(id="etherfi-weeth", category="ETH staking", project="ether.fi-stake", chain="Ethereum", symbol="WEETH",
         risk="med-high", us_access="protocol open; official UI may geo-restrict US persons",
         reason="Liquid restaking on top of ETH staking; extra protocol and slashing-stack risk."),
    dict(id="cbeth", category="ETH staking", project="coinbase-wrapped-staked-eth", chain="Ethereum", symbol="CBETH",
         risk="med", us_access="yes for eligible Coinbase customers (ETH price risk remains)",
         reason="Coinbase-wrapped staked ETH; custody plus ETH price and validator risk."),
]

# Manual / non-Llama rows filled at runtime (Coinbase page, FRED, live funding, prior study).
COINBASE_USDC_FALLBACK = 3.75  # advertised on coinbase.com/usdc when this script was written
COINBASE_URL = "https://www.coinbase.com/usdc"
CARRY_HIST = dict(
    id="funding-carry-hist", category="delta-neutral funding carry", name="Funding carry (paper study, OOS)",
    apy=None, apy_note="~5–6% net on notional (BTC/ETH always-on, Coinbase-cost OOS through 2026-11); ~4.6–4.8% on posted cash after margin",
    tvl=None, chain="CDE / public venues (historical proxy was Binance Vision)",
    risk="med", us_access="US Coinbase Derivatives (CDE) if eligible; live funding is venue-specific",
    reason="Edge is the funding rate, not a prediction; needs margin, two legs, and a durable positive-funding regime. Live rates can go negative.",
    source="carry-futures-sims/RESULTS.md (collected 2026-11-11)",
)


def _num(x):
    try:
        return None if x is None else float(x)
    except (TypeError, ValueError):
        return None


def pick(pools, spec):
    """Highest-TVL pool matching project, chain, symbol, and optional meta substring."""
    proj, chain, sym = spec["project"], spec["chain"], spec["symbol"].upper()
    meta = (spec.get("meta") or "").lower()
    hits = []
    for p in pools:
        if p.get("project") != proj or p.get("chain") != chain:
            continue
        if (p.get("symbol") or "").upper() != sym:
            continue
        pm = p.get("poolMeta")
        if meta:
            if not pm or meta not in str(pm).lower():
                continue
        elif pm:  # prefer the core (no-meta) pool when meta is not requested
            continue
        hits.append(p)
    if not hits and not meta:
        hits = [p for p in pools if p.get("project") == proj and p.get("chain") == chain
                and (p.get("symbol") or "").upper() == sym]
    if not hits:
        return None
    return max(hits, key=lambda p: p.get("tvlUsd") or 0)


def attach(spec, pool):
    apy, base, rew = _num(pool.get("apy")), _num(pool.get("apyBase")), _num(pool.get("apyReward")) or 0.0
    row = dict(spec)
    row.update(
        name=f"{pool['project']} {pool['symbol']}" + (f" ({pool['poolMeta']})" if pool.get("poolMeta") else ""),
        chain=pool.get("chain"), symbol=pool.get("symbol"), project=pool.get("project"),
        apy=apy, apy_base=base, apy_reward=rew or None, apy_mean_30d=_num(pool.get("apyMean30d")),
        tvl=pool.get("tvlUsd"), pool_meta=pool.get("poolMeta"), pool_id=pool.get("pool"),
        flag_high=bool(apy is not None and apy > INCENTIVE_APY),
        found=True,
    )
    return row


def coinbase_usdc():
    """Parse the public Coinbase USDC page. Falls back to the last advertised rate if the fetch fails."""
    try:
        html = get(COINBASE_URL, timeout=20).decode("utf-8", "replace")
        m = re.search(r"([0-9]+(?:\.[0-9]+)?)\s*%\s*(?:APY|rewards rate|REWARDS RATE)", html, re.I)
        if not m:
            m = re.search(r"(?:APY|rewards rate)[^0-9]{0,40}([0-9]+(?:\.[0-9]+)?)\s*%", html, re.I)
        apy = float(m.group(1)) if m else COINBASE_USDC_FALLBACK
        note = "parsed from coinbase.com/usdc" if m else f"parse missed; fallback {COINBASE_USDC_FALLBACK}%"
        return dict(id="coinbase-usdc", category="CEX earn (US)", name="Coinbase USDC rewards (Coinbase One)",
                    apy=apy, apy_base=apy, apy_reward=None, tvl=None, chain="Coinbase custody (off-chain)",
                    risk="low-med", us_access="yes, eligible US Coinbase One members (rate can vary by account)",
                    reason="Custodial, uninsured (not FDIC/SIPC) Coinbase counterparty rewards, not a bank account. One membership ($4.99/mo and up) is required in the US, so net APY shrinks on small balances and trails T-bills at any size.",
                    source=COINBASE_URL, found=True, flag_high=apy > INCENTIVE_APY, note=note)
    except Exception as e:
        return dict(id="coinbase-usdc", category="CEX earn (US)", name="Coinbase USDC rewards (Coinbase One)",
                    apy=COINBASE_USDC_FALLBACK, apy_base=COINBASE_USDC_FALLBACK, apy_reward=None, tvl=None,
                    chain="Coinbase custody (off-chain)", risk="low-med",
                    us_access="yes, eligible US Coinbase One members (rate can vary by account)",
                    reason="Custodial, uninsured (not FDIC/SIPC) Coinbase counterparty rewards. One membership required in the US.",
                    source=COINBASE_URL, found=True, flag_high=False,
                    note=f"fetch failed ({type(e).__name__}); fallback {COINBASE_USDC_FALLBACK}%")


def treasury_bills():
    """FRED constant-maturity yields (investment-yield style), latest business day."""
    out = []
    for sid, label in (("DGS1MO", "1-month T-bill (FRED DGS1MO, constant maturity)"),
                       ("DGS3MO", "3-month T-bill (FRED DGS3MO, constant maturity)")):
        s = fred.series(sid, days=60)
        if s.get("error"):
            out.append(dict(id=sid.lower(), name=label, error=s["error"]))
            continue
        out.append(dict(id=sid.lower(), name=label, apy=s["closes"][-1], asof=s["asof"],
                        source=s["source"], risk="low", us_access="yes",
                        reason="Direct US Treasury obligation; the risk-free benchmark these tokenized T-bill products track."))
    return out


def funding_live():
    hl = perps.hyperliquid(coins=("BTC", "ETH", "SOL"))
    rows = []
    if hl.get("data"):
        for coin, d in hl["data"].items():
            rows.append(dict(venue="Hyperliquid", coin=coin, funding_apr_pct=d.get("funding_apr_pct"),
                             asof=hl.get("asof"), source=hl.get("source")))
    for coin in ("BTC", "ETH"):
        k = perps.kraken_funding(coin)
        if not k.get("error"):
            rows.append(dict(venue="Kraken Futures", coin=coin, funding_apr_pct=k.get("funding_apr_pct"),
                             asof=k.get("asof"), source=k.get("source")))
    return rows


def _fmt_apy(x):
    return "n/a" if x is None else f"{x:.2f}%"


def _fmt_tvl(x):
    if not x:
        return "n/a"
    return f"${x/1e9:.2f}B" if x >= 1e9 else f"${x/1e6:.1f}M"


def _base_rew(row):
    if row.get("apy_base") is None and not row.get("apy_reward"):
        return _fmt_apy(row.get("apy"))
    b = _fmt_apy(row.get("apy_base"))
    r = row.get("apy_reward")
    return b if not r else f"{b} + {r:.2f}% rewards"


# Risk-adjusted shortlist: skip high-risk, US-blocked, >15%, ETH staking, and thin books.
# Penalty is in APY points so a low-risk 4% beats a medium 5% minus 1.5.
_RISK_PENALTY = {"low": 0.0, "low-med": 0.8, "med": 1.5, "med-high": 2.5}
MIN_TVL = 50_000_000  # skip utilization spikes on small pools; CEX/T-bill rows have tvl=None


def score(row, tbill=4.0):
    if not row.get("found") or row.get("flag_high") or row.get("apy") is None:
        return None
    if str(row.get("us_access", "")).lower().startswith("no"):
        return None
    if row.get("category") == "ETH staking":
        return None  # not a dollar yield
    if row.get("risk") not in _RISK_PENALTY:
        return None
    if row.get("tvl") is not None and row["tvl"] < MIN_TVL:
        return None
    base = row.get("apy_base") if row.get("apy_base") is not None else row.get("apy")
    core = (base or 0) - 0.5 * (row.get("apy_reward") or 0)
    # Round to 2 decimals so a 0.001% APY difference does not beat a much larger pool.
    return round(core - _RISK_PENALTY[row["risk"]], 2)


def render(asof, rows, bills, funding, carry, src):
    lines = [
        f"# Stablecoin and DeFi yields (paper scan)",
        "",
        f"Data as of **{asof}**. Public sources only. Not an offer, not advice, no deposits or sign-ups were made.",
        "",
        "## Benchmarks",
        "",
    ]
    if bills:
        for b in bills:
            if b.get("error"):
                lines.append(f"- {b['name']}: unavailable ({b['error']})")
            else:
                lines.append(f"- {b['name']}: **{_fmt_apy(b['apy'])}** as of {b.get('asof')} ({b.get('source')}). US-accessible, low risk — the cash benchmark.")
    lines += [
        "",
        f"- Coinbase USDC rewards: see the CEX row below (public page {COINBASE_URL}).",
        "- Historical paper funding carry (BTC/ETH always-on, Coinbase-cost out-of-sample, carry-futures-sims, collected 2026-11-11): **~5–6% net on notional**, about **4.6–4.8% on posted cash** after overnight margin. Live funding (below) is a different regime today.",
        "",
        "## Live rows",
        "",
        "| Category | Name | Chain | APY (base + rewards) | 30d mean | TVL | Risk | US access | Why |",
        "|---|---|---|---:|---:|---:|---|---|---|",
    ]
    for r in rows:
        if not r.get("found"):
            lines.append(f"| {r.get('category','')} | {r.get('id')} | — | not found | — | — | — | — | Pool missing in today's DefiLlama pull. |")
            continue
        flag = " **>15% flag**" if r.get("flag_high") else ""
        mean = _fmt_apy(r.get("apy_mean_30d")) if r.get("apy_mean_30d") is not None else "n/a"
        lines.append(
            f"| {r.get('category','')} | {r.get('name')}{flag} | {r.get('chain')} | "
            f"{_fmt_apy(r.get('apy'))} ({_base_rew(r)}) | {mean} | {_fmt_tvl(r.get('tvl'))} | "
            f"{r.get('risk')} | {r.get('us_access')} | {r.get('reason')} |"
        )
    lines += ["", "## Live funding (delta-neutral carry, snapshot)", "",
              "Positive APR means a long-spot / short-perp book would be *paid* funding; negative means it would *pay*. "
              "These are one-hour annualized snapshots, not a forecast.", "",
              "| Venue | Coin | Funding APR | As of |",
              "|---|---|---:|---|"]
    for f in funding:
        lines.append(f"| {f['venue']} | {f['coin']} | {_fmt_apy(f.get('funding_apr_pct'))} | {f.get('asof')} |")
    if not funding:
        lines.append("| — | — | unavailable | — |")

    # Top risk-adjusted among found, US-not-blocked, not high-flag, not ETH staking.
    tbill = next((b["apy"] for b in bills if b.get("apy") is not None), 4.0)
    ranked = sorted((r for r in rows if score(r, tbill) is not None),
                    key=lambda r: (-score(r, tbill), -(r.get("tvl") or 0)))
    # Always mention T-bills and historical carry in the shortlist context.
    lines += [
        "",
        "## Top options, ranked by risk-adjusted dollar yield",
        "",
        "ETH staking, US-blocked names, >15% APYs, high-risk rows, and pools under $50M TVL are omitted. "
        f"Cash benchmark is the latest 1-month T-bill, {_fmt_apy(tbill)}. "
        "Qualified-purchaser and accredited-only products (BUIDL, OUSG) are footnoted, not ranked as retail options. "
        "US Treasuries are state-tax exempt; a 4% T-bill can beat a 4.5% DeFi yield after state tax. DeFi and Sky rates are floating.",
        "",
    ]
    def _inst(r):
        u = (r.get("us_access") or "").lower()
        return any(s in u for s in ("qualified purchaser", "accredited", "institutional", "$5m"))
    short, inst, n, seen, seen_projects = [], [], 1, set(), set()
    if bills and bills[0].get("apy") is not None:
        short.append(f"{n}. **US 1-month T-bill {_fmt_apy(bills[0]['apy'])}** — low risk, fully US-accessible cash benchmark (official 4-week / 13-week coupon-equivalent on 2026-11-13: 4.02% / 4.23%).")
        n += 1
    for r in ranked:
        if r["id"] in seen:
            continue
        proj = r.get("project") or r["id"]
        if proj in seen_projects:
            continue
        seen.add(r["id"]); seen_projects.add(proj)
        line = (f"**{r['name']} {_fmt_apy(r.get('apy'))}** ({r.get('risk')} risk) — {_base_rew(r)} on {_fmt_tvl(r.get('tvl'))}, {r.get('chain')}. {r.get('reason')} US: {r.get('us_access')}.")
        if _inst(r):
            inst.append(f"- {line}")
            continue
        if (r.get("apy") or 0) < tbill - 1:  # skip leftover low-rate legacy pools (e.g. sFRAX)
            continue
        short.append(f"{n}. {line}")
        n += 1
        if len(short) >= 8:
            break
    lines.extend(short)
    if inst:
        lines += ["", "Institutional / qualified-purchaser only (not ranked as retail):", ""] + inst

    # Recommendation vs funding carry and prediction-market maker.
    live_btc_hl = next((f for f in funding if f["venue"] == "Hyperliquid" and f["coin"] == "BTC"), None)
    live_eth_hl = next((f for f in funding if f["venue"] == "Hyperliquid" and f["coin"] == "ETH"), None)
    lines += [
        "",
        "## Versus funding carry and the prediction-market test",
        "",
        f"Funding carry remains the best *tested* crypto yield in our paper work (~5–6% net on notional historically), "
        f"but today's live funding is mixed: Hyperliquid BTC is "
        f"{_fmt_apy(live_btc_hl['funding_apr_pct']) if live_btc_hl else 'n/a'} and ETH is "
        f"{_fmt_apy(live_eth_hl['funding_apr_pct']) if live_eth_hl else 'n/a'} annualized, so an always-on ETH or SOL book would currently pay funding, not earn it. "
        f"Plain dollar yields (T-bills ~4%, Coinbase USDC ~3.75% only if Coinbase One is already paid for, Sky sUSDS 3.80%, large Morpho/Aave USDC around 3.8–4.5%) are the more reliable cash park today; T-bills also have a state-tax edge. "
        f"Do not size into Ethena, stUSDS Expert, or high Pendle PTs for a 'safer than carry' sleeve. "
        f"The prediction-market maker test is still negative on paper — it is not a substitute for either sleeve.",
        "",
        "## Notes",
        "",
        f"- Source: [{src}]({src}), plus FRED public CSVs, {COINBASE_URL}, Hyperliquid public info, and Kraken Futures public funding.",
        "- FRED DGS1MO/DGS3MO are constant-maturity yields and can lag the latest business day. Official Treasury coupon-equivalent bill rates (a closer cash-APY comparison) are at home.treasury.gov daily Treasury bill rates; they were 4.02% (4-week) and 4.23% (13-week) on 2026-11-13, the last session before this Saturday scan.",
        "- The shortlist drops high-risk rows, US-blocked names, APY > 15%, ETH staking, and pools under $50M TVL (thin utilization spikes). Reward-token APY is halved in the score.",
        "- APY > 15% is flagged as likely incentive- or risk-driven. Reward-token APY can go to zero when emissions stop.",
        "- DefiLlama TVL and APY can lag or double-count across chains and vault wrappers. Official protocol pages win if they disagree.",
        "- US-access labels are a research summary of public terms, not legal advice. Frontends change geo-rules without notice.",
        "- This scan does not hold custody, sign up, deposit, or place quotes.",
        "",
    ]
    return "\n".join(lines) + "\n", ranked


def run(offline=False):
    asof = dt.datetime.now(ET).strftime("%Y-%m-%d %-I:%M %p ET")
    pools, src = llama.pools(max_age_hours=8760 if offline else 6)
    rows = []
    for spec in WATCH:
        pool = pick(pools, spec)
        rows.append(attach(spec, pool) if pool else dict(spec, found=False, name=spec["id"]))
    # If two Steakhouse Base USDC hits were possible, pick already took highest TVL.
    cb = coinbase_usdc()
    rows.insert(0, cb)
    bills = treasury_bills()
    fund = funding_live()
    md, ranked = render(asof, rows, bills, fund, CARRY_HIST, src)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "latest.md").write_text(md)
    payload = dict(asof=asof, source=src, rows=rows, treasury=bills, funding=fund, carry_hist=CARRY_HIST,
                   ranked_ids=[r["id"] for r in ranked])
    (OUT_DIR / "latest.json").write_text(json.dumps(payload, indent=2, default=str) + "\n")
    return payload, md


def main(argv=None):
    ap = argparse.ArgumentParser(description="Paper-only public stablecoin/DeFi yield scan")
    ap.add_argument("--offline", action="store_true", help="use the cached DefiLlama pull even if stale")
    args = ap.parse_args(argv)
    payload, md = run(offline=args.offline)
    sys.stdout.write(md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
