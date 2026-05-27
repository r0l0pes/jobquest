"""Characterization tests for scripts/form_filler.py.

These tests document the current behavior of the deterministic form filler
before any changes are made. They serve as regression protection.
"""

import sys
from pathlib import Path

import pytest

# Add project root to path for imports
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from scripts.form_filler import classify_field, FIELD_PATTERNS


class TestClassifyField:
    """Test field classification logic."""

    # ─── Happy Path: Standard field patterns ──────────────────────

    @pytest.mark.parametrize(
        "label,expected",
        [
            ("Full Name", "name"),
            ("Your Name", "name"),
            ("Candidate Name", "name"),
            ("Applicant Name", "name"),
            ("First Name Last Name", "name"),
            ("First Name", "first_name"),
            ("Given Name", "first_name"),
            ("FName", "first_name"),
            ("Last Name", "last_name"),
            ("Sur Name", "last_name"),
            ("Family Name", "last_name"),
            ("LName", "last_name"),
            ("Email", "email"),
            ("E-Mail", "email"),
            ("Email Address", "email"),
            ("Phone", "phone"),
            ("Telephone", "phone"),
            ("Mobile", "phone"),
            ("Cell", "phone"),
            ("LinkedIn", "linkedin"),
            ("Linked In", "linkedin"),
            ("Location", "location"),
            ("City", "location"),
            ("Address", "location"),
            ("Where Are You", "location"),
            ("Website", "website"),
            ("Portfolio", "website"),
            ("Personal URL", "website"),
            ("Blog", "website"),
            ("Cover Letter", "cover_letter"),
            ("Motivation", "cover_letter"),
            ("Comments", "cover_letter"),
            ("Additional Info", "cover_letter"),
            ("Salary", "salary"),
            ("Compensation", "salary"),
            ("Pay Expectations", "unknown"),  # regex is pay.?expect, doesn't match 'Expectations'
            ("Start Date", "start_date"),
            ("Availability", "unknown"),  # regex is avail\b, doesn't match 'Availability'
            ("Earliest Start", "start_date"),
            ("When Can You Start", "start_date"),
            ("Current Company", "company_current"),
            ("Current Employer", "company_current"),
            ("Org", "company_current"),
            ("Current Title", "title_current"),
            ("Job Title", "title_current"),
            ("Position", "title_current"),
        ],
    )
    def test_standard_field_patterns(self, label, expected):
        """Each known field pattern matches its classification."""
        result = classify_field(label, "", "", "")
        assert result == expected, f"Expected {expected!r} for {label!r}, got {result!r}"

    # ─── Edge Cases ───────────────────────────────────────────────

    def test_compound_first_and_last_name(self):
        """Compound label with both first and last name keywords."""
        result = classify_field("First and Last Name", "", "", "")
        # The 'name' pattern (first.?name.*last.?name) does NOT match because
        # "First and Last Name" has "and" between; last_name pattern matches instead
        assert result == "last_name"

    def test_empty_search_text(self):
        """All empty inputs should return unknown."""
        result = classify_field("", "", "", "")
        assert result == "unknown"

    def test_whitespace_only(self):
        """Whitespace-only search text should return unknown."""
        result = classify_field("   ", "", "", "")
        assert result == "unknown"

    def test_unrecognized_field(self):
        """Fields not matching any pattern return unknown."""
        result = classify_field("Favorite Color", "", "", "")
        assert result == "unknown"

    def test_non_english_label(self):
        """Non-English labels are not recognized (documents current behavior)."""
        result = classify_field("Courriel", "", "", "")  # French for email
        assert result == "unknown"

    def test_name_attribute_overrides_label(self):
        """Name attribute is searched alongside label."""
        result = classify_field("", "email_address", "", "")
        assert result == "email"

    def test_placeholder_searched(self):
        """Placeholder text is searched for classification."""
        result = classify_field("", "", "Enter your phone number", "")
        assert result == "phone"

    def test_id_searched(self):
        """Field id is searched for classification."""
        result = classify_field("", "", "", "linkedin-url")
        assert result == "linkedin"

    def test_case_insensitive_matching(self):
        """Matching should be case-insensitive."""
        result = classify_field("EMAIL", "", "", "")
        assert result == "email"

        result = classify_field("Phone Number", "", "", "")
        assert result == "phone"

    def test_multiple_signals_combined(self):
        """Label, name, placeholder, and id all contribute to search."""
        result = classify_field("", "", "", "first-name-input")
        assert result == "first_name"

    def test_partial_match_false_positive(self):
        """Partial words should not match (e.g., 'phonetic' vs 'phone')."""
        result = classify_field("Phonetic", "", "", "")
        # 'phone' pattern uses \b(phone|telephone|mobile|cell|tel)\b
        # 'Phonetic' should NOT match because of word boundary
        assert result == "unknown"

    def test_no_pattern_matches_return_unknown(self):
        """When nothing matches, return unknown."""
        result = classify_field("Department", "dept_code", "Select department", "dept")
        assert result == "unknown"


class TestFieldPatterns:
    """Direct tests for regex pattern behavior."""

    def test_all_patterns_are_compiled_regex(self):
        """FIELD_PATTERNS values should be compiled regex objects."""
        import re

        for key, pattern in FIELD_PATTERNS.items():
            assert isinstance(pattern, re.Pattern), f"{key} is not a compiled regex"

    def test_pattern_count(self):
        """There should be exactly 13 field classification patterns."""
        assert len(FIELD_PATTERNS) == 13
