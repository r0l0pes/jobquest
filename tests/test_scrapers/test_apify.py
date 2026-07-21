"""Tests for the Apify JobStream adapter."""

import os
import json
from unittest.mock import patch, MagicMock

import pytest

from modules.scrapers.sources.apify_jobstream import ApifyJobStreamAdapter


class TestApifyCanResolve:
    """Tests for ApifyJobStreamAdapter.can_resolve()."""

    def test_greenhouse_url_matches(self):
        """Greenhouse board URL should resolve when Apify key is present."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            url = "https://boards.greenhouse.io/stripe/jobs/123"
            assert adapter.can_resolve(url)

    def test_lever_url_matches(self):
        """Lever job URL should resolve when Apify key is present."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            url = "https://jobs.lever.co/uber/abc-123"
            assert adapter.can_resolve(url)

    def test_ashby_url_matches(self):
        """Ashby job URL should resolve when Apify key is present."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            url = "https://jobs.ashbyhq.com/ramp/xyz-456"
            assert adapter.can_resolve(url)

    def test_unknown_url_does_not_match(self):
        """Non-ATS URL should not resolve."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            url = "https://www.linkedin.com/jobs/view/123"
            assert not adapter.can_resolve(url)

    def test_no_api_key_does_not_match(self):
        """Without APIFY_API_KEY, no URLs should resolve."""
        with patch.dict(os.environ, clear=True):
            adapter = ApifyJobStreamAdapter()
            url = "https://boards.greenhouse.io/stripe/jobs/123"
            assert not adapter.can_resolve(url)

    def test_priority_is_between_ats_and_stealth(self):
        """Apify adapter should be priority 20 (between ATS=10 and stealth=30)."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            assert adapter.priority == 20


class TestApifyFetch:
    """Tests for ApifyJobStreamAdapter.fetch()."""

    GREENHOUSE_DATA = [
        {
            "title": "Senior Product Manager",
            "company": "Stripe",
            "description": "We are looking for a Senior PM...\n\n",
            "url": "https://boards.greenhouse.io/stripe/jobs/123",
            "location": "Remote, US",
            "department": "Product",
            "employment_type": "full_time",
        }
    ]

    def _mock_apify_responses(self, job_data, run_id="run_123"):
        """Set up mock responses for Apify API calls.

        Returns a tuple of (mock_post, mock_get) configured for:
        1. POST /acts/brebiv~jobstream/runs → 201 with run_id
        2. GET /actor-runs/{run_id} → 200 with SUCCEEDED status (dict)
        3. GET /actor-runs/{run_id}/dataset/items → 200 with job_data (list)
        """
        from unittest.mock import patch, MagicMock

        mock_post = MagicMock()
        mock_run_resp = MagicMock()
        mock_run_resp.status_code = 201
        mock_run_resp.json.return_value = {"data": {"id": run_id}}
        mock_post.return_value = mock_run_resp

        mock_get = MagicMock()

        def get_side_effect(url, *args, **kwargs):
            mock_resp = MagicMock()
            mock_resp.status_code = 200
            if "/dataset/items" in url:
                mock_resp.json.return_value = job_data
            else:
                # status endpoint returns dict with "data"
                mock_resp.json.return_value = {"data": {"status": "SUCCEEDED"}}
            return mock_resp

        mock_get.side_effect = get_side_effect

        return mock_post, mock_get

    @patch.dict(os.environ, {"APIFY_API_KEY": "test_key"})
    def test_fetch_greenhouse_happy_path(self):
        """Apify JobStream adapter returns normalized JobPost for a Greenhouse URL."""
        mock_post, mock_get = self._mock_apify_responses(self.GREENHOUSE_DATA)

        with patch("modules.scrapers.sources.apify_jobstream.requests.post", mock_post):
            with patch("modules.scrapers.sources.apify_jobstream.requests.get", mock_get):
                adapter = ApifyJobStreamAdapter()
                result = adapter.fetch("https://boards.greenhouse.io/stripe/jobs/123")

                assert result["source"] == "apify"
                assert result["title"] == "Senior Product Manager"
                assert result["company"] == "Stripe"
                assert "looking for a Senior PM" in result["description"]
                assert result["url"] == "https://boards.greenhouse.io/stripe/jobs/123"

    @patch.dict(os.environ, {"APIFY_API_KEY": "test_key"})
    def test_fetch_lever_happy_path(self):
        """Apify JobStream returns job for a Lever URL."""
        lever_data = [
            {
                "title": "Growth PM",
                "company": "Uber",
                "description": "Join Uber as a Growth PM...",
                "url": "https://jobs.lever.co/uber/abc-123",
                "location": "Berlin, Germany",
                "department": "Growth",
            }
        ]
        mock_post, mock_get = self._mock_apify_responses(lever_data, run_id="run_abc")

        with patch("modules.scrapers.sources.apify_jobstream.requests.post", mock_post):
            with patch("modules.scrapers.sources.apify_jobstream.requests.get", mock_get):
                adapter = ApifyJobStreamAdapter()
                result = adapter.fetch("https://jobs.lever.co/uber/abc-123")

                assert result["source"] == "apify"
                assert result["title"] == "Growth PM"
                assert result["company"] == "Uber"

    @patch("modules.scrapers.sources.apify_jobstream.requests.post")
    def test_fetch_fallback_to_direct_api(self, mock_post):
        """When Apify fails (no API key), adapter should raise for fallback."""
        # Simulate Apify returning no data (missing key scenario at runtime)
        mock_run_resp = MagicMock()
        mock_run_resp.status_code = 401
        mock_run_resp.text = "Unauthorized"
        mock_post.return_value = mock_run_resp

        with patch.dict(os.environ, {"APIFY_API_KEY": "bad_key"}):
            adapter = ApifyJobStreamAdapter()
            with pytest.raises(RuntimeError, match="Apify JobStream"):
                adapter.fetch("https://boards.greenhouse.io/stripe/jobs/123")

    def test_fetch_no_data_returns_empty(self):
        """When Apify returns empty dataset, adapter returns minimal result."""
        # This test verifies that even without mock on the real endpoint,
        # the adapter handles gracefully. In practice, without APIFY_API_KEY
        # set, can_resolve returns False, so fetch shouldn't be called.
        # This is a structural test of the fallback path.
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            # We patch can_resolve to bypass the key check for testing
            with patch.object(adapter, "can_resolve", return_value=True):
                with patch.object(adapter, "_call_apify", return_value=[]):
                    result = adapter.fetch("https://boards.greenhouse.io/stripe/jobs/123")
                    assert result["source"] == "apify"
                    assert result["title"] == ""
                    assert result["url"] == "https://boards.greenhouse.io/stripe/jobs/123"

    def test_ats_type_extraction(self):
        """_extract_ats_type correctly identifies ATS from URL patterns."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()

            assert adapter._extract_ats_type("https://boards.greenhouse.io/stripe/jobs/123") == "greenhouse"
            assert adapter._extract_ats_type("https://job-boards.eu.greenhouse.io/company/jobs/456") == "greenhouse"
            assert adapter._extract_ats_type("https://jobs.lever.co/uber/abc") == "lever"
            assert adapter._extract_ats_type("https://jobs.ashbyhq.com/ramp/xyz") == "ashby"
            assert adapter._extract_ats_type("https://apply.workable.com/company/j/abc") is None
            assert adapter._extract_ats_type("https://example.com/job/123") is None

    def test_company_extraction(self):
        """_extract_company_from_url pulls correct company name."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()

            assert adapter._extract_company_from_url("https://boards.greenhouse.io/stripe/jobs/123") == "stripe"
            assert adapter._extract_company_from_url("https://jobs.lever.co/uber/abc") == "uber"
            assert adapter._extract_company_from_url("https://jobs.ashbyhq.com/ramp/xyz") == "ramp"
            assert adapter._extract_company_from_url("https://example.com/job/123") is None

    def test_job_id_extraction(self):
        """_extract_job_id pulls job identifier from URL."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()

            assert adapter._extract_job_id("https://boards.greenhouse.io/stripe/jobs/12345") == "12345"
            assert adapter._extract_job_id("https://jobs.lever.co/uber/abc-def-ghi") == "abc-def-ghi"
            assert adapter._extract_job_id("https://jobs.ashbyhq.com/ramp/xyz-789") == "xyz-789"

    def test_job_id_extraction_returns_none_when_missing(self):
        """_extract_job_id returns None when no job ID found."""
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            adapter = ApifyJobStreamAdapter()
            assert adapter._extract_job_id("https://boards.greenhouse.io/stripe") is None


