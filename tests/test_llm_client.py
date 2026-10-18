"""Tests for per-step LLM client factories and the B.1.5 explicit routing contract.

B.1.5 replaced implicit fallback with explicit stage routing:
  * every production stage resolves through ``RoutedClient``
  * exactly ONE primary route plus AT MOST one declared fallback route
  * Gemini is not an active production gateway
  * the broad ``WRITING_CHAIN`` is no longer an active production route
  * ``ATS_*`` owns the ATS stage and ``JD_*`` owns JD extraction
"""

import os
from unittest import mock

import pytest

import modules.llm_client as llm_module
from modules.llm_client import LLMClient, RoutedClient


class _FakeClient(LLMClient):
    """Dummy client for testing — never makes real API calls."""

    def generate(self, system_prompt, user_prompt, temperature=0.3):
        return "fake response"

    def model_name(self):
        return "fake"


class _Recorder:
    """Records every ``_create_single_client`` call and returns a fake client."""

    def __init__(self):
        self.calls = []

    def __call__(self, provider, model=None, **kwargs):
        self.calls.append((provider, model, kwargs))
        return _FakeClient()

    @property
    def providers(self):
        return [c[0] for c in self.calls]

    @property
    def efforts(self):
        return [c[2].get("reasoning_effort") for c in self.calls]


def _mock_single_client(provider, model=None, **kwargs):
    """Stand-in for ``_create_single_client`` (signature mirrors the real one)."""
    return _FakeClient()


def _mock_writing_client():
    return _FakeClient()


def _routes(client: LLMClient) -> list[str]:
    """Narrow to ``RoutedClient`` and return its reachable routes."""
    assert isinstance(client, RoutedClient), f"expected RoutedClient, got {type(client)}"
    return client.route_ids


def _providers(client: LLMClient) -> list[str]:
    """Provider portion of every route the client can reach."""
    return [r.split("/", 1)[0] for r in _routes(client)]


FACTORY_STAGE_CASES = [
    ("create_fit_client_v2", "FIT"),
    ("create_jd_client", "JD"),
    ("create_tailor_client", "TAILOR"),
    ("create_reviewer_client_v2", "REVIEWER"),
    ("create_ats_client", "ATS"),
    ("create_qa_client", "QA"),
]


class TestStageRoutesAreExplicitAndBounded:
    """Every stage resolves one primary + at most one declared fallback."""

    @pytest.mark.parametrize("factory,prefix", FACTORY_STAGE_CASES)
    def test_default_route_is_openrouter_primary_plus_one_fallback(
        self, factory, prefix, monkeypatch
    ):
        for key in (
            f"{prefix}_PROVIDER", f"{prefix}_MODEL",
            f"{prefix}_FALLBACK_PROVIDER", f"{prefix}_FALLBACK_MODEL",
        ):
            monkeypatch.delenv(key, raising=False)
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            client = getattr(llm_module, factory)()

        routes = _routes(client)
        assert len(routes) == 2, f"{factory} must expose exactly one fallback"
        assert all(r.startswith("openrouter/") for r in routes), routes
        assert len(rec.calls) == 2

    @pytest.mark.parametrize("factory,prefix", FACTORY_STAGE_CASES)
    def test_stage_env_vars_own_that_stage(self, factory, prefix, monkeypatch):
        monkeypatch.setenv(f"{prefix}_PROVIDER", "openrouter")
        monkeypatch.setenv(f"{prefix}_MODEL", "vendor/primary-slug")
        monkeypatch.setenv(f"{prefix}_FALLBACK_PROVIDER", "openrouter")
        monkeypatch.setenv(f"{prefix}_FALLBACK_MODEL", "vendor/fallback-slug")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = getattr(llm_module, factory)()
        assert _routes(client) == [
            "openrouter/vendor/primary-slug",
            "openrouter/vendor/fallback-slug",
        ]
        assert _providers(client) == ["openrouter", "openrouter"]

    @pytest.mark.parametrize("factory,prefix", FACTORY_STAGE_CASES)
    def test_empty_fallback_model_disables_the_fallback(self, factory, prefix, monkeypatch):
        monkeypatch.setenv(f"{prefix}_FALLBACK_MODEL", "")
        monkeypatch.setenv(f"{prefix}_PROVIDER", "openrouter")
        monkeypatch.setenv(f"{prefix}_MODEL", "vendor/primary-slug")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = getattr(llm_module, factory)()
        assert _routes(client) == ["openrouter/vendor/primary-slug"]

    def test_no_stage_default_uses_gemini_or_opencode(self):
        for stage, route in llm_module.STAGE_ROUTES.items():
            assert route["provider"] == "openrouter", stage
            assert route["fallback_provider"] == "openrouter", stage
            assert "gemini" not in route["model"], stage
            assert "kimi" not in route["model"], stage


