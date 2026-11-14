"""Fails if any live-trading, wallet, key or order-placing code appears anywhere in trading-tool."""
import re, unittest, tempfile
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
J = "".join   # patterns are split so this file does not match itself
BANNED = [J(["create", "_order"]), J(["place", "_order"]), J(["submit", "_order"]), J(["cancel", "_order"]),
          J(["order", "_send"]), J(["eth", "_account"]), J(["private", "_key"]), J(["secret", "_key"]),
          J(["api", "_secret"]), J(["mnem", "onic"]), J(["sign", "_transaction"]), J(["sign", "_typed_data"]),
          J(["web", "3"]), J(["cc", "xt"]), J(["robin", "_stocks"]), J(["alp", "aca"]), J(["wal", "let"]),
          r"\bExchange\(", J(["hyper", "liquid.xyz/exchange"]), r"/api/v\d/order", J(["live", "_guard"]),
          r"method\s*=\s*['\"](POST|PUT|DELETE)", J(["Authori", "zation"]), J(["Bear", "er "])]
RX = re.compile("|".join(BANNED), re.I)

def scan(root):
    hits = []
    for p in Path(root).rglob("*"):
        if p.suffix in (".py", ".sh", ".toml", ".cfg", ".txt", ".ini") and p.resolve() != Path(__file__).resolve() and "out" not in p.parts:
            for i, line in enumerate(p.read_text(errors="ignore").splitlines(), 1):
                if RX.search(line): hits.append(f"{p.relative_to(root)}:{i}: {line.strip()[:100]}")
    return hits

class NoLiveCode(unittest.TestCase):
    def test_tree_is_clean(self):
        self.assertEqual(scan(ROOT), [], "live/wallet/order code found")
    def test_reused_btlib_modules_clean(self):
        bt = Path("/workspace/backtest/btlib")
        hits = [f"{n}:{i}" for n in ("trades.py", "stats.py") for i, l in enumerate((bt / n).read_text().splitlines(), 1) if RX.search(l)]
        self.assertEqual(hits, [])
    def test_only_post_is_allowlisted_info_call(self):
        posts = [str(p.relative_to(ROOT)) for p in ROOT.rglob("*.py") if "out" not in p.parts and p.resolve() != Path(__file__).resolve() and "data=" in p.read_text() and "urlopen" in p.read_text()]
        self.assertEqual(posts, ["tt/http.py"])
    def test_websocket_hosts_allowlisted(self):
        # read-only public streams only; adding a host means editing this set on purpose
        hosts = {h for p in ROOT.rglob("*.py") if "out" not in p.parts and p.resolve() != Path(__file__).resolve()
                 for h in re.findall(r"wss://([^/:'\"]+)", p.read_text())}
        self.assertLessEqual(hosts, {"stream.binance.us"})
    def test_scanner_catches_planted_code(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "bad.py").write_text("client." + "create" + "_order('BTC', 1)\n")
            self.assertEqual(len(scan(d)), 1)
    def test_paper_only_and_risk_defaults(self):
        from tt import config
        self.assertTrue(config.PAPER_ONLY)
        self.assertEqual(config.MAX_POSITION_PCT, 0.10)
        self.assertEqual(config.MAX_RISK_PER_TRADE_PCT, 0.01)

if __name__ == "__main__": unittest.main()
