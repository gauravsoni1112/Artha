"""Unit tests for PIIScanner — no external dependencies required."""

import pytest
from libs.privacy.pii_scanner import PIIScanner

scanner = PIIScanner()


@pytest.mark.parametrize("text,entity", [
    ("My PAN is ABCDE1234F", "IN_PAN"),
    ("PAN: ZZZZZ9999Z here", "IN_PAN"),
    ("Aadhaar: 2345 6789 0123", "IN_AADHAAR"),
    ("aadhaar 234567890123", "IN_AADHAAR"),
    ("Call +91 9876543210 now", "IN_PHONE"),
    ("mobile 9876543210", "IN_PHONE"),
    ("IFSC SBIN0001234", "IN_IFSC"),
    ("ifsc HDFC0000123", "IN_IFSC"),
    ("account 123456789012", "IN_ACCOUNT"),
])
def test_scan_detects_pii(text, entity):
    matches = scanner.scan(text)
    types = [m.entity_type for m in matches]
    assert entity in types, f"Expected {entity} in {types} for text: {text!r}"


@pytest.mark.parametrize("text", [
    "Your surplus is ₹45,000 this month.",
    "Monthly income bucket: 150000p",
    "Category: food_delivery",
    "Risk appetite: moderate",
    "2026-03",
])
def test_scan_clean_text(text):
    assert scanner.is_safe_for_cloud(text), f"False positive for: {text!r}"


def test_is_safe_for_cloud_false_on_pan():
    assert not scanner.is_safe_for_cloud("PAN ABCDE1234F balance ₹10,000")


def test_assert_safe_raises_with_context():
    with pytest.raises(ValueError, match="IN_PAN"):
        scanner.assert_safe_for_cloud("PAN ABCDE1234F", context="reflector prompt")


def test_assert_safe_passes_clean_text():
    scanner.assert_safe_for_cloud("User has surplus of ₹30,000 this month.")