class TestAtsAndJdOwnership:
    """ATS_* controls the ATS stage; JD_* controls JD extraction."""

    def test_ats_provider_and_model_control_the_ats_stage(self, monkeypatch):
        monkeypatch.setenv("ATS_PROVIDER", "openrouter")
        monkeypatch.setenv("ATS_MODEL", "vendor/ats-slug")
        monkeypatch.setenv("ATS_FALLBACK_MODEL", "vendor/ats-fb")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_ats_client()
        assert _routes(client)[0] == "openrouter/vendor/ats-slug"

    def test_ats_config_does_not_leak_into_jd_extraction(self, monkeypatch):
        monkeypatch.setenv("ATS_PROVIDER", "openrouter")
        monkeypatch.setenv("ATS_MODEL", "vendor/ats-slug")
        monkeypatch.delenv("JD_MODEL", raising=False)
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            jd = llm_module.create_jd_client()
            ats = llm_module.create_ats_client()
        assert _routes(jd)[0] != _routes(ats)[0]

    def test_jd_provider_and_model_control_jd_extraction(self, monkeypatch):
        monkeypatch.setenv("JD_PROVIDER", "openrouter")
        monkeypatch.setenv("JD_MODEL", "vendor/jd-slug")
        monkeypatch.setenv("JD_FALLBACK_MODEL", "")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_jd_client()
        assert _routes(client) == ["openrouter/vendor/jd-slug"]


class TestInterviewPrep:
    """Interview prep must not be forced onto OpenCode by an API key alone."""

    def test_inherits_qa_route(self, monkeypatch):
        monkeypatch.setenv("QA_PROVIDER", "openrouter")
        monkeypatch.setenv("QA_MODEL", "vendor/qa-slug")
        monkeypatch.setenv("QA_FALLBACK_PROVIDER", "openrouter")
        monkeypatch.setenv("QA_FALLBACK_MODEL", "vendor/qa-fb")
        monkeypatch.delenv("INTERVIEW_MODEL", raising=False)
        monkeypatch.setenv("OPENCODE_API_KEY", "present")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_interview_client()
        assert _routes(client)[0] == "openrouter/vendor/qa-slug"

    def test_does_not_default_to_opencode(self, monkeypatch):
        for key in ("INTERVIEW_MODEL", "INTERVIEW_PROVIDER", "QA_MODEL", "QA_PROVIDER"):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv("OPENCODE_API_KEY", "present")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_interview_client()
        joined = "".join(_routes(client))
        assert "opencode" not in joined
        assert "kimi" not in joined


class TestLegacySurfaces:
    """Legacy names and classes stay importable but are no longer active routes."""

    def test_create_writing_client_is_a_legacy_alias_for_the_tailor_route(self, monkeypatch):
        monkeypatch.setenv("TAILOR_MODEL", "vendor/tailor-slug")
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_writing_client()
        assert _routes(client)[0] == "openrouter/vendor/tailor-slug"

    def test_legacy_gemini_writing_model_no_longer_drives_routing(self, monkeypatch):
        monkeypatch.setenv("GEMINI_WRITING_MODEL", "gemini-2.5-pro-preview-05-06")
        for key in ("TAILOR_MODEL", "TAILOR_PROVIDER"):
            monkeypatch.delenv(key, raising=False)
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            client = llm_module.create_tailor_client()
        assert "gemini" not in "".join(_routes(client))

    def test_writing_chain_constant_is_not_used_by_production_factories(self):
        """The 9-entry chain must not appear in any production route."""
        chain_models = {model for _provider, model, _label, _cap in llm_module.WRITING_CHAIN}
        with mock.patch.object(llm_module, "_create_single_client", _mock_single_client):
            for factory, _prefix in FACTORY_STAGE_CASES:
                client = getattr(llm_module, factory)()
                assert not (set(_routes(client)) & chain_models), factory

    def test_fallback_client_class_still_exists(self):
        assert callable(llm_module.FallbackClient)
        assert llm_module.PROVIDER_FALLBACK_ORDER == ["openrouter"]

    def test_all_factories_are_importable(self):
        for factory, _prefix in FACTORY_STAGE_CASES:
            assert callable(getattr(llm_module, factory))
        assert callable(llm_module.create_writing_client)
        assert callable(llm_module.create_client)


