"""HTTPS transport for a transaction already admitted by the canary."""
import re
import urllib.error
import urllib.request

from core import DenyRedirect, Gate

ENDPOINT = "https://mempool.space/testnet4/api/tx"
TXID = re.compile(r"[0-9a-f]{64}")


def broadcast(raw, txid):
    if not TXID.fullmatch(txid) or not re.fullmatch(r"(?:[0-9a-f]{2}){1,100000}", raw):
        raise Gate("Invalid reserved Testnet4 transaction")
    request = urllib.request.Request(
        ENDPOINT, data=raw.encode("ascii"), method="POST",
        headers={"Content-Type": "text/plain", "Accept": "text/plain"},
    )
    opener = urllib.request.build_opener(DenyRedirect())
    try:
        with opener.open(request, timeout=15) as response:
            reply = response.read(129).strip()
    except (OSError, urllib.error.URLError, Gate):
        raise Gate("HTTPS submission outcome uncertain; check the reserved txid before retry") from None
    if reply != txid.encode("ascii"):
        raise Gate("HTTPS relay did not return the reserved transaction ID")
    return txid