class TestApifyMatchJob:
    """Tests for the _match_job_by_url method."""

    def setup_method(self):
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            self.adapter = ApifyJobStreamAdapter()
        self.jobs = [
            {"title": "PM", "url": "https://boards.greenhouse.io/stripe/jobs/111", "company": "Stripe"},
            {"title": "Eng", "url": "https://boards.greenhouse.io/stripe/jobs/222", "company": "Stripe"},
        ]

    def test_matches_by_job_id(self):
        """Matching by job ID returns the correct listing."""
        result = self.adapter._match_job_by_url(self.jobs, "https://boards.greenhouse.io/stripe/jobs/111")
        assert result["title"] == "PM"

    def test_matches_by_url_substring(self):
        """Falls back to URL substring match when no exact ID match."""
        result = self.adapter._match_job_by_url(self.jobs, "https://boards.greenhouse.io/stripe/jobs/111?source=linkedin")
        assert result["title"] == "PM"

    def test_no_match_returns_first(self):
        """When no job matches, returns first job as best guess."""
        result = self.adapter._match_job_by_url(self.jobs, "https://boards.greenhouse.io/stripe/jobs/999")
        assert result["title"] == "PM"

    def test_empty_list_returns_none(self):
        """Empty job list returns None."""
        result = self.adapter._match_job_by_url([], "https://boards.greenhouse.io/stripe/jobs/123")
        assert result is None


