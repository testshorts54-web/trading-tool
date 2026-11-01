"""Read-only HTTP GET (urllib). No POST, no auth headers, no keys."""
import time, urllib.request
UA = {"User-Agent": "trading-tool-research/0.1 (read-only)"}

def get(url, timeout=30, retries=2, ua=True):
    """ua=False sends urllib's default User-Agent (FRED stalls on custom UAs)."""
    err = None
    for i in range(retries + 1):
        try:
            return urllib.request.urlopen(urllib.request.Request(url, headers=UA if ua else {}), timeout=timeout).read()
        except Exception as e:
            err = e; time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"GET failed {url}: {err}")

# The one exception to GET-only: Hyperliquid's public market-data endpoint only answers JSON POSTs.
# Locked to that single read-only URL and an allowlist of info types; anything else raises before any network call.
HL_INFO_URL = "https://api.hyperliquid.xyz/info"
HL_INFO_TYPES = {"metaAndAssetCtxs", "fundingHistory"}

def hl_info(body, timeout=20, url=HL_INFO_URL):
    import json
    if url != HL_INFO_URL: raise ValueError(f"refused: {url} is not the allowlisted read-only info URL")
    if not isinstance(body, dict) or body.get("type") not in HL_INFO_TYPES:
        raise ValueError(f"refused: info type {body.get('type') if isinstance(body, dict) else body!r} not allowlisted")
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**UA, "Content-Type": "application/json"})
    return json.loads(urllib.request.urlopen(req, timeout=timeout).read())
