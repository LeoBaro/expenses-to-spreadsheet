"""Enable Banking JWT bearer authentication.

Enable Banking authenticates each request with an RS256-signed JWT whose ``kid``
header is the registered application id and whose claims are fixed
(iss=enablebanking.com, aud=api.enablebanking.com). See the API quick-start.
"""

from __future__ import annotations

import time
from pathlib import Path

import jwt

_ISS = "enablebanking.com"
_AUD = "api.enablebanking.com"


class EnableBankingAuth:
    def __init__(
        self,
        application_id: str,
        private_key: str,
        *,
        ttl_seconds: int = 3600,
        _now=time.time,
    ) -> None:
        self._application_id = application_id
        self._private_key = private_key
        self._ttl_seconds = ttl_seconds
        self._now = _now
        self._token: str | None = None
        self._expires_at = 0.0

    @classmethod
    def from_key_file(cls, application_id: str, key_path: str | Path, **kwargs) -> "EnableBankingAuth":
        return cls(application_id, Path(key_path).read_text(), **kwargs)

    def bearer(self) -> str:
        """Return a valid JWT, minting a new one when the cached token is near expiry."""
        now = self._now()
        # Refresh a minute early to avoid clock-skew rejections.
        if self._token is not None and now < self._expires_at - 60:
            return self._token
        expires_at = now + self._ttl_seconds
        self._token = jwt.encode(
            {"iss": _ISS, "aud": _AUD, "iat": int(now), "exp": int(expires_at)},
            self._private_key,
            algorithm="RS256",
            headers={"typ": "JWT", "kid": self._application_id},
        )
        self._expires_at = expires_at
        return self._token