class TestApifyNormalize:
    """Tests for _normalize_job_post method."""

    def setup_method(self):
        with patch.dict(os.environ, {"APIFY_API_KEY": "test_key"}):
            self.adapter = ApifyJobStreamAdapter()

    def test_normalize_populates_all_fields(self):
        """_normalize_job_post maps all available fields."""
        raw = {
            "title": "Senior PM",
            "company": "Stripe",
            "description": "<p>Job description</p>",
            "url": "https://boards.greenhouse.io/stripe/jobs/123",
            "location": "Remote, US",
            "department": "Product",
            "employment_type": "full_time",
        }
        result = self.adapter._normalize_job_post(raw)
        assert result["title"] == "Senior PM"
        assert result["company"] == "Stripe"
        assert result["description"] == "Job description"
        assert result["source"] == "apify"
        assert result["questions"] == []

    def test_normalize_handles_html_description(self):
        """Strips HTML tags from description."""
        raw = {
            "title": "PM",
            "company": "Co",
            "description": "<h2>About the role</h2><p>We need a <strong>great</strong> PM</p>",
            "url": "https://example.com/job/1",
        }
        result = self.adapter._normalize_job_post(raw)
        assert "**" not in result["description"]  # tags stripped
        assert "great" in result["description"]
        assert "About the role" in result["description"]

    def test_normalize_handles_missing_fields(self):
        """Missing optional fields don't crash."""
        raw = {"title": "PM", "company": "Co", "url": "https://example.com/job/1"}
        result = self.adapter._normalize_job_post(raw)
        assert result["description"] == ""
        assert result["questions"] == []

    def test_normalize_truncates_long_descriptions(self):
        """Descriptions longer than 20000 chars should be truncated."""
        raw = {
            "title": "PM",
            "company": "Co",
            "description": "X" * 30000,
            "url": "https://example.com/job/1",
        }
        result = self.adapter._normalize_job_post(raw)
        assert len(result["description"]) <= 20000
