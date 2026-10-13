"""Fixtures for the offline MockLLMClient. First attempt is deliberately flawed to exercise the review loop."""

FLAWED_IMPL = r'''def is_valid_email(email):
    """Naive (flawed) check."""
    return "@" in email and "." in email
'''

FIXED_IMPL = r'''"""Small, dependency-free email address validator (pragmatic subset of RFC 5322)."""
import re

_LOCAL = re.compile(r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(?:\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*$")
_LABEL = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")


def is_valid_email(email: object) -> bool:
    """Return True if `email` looks like a valid address. Never raises."""
    if not isinstance(email, str) or len(email) > 254:
        return False
    local, sep, domain = email.rpartition("@")
    if not sep or not local or len(local) > 64 or not domain:
        return False
    if not _LOCAL.match(local):
        return False
    labels = domain.split(".")
    if len(labels) < 2 or not all(_LABEL.match(label) for label in labels):
        return False
    return labels[-1].isalpha() and len(labels[-1]) >= 2
'''

TESTS = r'''import pytest

from email_validator_util import is_valid_email


@pytest.mark.parametrize("email", ["user@example.com", "first.last+tag@sub.example.co.uk", "a_b@x-y.org"])
def test_valid_addresses(email):
    assert is_valid_email(email) is True


@pytest.mark.parametrize(
    "email",
    ["", "plainaddress", "@example.com", "user@", "user@@example.com", "user@example",
     "user..name@example.com", "user@-example.com", "user name@example.com", "user@example.c0m", None, 42],
)
def test_invalid_addresses(email):
    assert is_valid_email(email) is False
'''
