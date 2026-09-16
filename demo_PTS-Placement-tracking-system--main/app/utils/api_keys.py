"""API key generation and verification for organization-level API access.

The key shown to the user (once, at generation time) is a random secret
prefixed with "pts_live_" for easy identification in logs/support tickets.
Only its hash is ever stored (Organization.api_key) - same trust model as
a password, so a leaked database does not expose usable keys.
"""

import secrets

from werkzeug.security import check_password_hash, generate_password_hash


def generate_api_key():
    """Returns (plaintext_key, hashed_key). Caller must show plaintext_key
    to the user immediately and never persist it anywhere - only
    hashed_key should be saved (e.g. to Organization.api_key)."""
    plaintext_key = "pts_live_" + secrets.token_urlsafe(32)
    hashed_key = generate_password_hash(plaintext_key)
    return plaintext_key, hashed_key


def verify_api_key(plaintext_key, hashed_key):
    """True if plaintext_key (e.g. from an X-API-Key header) matches the
    stored hash. False for any mismatch, empty input, or missing hash -
    never raises, so callers can use it directly in an if-check."""
    if not plaintext_key or not hashed_key:
        return False
    try:
        return check_password_hash(hashed_key, plaintext_key)
    except Exception:
        return False
