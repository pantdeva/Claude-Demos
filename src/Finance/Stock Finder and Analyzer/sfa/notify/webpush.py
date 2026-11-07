"""Standard Web Push, sent straight from this computer: no Firebase, no app store.

The dashboard is a web app (PWA). On the phone, the browser subscribes to push with this
computer's VAPID public key and hands the subscription (an endpoint at the browser's
push service plus two keys) to the dashboard. Sending is two standards:

  RFC 8291  message encryption (aes128gcm): only that browser can read the message
  RFC 8292  VAPID: a signed token proving the message comes from the holder of the key

Both are implemented here on the `cryptography` package, so there is nothing else to
install. The VAPID key pair is created on first use and stored in db/push/ (ignored by
git). Deleting it invalidates every subscription: phones then need to enable
notifications again.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import struct
import time
from pathlib import Path
from urllib.parse import urlparse

import requests

KEY_DIR_DEFAULT = Path(__file__).resolve().parents[2] / "db" / "push"


def b64u(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def b64u_dec(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


class PushError(RuntimeError):
    def __init__(self, msg: str, status: int = 0, gone: bool = False):
        super().__init__(msg)
        self.status = status
        self.gone = gone              # the subscription no longer exists: delete it


def _ec():
    try:
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import ec
        from cryptography.hazmat.primitives.asymmetric.utils import decode_dss_signature
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    except ImportError as e:  # pragma: no cover
        raise PushError("the cryptography package is missing: pip install cryptography") from e
    return ec, serialization, hashes, decode_dss_signature, AESGCM


def _raw_public(pub) -> bytes:
    _, serialization, *_ = _ec()
    return pub.public_bytes(serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint)


# ------------------------------------------------------------------ VAPID keys
class Vapid:
    def __init__(self, key_dir: str | Path | None = None):
        ec, serialization, *_ = _ec()
        self.dir = Path(key_dir or os.environ.get("SFA_PUSH_DIR") or KEY_DIR_DEFAULT)
        f = self.dir / "vapid_private.pem"
        if f.exists():
            self.key = serialization.load_pem_private_key(f.read_bytes(), password=None)
        else:
            self.dir.mkdir(parents=True, exist_ok=True)
            self.key = ec.generate_private_key(ec.SECP256R1())
            f.write_bytes(self.key.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
                                                 serialization.NoEncryption()))
            try:
                os.chmod(f, 0o600)
            except OSError:
                pass
        self.public_b64 = b64u(_raw_public(self.key.public_key()))

    def auth_header(self, endpoint: str, contact: str, ttl_s: int = 12 * 3600) -> str:
        ec, _, hashes, decode_dss_signature, _ = _ec()
        u = urlparse(endpoint)
        claims = {"aud": f"{u.scheme}://{u.netloc}", "exp": int(time.time()) + ttl_s, "sub": contact}
        signing = (b64u(json.dumps({"typ": "JWT", "alg": "ES256"}, separators=(",", ":")).encode()) + "." +
                   b64u(json.dumps(claims, separators=(",", ":")).encode()))
        r, s = decode_dss_signature(self.key.sign(signing.encode(), ec.ECDSA(hashes.SHA256())))
        jwt = signing + "." + b64u(r.to_bytes(32, "big") + s.to_bytes(32, "big"))
        return f"vapid t={jwt}, k={self.public_b64}"


# ------------------------------------------------------------------ RFC 8291 encryption
def _hkdf_expand(prk: bytes, info: bytes, n: int) -> bytes:
    return hmac.new(prk, info + b"\x01", hashlib.sha256).digest()[:n]


def encrypt(plaintext: bytes, p256dh_b64: str, auth_b64: str, salt: bytes | None = None, server_key=None) -> bytes:
    """aes128gcm body for one push message (single record)."""
    ec, serialization, _, _, AESGCM = _ec()
    ua_pub_raw, auth = b64u_dec(p256dh_b64), b64u_dec(auth_b64)
    ua_pub = ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), ua_pub_raw)
    as_key = server_key or ec.generate_private_key(ec.SECP256R1())
    as_pub_raw = _raw_public(as_key.public_key())
    ecdh = as_key.exchange(ec.ECDH(), ua_pub)
    prk_key = hmac.new(auth, ecdh, hashlib.sha256).digest()
    ikm = _hkdf_expand(prk_key, b"WebPush: info\x00" + ua_pub_raw + as_pub_raw, 32)
    salt = salt or os.urandom(16)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    cek = _hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)
    nonce = _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12)
    rs = 4096
    if len(plaintext) + 1 + 16 > rs:
        raise PushError("message too long for one push record")
    ct = AESGCM(cek).encrypt(nonce, plaintext + b"\x02", None)
    return salt + struct.pack(">IB", rs, len(as_pub_raw)) + as_pub_raw + ct


def decrypt(body: bytes, ua_private, auth_b64: str) -> bytes:
    """Inverse of encrypt(), as the browser does it (used by the tests)."""
    ec, serialization, _, _, AESGCM = _ec()
    salt, (rs, idlen) = body[:16], struct.unpack(">IB", body[16:21])
    as_pub_raw, ct = body[21:21 + idlen], body[21 + idlen:]
    ua_pub_raw = _raw_public(ua_private.public_key())
    ecdh = ua_private.exchange(ec.ECDH(), ec.EllipticCurvePublicKey.from_encoded_point(ec.SECP256R1(), as_pub_raw))
    prk_key = hmac.new(b64u_dec(auth_b64), ecdh, hashlib.sha256).digest()
    ikm = _hkdf_expand(prk_key, b"WebPush: info\x00" + ua_pub_raw + as_pub_raw, 32)
    prk = hmac.new(salt, ikm, hashlib.sha256).digest()
    pt = AESGCM(_hkdf_expand(prk, b"Content-Encoding: aes128gcm\x00", 16)).decrypt(
        _hkdf_expand(prk, b"Content-Encoding: nonce\x00", 12), ct, None)
    return pt.rstrip(b"\x00")[:-1]


# ------------------------------------------------------------------ sender
class WebPushSender:
    def __init__(self, contact: str, vapid: Vapid | None = None, session: requests.Session | None = None):
        self.vapid = vapid or Vapid()
        self.contact = contact
        self.session = session or requests.Session()

    def send(self, sub: dict, data: dict, ttl_s: int = 86400, urgency: str = "high") -> int:
        body = encrypt(json.dumps(data, separators=(",", ":")).encode(), sub["p256dh"], sub["auth"])
        headers = {"Authorization": self.vapid.auth_header(sub["endpoint"], self.contact),
                   "Content-Encoding": "aes128gcm", "Content-Type": "application/octet-stream",
                   "TTL": str(ttl_s), "Urgency": urgency}
        for attempt in range(3):
            r = self.session.post(sub["endpoint"], data=body, headers=headers, timeout=20)
            if r.status_code in (200, 201, 202):
                return r.status_code
            if r.status_code in (429, 500, 502, 503) and attempt < 2:
                time.sleep(2 ** attempt * 2)
                continue
            raise PushError(f"push service HTTP {r.status_code}: {r.text[:200]}", r.status_code,
                            gone=r.status_code in (404, 410))
        raise PushError("push service: retries exhausted")
