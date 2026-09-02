"""URL validation shared by credential-bearing HTTP clients."""

import ipaddress
from urllib.parse import urlsplit, urlunsplit


def normalize_service_base_url(raw_url: str, label: str = "Service URL") -> str:
    """Return a normalized HTTPS URL, allowing HTTP only on loopback hosts."""
    value = (raw_url or "").strip()
    parsed = urlsplit(value)
    if not parsed.scheme or not parsed.hostname:
        raise ValueError(f"{label} must be a valid absolute URL.")

    hostname = parsed.hostname.lower()
    is_loopback = hostname == "localhost"
    if not is_loopback:
        try:
            is_loopback = ipaddress.ip_address(hostname).is_loopback
        except ValueError:
            is_loopback = False

    if parsed.scheme != "https" and not (parsed.scheme == "http" and is_loopback):
        raise ValueError(f"{label} must use HTTPS. HTTP is allowed only for local development.")
    if parsed.username or parsed.password:
        raise ValueError(f"{label} must not contain embedded credentials.")
    if parsed.query or parsed.fragment:
        raise ValueError(f"{label} must not contain a query string or fragment.")

    path = parsed.path.rstrip("/")
    return urlunsplit((parsed.scheme, parsed.netloc, path, "", ""))


def reject_redirect(response, label: str = "Request") -> None:
    """Reject redirects before a credential-bearing request can be replayed elsewhere."""
    status_code = getattr(response, "status_code", 200)
    if 300 <= status_code < 400:
        raise ValueError(f"{label} was redirected and has been blocked for security.")
