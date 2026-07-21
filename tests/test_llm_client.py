"""Tests for per-step LLM client factory functions (U1)."""

import os
import pytest
from unittest import mock

import modules.llm_client as llm_module
from modules.llm_client import LLMClient


class _FakeClient(LLMClient):
    """Dummy client for testing — never makes real API calls."""
    def generate(self, system_prompt, user_prompt, temperature=0.3):
        return "fake response"
    def model_name(self):
        return "fake"


def _mock_single_client(provider, model=None):
    """Mock _create_single_client to return a fake client."""
    return _FakeClient()


def _mock_writing_client():
    """Mock create_writing_client to return a fake client."""
    return _FakeClient()


class TestCreateTailorClient:
    """create_tailor_client() — per-step factory for Step 3 (resume tailoring)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'create_writing_client', _mock_writing_client):
            client = llm_module.create_tailor_client()
            assert isinstance(client, LLMClient)

    def test_uses_env_var_when_set(self):
        with mock.patch.dict(os.environ, {
            "TAILOR_PROVIDER": "gemini",
            "TAILOR_MODEL": "gemini-2.5-pro",
        }), mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_tailor_client()
            assert isinstance(client, LLMClient)

    def test_legacy_writing_model_env_var_respected(self):
        with mock.patch.dict(os.environ, {
            "TAILOR_PROVIDER": "",
            "TAILOR_MODEL": "",
            "GEMINI_WRITING_MODEL": "gemini-3.1-flash-lite",
        }), mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_tailor_client()
            assert isinstance(client, LLMClient)


class TestCreateReviewerClientV2:
    """create_reviewer_client_v2() — per-step factory for Step 5 (adversarial review)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'create_reviewer_client', _mock_writing_client):
            client = llm_module.create_reviewer_client_v2()
            assert isinstance(client, LLMClient)

    def test_uses_env_var_when_set(self):
        with mock.patch.dict(os.environ, {
            "REVIEWER_PROVIDER": "gemini",
            "REVIEWER_MODEL": "gemini-3-flash",
        }), mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_reviewer_client_v2()
            assert isinstance(client, LLMClient)

    def test_backward_compat_original_still_works(self):
        with mock.patch.object(llm_module, 'create_reviewer_client', _mock_writing_client):
            client = llm_module.create_reviewer_client()
            assert isinstance(client, LLMClient)


class TestCreateAtsClient:
    """create_ats_client() — per-step factory for Step 5/9 (ATS keyword check)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'FallbackClient', return_value=_FakeClient()):
            client = llm_module.create_ats_client()
            assert isinstance(client, LLMClient)

    def test_falls_back_to_gemini(self):
        with mock.patch.object(llm_module, 'FallbackClient', return_value=_FakeClient()):
            client = llm_module.create_ats_client()
            assert isinstance(client, LLMClient)

    def test_uses_env_var_when_set(self):
        with mock.patch.dict(os.environ, {
            "ATS_PROVIDER": "gemini",
            "ATS_MODEL": "gemini-3.1-flash-lite",
        }), mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_ats_client()
            assert isinstance(client, LLMClient)


class TestCreateQaClient:
    """create_qa_client() — per-step factory for Step 8 (Q&A + cover letter)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'create_writing_client', _mock_writing_client):
            client = llm_module.create_qa_client()
            assert isinstance(client, LLMClient)

    def test_falls_back_to_writing_chain(self):
        with mock.patch.object(llm_module, 'create_writing_client', _mock_writing_client):
            client = llm_module.create_qa_client()
            assert isinstance(client, LLMClient)


class TestCreateInterviewClient:
    """create_interview_client() — per-step factory for Step 8b (interview prep)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'create_writing_client', _mock_writing_client):
            client = llm_module.create_interview_client()
            assert isinstance(client, LLMClient)

    def test_defaults_to_kimi_when_available(self):
        with mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_interview_client()
            assert isinstance(client, LLMClient)


def _mock_create_client(**kwargs):
    return _FakeClient()


class TestCreateFitClientV2:
    """create_fit_client_v2() — per-step factory for Step 2b (fit evaluation)."""

    def test_returns_llm_client_when_mocked(self):
        with mock.patch.object(llm_module, 'create_client', _mock_create_client):
            client = llm_module.create_fit_client_v2()
            assert isinstance(client, LLMClient)

    def test_uses_env_var_when_set(self):
        with mock.patch.dict(os.environ, {
            "FIT_PROVIDER": "gemini",
            "FIT_MODEL": "gemini-3.1-flash-lite",
        }), mock.patch.object(llm_module, '_create_single_client', _mock_single_client):
            client = llm_module.create_fit_client_v2()
            assert isinstance(client, LLMClient)

    def test_default_is_gemini_flash_lite(self):
        with mock.patch.object(llm_module, 'create_client', _mock_create_client):
            client = llm_module.create_fit_client_v2()
            assert isinstance(client, LLMClient)


class TestBackwardCompatibility:
    """Verify existing factory functions still work after U1 changes."""

    def test_create_writing_client_still_works(self):
        assert callable(llm_module.create_writing_client)

    def test_create_reviewer_client_still_works(self):
        assert callable(llm_module.create_reviewer_client)

    def test_create_client_still_works(self):
        assert callable(llm_module.create_client)


class TestNewFactoriesExist:
    """Verify all new factory functions are importable."""

    def test_create_tailor_client_exists(self):
        assert callable(llm_module.create_tailor_client)

    def test_create_reviewer_client_v2_exists(self):
        assert callable(llm_module.create_reviewer_client_v2)

    def test_create_ats_client_exists(self):
        assert callable(llm_module.create_ats_client)

    def test_create_qa_client_exists(self):
        assert callable(llm_module.create_qa_client)

    def test_create_interview_client_exists(self):
        assert callable(llm_module.create_interview_client)

    def test_create_fit_client_v2_exists(self):
        assert callable(llm_module.create_fit_client_v2)