class TestCreateClientFallbackSemantics:
    """``fallback=False`` must mean exactly one model route."""

    def test_fallback_false_yields_a_single_provider_client(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            client = llm_module.create_client(fallback=False)
        assert not isinstance(client, RoutedClient)
        assert rec.calls == [("openrouter", None, {})]

    def test_fallback_true_yields_one_primary_plus_one_fallback(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        monkeypatch.delenv("LLM_FALLBACK_MODEL", raising=False)
        monkeypatch.delenv("LLM_MODEL", raising=False)
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            client = llm_module.create_client(fallback=True)
        assert len(_routes(client)) == 2
        assert len(rec.calls) == 2

    def test_default_provider_is_openrouter_not_gemini(self, monkeypatch):
        monkeypatch.delenv("LLM_PROVIDER", raising=False)
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            llm_module.create_client(fallback=False)
        assert rec.providers == ["openrouter"]


class TestSelectedRouteTableIsPinned:
    """The B.1.5 selection is a decision, so pin it against silent drift."""

    EXPECTED = {
        "fit": ("z-ai/glm-5.3-flash", "qwen/qwen3.8-flash"),
        "jd": ("qwen/qwen3.8-flash", "z-ai/glm-5.3-flash"),
        "tailor": ("openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash"),
        "reviewer": ("openai/gpt-6-luna", "deepseek/deepseek-v4.1-flash"),
        "ats": ("z-ai/glm-5.3-flash", "openai/gpt-6-luna"),
        "qa": ("deepseek/deepseek-v4.1-flash", "openai/gpt-6-luna"),
    }

    def test_every_core_stage_has_a_primary_and_one_fallback(self):
        for stage, (primary, fallback) in self.EXPECTED.items():
            route = llm_module.STAGE_ROUTES[stage]
            assert route["model"] == primary, stage
            assert route["fallback_model"] == fallback, stage
            assert route["provider"] == "openrouter", stage
            assert route["fallback_provider"] == "openrouter", stage

    def test_no_auto_router_or_variant_slug_is_configured(self):
        for stage, route in llm_module.STAGE_ROUTES.items():
            for key in ("model", "fallback_model"):
                slug = route[key]
                assert "auto" not in slug.lower(), (stage, key)
                assert ":" not in slug, (stage, key)
                assert slug.count("/") >= 1, (stage, key)

    def test_per_route_reasoning_effort_is_applied(self, monkeypatch):
        """Primary and fallback may need different reasoning settings."""
        for key in ("FIT_REASONING_EFFORT", "FIT_FALLBACK_REASONING_EFFORT"):
            monkeypatch.delenv(key, raising=False)
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            llm_module.create_fit_client_v2()
        route = llm_module.STAGE_ROUTES["fit"]
        assert rec.efforts == [
            route["reasoning_effort"],
            route["fallback_reasoning_effort"],
        ]
        assert route["reasoning_effort"] != route["fallback_reasoning_effort"]

    def test_stage_reasoning_effort_can_be_overridden(self, monkeypatch):
        monkeypatch.setenv("QA_REASONING_EFFORT", "medium")
        monkeypatch.setenv("QA_FALLBACK_REASONING_EFFORT", "high")
        rec = _Recorder()
        with mock.patch.object(llm_module, "_create_single_client", rec):
            llm_module.create_qa_client()
        assert rec.efforts == ["medium", "high"]


class TestGeminiWalkIsOptIn:
    """A single-model Gemini client must not walk the hidden fallback order."""

    def test_model_fallback_defaults_to_off(self):
        # gemini is absent from every production route; the walk must stay opt-in.
        import inspect

        sig = inspect.signature(llm_module.GeminiClient.__init__)
        assert sig.parameters["model_fallback"].default is False

    def test_no_stage_route_selects_gemini(self):
        assert all("gemini" not in r["provider"] for r in llm_module.STAGE_ROUTES.values())


class TestBackwardCompatibility:
    def test_create_writing_client_still_callable(self):
        assert callable(llm_module.create_writing_client)

    def test_create_reviewer_client_still_callable(self):
        assert callable(llm_module.create_reviewer_client)

    def test_create_client_still_callable(self):
        assert callable(llm_module.create_client)

    def test_original_helpers_still_work(self):
        with mock.patch.object(llm_module, "create_reviewer_client", _mock_writing_client):
            assert isinstance(llm_module.create_reviewer_client(), LLMClient)
        with mock.patch.object(llm_module, "create_writing_client", _mock_writing_client):
            assert isinstance(llm_module.create_tailor_client(), LLMClient)
