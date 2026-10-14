"""
tests/unit/test_auth.py — Unit tests for modules/auth.py

Tests password hashing, verification, constant-time compare, and the
lockout threshold logic without touching Streamlit session state.
"""
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from modules.auth import (
    _hash_password,
    _hash_password_legacy,
    _verify_password,
    _verify_password_constant_time,
    _DUMMY_STORED,
    _MAX_ATTEMPTS,
    _SESSION_TIMEOUT_HOURS,
)


class TestPasswordHashing:
    def test_pbkdf2_hash_is_deterministic(self):
        """Same password + salt must always produce the same hash."""
        h1 = _hash_password("secret", "mysalt")
        h2 = _hash_password("secret", "mysalt")
        assert h1 == h2

    def test_pbkdf2_hash_differs_with_different_password(self):
        h1 = _hash_password("password1", "salt")
        h2 = _hash_password("password2", "salt")
        assert h1 != h2

    def test_pbkdf2_hash_differs_with_different_salt(self):
        h1 = _hash_password("password", "salt1")
        h2 = _hash_password("password", "salt2")
        assert h1 != h2

    def test_pbkdf2_hash_has_prefix(self):
        h = _hash_password("x", "y")
        assert h.startswith("pbkdf2:")

    def test_legacy_hash_no_prefix(self):
        h = _hash_password_legacy("x", "y")
        assert not h.startswith("pbkdf2:")

    def test_legacy_hash_is_hex(self):
        h = _hash_password_legacy("password", "salt")
        assert all(c in "0123456789abcdef" for c in h)
        assert len(h) == 64  # SHA-256 hex

    def test_pbkdf2_and_legacy_differ(self):
        h_new = _hash_password("password", "salt")
        h_old = _hash_password_legacy("password", "salt")
        assert h_new != h_old


class TestVerifyPassword:
    def _make_stored(self, password: str, salt: str = "testsalt") -> str:
        """Build a stored 'salt$hash' string using the new PBKDF2 scheme."""
        return f"{salt}$" + _hash_password(password, salt)

    def _make_stored_legacy(self, password: str, salt: str = "testsalt") -> str:
        return f"{salt}$" + _hash_password_legacy(password, salt)

    def test_correct_password_verifies(self):
        stored = self._make_stored("correct_password")
        assert _verify_password("correct_password", stored) is True

    def test_wrong_password_fails(self):
        stored = self._make_stored("correct_password")
        assert _verify_password("wrong_password", stored) is False

    def test_empty_password_fails(self):
        stored = self._make_stored("correct_password")
        assert _verify_password("", stored) is False

    def test_legacy_hash_verifies(self):
        stored = self._make_stored_legacy("old_password")
        assert _verify_password("old_password", stored) is True

    def test_legacy_wrong_password_fails(self):
        stored = self._make_stored_legacy("old_password")
        assert _verify_password("wrong_password", stored) is False

    def test_malformed_stored_returns_false(self):
        assert _verify_password("anything", "no_dollar_sign_at_all") is False

    def test_empty_stored_returns_false(self):
        assert _verify_password("anything", "") is False


class TestConstantTimeVerify:
    def _stored(self, pw: str) -> str:
        return f"salt${_hash_password(pw, 'salt')}"

    def test_valid_credentials_accepted(self):
        assert _verify_password_constant_time("pass", self._stored("pass")) is True

    def test_wrong_password_rejected(self):
        assert _verify_password_constant_time("wrong", self._stored("pass")) is False

    def test_none_stored_rejected(self):
        """Unknown username — stored_or_none is None — must return False."""
        assert _verify_password_constant_time("any_password", None) is False

    def test_dummy_stored_is_well_formed(self):
        """_DUMMY_STORED must contain '$' so _verify_password doesn't raise."""
        assert "$" in _DUMMY_STORED


class TestConstants:
    def test_max_attempts_positive(self):
        assert _MAX_ATTEMPTS > 0

    def test_session_timeout_positive(self):
        assert _SESSION_TIMEOUT_HOURS > 0
