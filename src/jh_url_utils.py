# jh_url_utils.py — shared URL sanitization for outbound OS calls
"""
Centralized guard between vacancy data (scraped/AI-generated, thus
untrusted) and webbrowser.open(). Without this check, a malformed or
malicious "url" field — an empty string, a relative path, or a custom URI
scheme (e.g. "javascript:", "file:", "mailto:", or an arbitrary
"myapp://..." handler) — gets handed straight to the OS, which can crash
the app or trigger unintended protocol-handler execution.

Every click-handler that ends up calling webbrowser.open() on
user/AI-supplied data must go through safely_open_url() (or sanitize_url()
if it needs to open the browser itself) instead of calling
webbrowser.open() directly.
"""
from urllib.parse import urlparse
import webbrowser

_ALLOWED_SCHEMES = ("http", "https")


def sanitize_url(url_string):
    """
    Validates url_string without opening anything.

    Returns (True, None) if url_string is a safe, absolute http(s) URL.
    Returns (False, reason) otherwise. Never raises.
    """
    if not url_string or not isinstance(url_string, str):
        return False, "Empty URL"

    candidate = url_string.strip()
    if not candidate or candidate == "#":
        return False, "Empty URL"

    try:
        parsed = urlparse(candidate)
    except Exception as e:
        return False, f"Error parsing URL: {e}"

    if parsed.scheme.lower() not in _ALLOWED_SCHEMES or not parsed.netloc:
        return False, "Invalid or relative link format"

    return True, None


def safely_open_url(url_string):
    """
    Validates url_string and only calls webbrowser.open() if it passes.

    Returns (True, None) on a successful open.
    Returns (False, reason) if the URL was rejected or webbrowser.open()
    itself raised — in both cases the OS never sees an unvalidated string.
    """
    ok, reason = sanitize_url(url_string)
    if not ok:
        return False, reason

    try:
        webbrowser.open(url_string)
        return True, None
    except Exception as e:
        return False, f"Error opening URL: {e}"
