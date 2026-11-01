"""Constants. Paper-only research tool; nothing here can trade."""
PAPER_ONLY = True
# Kennedy's rules (trade-journal/rules.md). flow's 20% / 1.5% defaults are NOT used.
MAX_POSITION_PCT = 0.10       # max 10% of account per position
MAX_RISK_PER_TRADE_PCT = 0.01 # max 1% of account at risk per trade
# Staleness limits (calendar days between data date and run date)
MAX_AGE_DAYS = {"equity": 5, "crypto": 2, "fred": 7}
# Validation / risk (Part B)
MIN_TRADES = 30                     # below this per IS/OOS window: verdict INSUFFICIENT, no stats shown
COST_BPS = {"equity": (10, 20), "crypto": (25, 90)}   # (base, stress) per side, fees + slippage
OOS_FRACTION = 0.30                 # last 30% of bars after warm-up is out-of-sample
NULL_DRAWS, NULL_SEED = 500, 7
DAILY_DD_BREAKER_PCT = 0.04         # flow's -4% day breaker; open question for Kennedy
BLOCK_ON_RISK_OFF = False           # risk-off regime warns by default; open question
