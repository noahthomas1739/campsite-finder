"""Fetching pages, with a curl fallback for old Pythons.

macOS's built-in Python 3.9 links an old LibreSSL that can't negotiate the TLS
versions some sites (e.g. Campspot) require; the system curl can.
"""

import shutil
import ssl
import subprocess
import urllib.error
import urllib.request

USER_AGENT = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/124.0 Safari/537.36")
HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}


def _is_tls_failure(err):
    reason = getattr(err, "reason", err)
    return isinstance(reason, ssl.SSLError) or "SSL" in str(reason)


def fetch_text(url, timeout=40, headers=None):
    headers = headers or HEADERS
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=timeout) as resp:
            return resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError:
        raise
    except (urllib.error.URLError, ssl.SSLError) as e:
        if not (_is_tls_failure(e) and shutil.which("curl")):
            raise
    cmd = ["curl", "-sSL", "--compressed", "--max-time", str(timeout), "--fail"]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    out = subprocess.run(cmd + [url], capture_output=True, check=True)
    return out.stdout.decode("utf-8", "replace")
