"""Encrypted storage helper (development stub, not production cryptography)."""

from __future__ import annotations

import base64
import hashlib


class EncryptionLayer:
    """
    Lightweight encryption stub for local development.

    This is intentionally simple and must be replaced with an audited
    production encryption implementation.
    """

    def __init__(self, key_material: str) -> None:
        if not key_material:
            raise ValueError("key_material must not be empty")
        self._key = hashlib.sha256(key_material.encode("utf-8")).digest()

    def encrypt(self, plaintext: str | None) -> str | None:
        """Encrypt UTF-8 text and return URL-safe base64 payload."""
        if plaintext is None:
            return None
        raw = plaintext.encode("utf-8")
        cipher = bytes(value ^ self._key[idx % len(self._key)] for idx, value in enumerate(raw))
        return base64.urlsafe_b64encode(cipher).decode("ascii")

    def decrypt(self, ciphertext: str | None) -> str | None:
        """Decrypt URL-safe base64 payload back to UTF-8 text."""
        if ciphertext is None:
            return None
        cipher = base64.urlsafe_b64decode(ciphertext.encode("ascii"))
        plain = bytes(value ^ self._key[idx % len(self._key)] for idx, value in enumerate(cipher))
        return plain.decode("utf-8")
