"""At-rest encryption for device credentials, and the App<->companion
integration pairing code.

Pairing is a single opaque code (base64url of a small JSON payload) shown
once in the App's Settings screen and pasted into one field in the
integration's config flow -- no separate host/port entry, per the user's
explicit choice during design. It carries the App's internal-network host
and port (so the integration doesn't need zeroconf / host_network to find
it) plus a random bearer token the integration presents on every call to
`/api/integration/*`.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import stat

from cryptography.fernet import Fernet, InvalidToken

from ir_rf_hub.config import settings

_PAIRING_TOKEN_SETTING_KEY = "pairing_token"


def _load_or_create_fernet_key() -> bytes:
    path = settings.secret_key_path
    if path.exists():
        return path.read_bytes()

    key = Fernet.generate_key()
    path.write_bytes(key)
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        # Best-effort on platforms (e.g. local Windows dev) without POSIX
        # permission bits; the container always runs on Linux.
        pass
    return key


_fernet: Fernet | None = None


def get_fernet() -> Fernet:
    global _fernet
    if _fernet is None:
        _fernet = Fernet(_load_or_create_fernet_key())
    return _fernet


def encrypt_secret(plaintext: str) -> bytes:
    return get_fernet().encrypt(plaintext.encode("utf-8"))


def decrypt_secret(ciphertext: bytes) -> str:
    try:
        return get_fernet().decrypt(ciphertext).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Stored secret could not be decrypted") from exc


def generate_pairing_token() -> str:
    return secrets.token_urlsafe(32)


def encode_pairing_code(*, host: str, port: int, token: str) -> str:
    payload = {"h": host, "p": port, "t": token, "v": 1}
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_pairing_code(code: str) -> dict:
    padding = "=" * (-len(code) % 4)
    try:
        raw = base64.urlsafe_b64decode(code + padding)
        payload = json.loads(raw)
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid pairing code") from exc

    if payload.get("v") != 1 or not all(k in payload for k in ("h", "p", "t")):
        raise ValueError("Invalid pairing code")

    return {"host": payload["h"], "port": int(payload["p"]), "token": payload["t"]}


_TOKEN_HASH_PREFIX = "sha256$"


def hash_integration_token(token: str) -> str:
    """A plain SHA-256, deliberately -- not bcrypt/argon2.

    Those exist to make *low-entropy human passwords* expensive to guess.
    This token is 32 random bytes from `secrets.token_urlsafe` (256 bits),
    so there is nothing to brute-force and a slow KDF would only add cost
    to every authenticated call the integration makes.
    """
    return _TOKEN_HASH_PREFIX + hashlib.sha256(token.encode("utf-8")).hexdigest()


def is_hashed_token(stored: str) -> bool:
    return stored.startswith(_TOKEN_HASH_PREFIX)


def verify_integration_token(presented: str, stored: str) -> bool:
    """Accepts either storage form.

    The token is held in plaintext only while the App is still unpaired,
    because the pairing code shown in the UI has to contain it. Once
    something has paired, the stored value is replaced by its hash (see
    api/rest/integration.py) -- from then on the database holds nothing
    that would let a reader authenticate as the integration. Installs
    that paired before this existed keep working on the plaintext branch
    and are upgraded in place on their next authenticated call.
    """
    if is_hashed_token(stored):
        return secrets.compare_digest(hash_integration_token(presented), stored)
    return secrets.compare_digest(presented, stored)
