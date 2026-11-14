"""Cached GET of DefiLlama yields (https://yields.llama.fi/pools). Same disk-cache pattern as
tt.sources.series (allowlisted HTTPS, out/cache). Research only; no keys."""
import json, time, hashlib
from pathlib import Path
from urllib.parse import urlparse
from tt.http import get

ALLOWED_HOSTS = {"yields.llama.fi"}
CACHE = Path(__file__).resolve().parents[2] / "out" / "cache" / "yields"
POOLS_URL = "https://yields.llama.fi/pools"

def fetch(url, max_age_hours=6):
    """Cached GET. Refetch when older than max_age_hours (default 6)."""
    if urlparse(url).scheme != "https" or urlparse(url).hostname not in ALLOWED_HOSTS:
        raise ValueError(f"refused: host not allowlisted: {url}")
    p = CACHE / hashlib.sha1(url.encode()).hexdigest()[:16]
    if p.exists() and time.time() - p.stat().st_mtime < max_age_hours * 3600:
        return p.read_bytes()
    b = get(url, timeout=60)
    CACHE.mkdir(parents=True, exist_ok=True)
    p.write_bytes(b)
    return b

def pools(max_age_hours=6):
    """Return the DefiLlama pool list (data[]) and a source note."""
    raw = json.loads(fetch(POOLS_URL, max_age_hours=max_age_hours))
    if raw.get("status") != "success" or not isinstance(raw.get("data"), list):
        raise RuntimeError("DefiLlama yields: unexpected payload")
    return raw["data"], POOLS_URL
