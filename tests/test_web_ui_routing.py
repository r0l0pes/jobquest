"""UI/config regression tests for the retired global writing-model selector.

The Pipeline UI used to expose a global "Writing model (steps 3, 6, 8)" radio
(WITH ``Gemini`` / ``Groq`` / ``SambaNova`` / ``OpenCode Kimi`` options) plus an
"ATS provider" radio, and wrote the retired ``WRITING_PROVIDER`` /
``WRITING_MODEL`` / ``GEMINI_WRITING_MODEL`` / ``LLM_PROVIDER`` env vars.

B.1.5 made routing explicit and per stage (``modules.llm_client.STAGE_ROUTES``),
so those controls must not come back. These tests assert the UI now shows a
read-only, stage-specific routing panel instead.

Run with: pytest tests/test_web_ui_routing.py -v
"""

import inspect
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import web_ui  # noqa: E402
from modules.llm_client import STAGE_ROUTES  # noqa: E402

# Every legacy option/label the retired selector exposed.
LEGACY_SELECTOR_STRINGS = (
    "Writing model",
    "ATS provider",
    "Gemini",
    "Groq",
    "SambaNova",
    "Kimi",
    "OpenCode",
    "DeepSeek V3.2",
    "gemini-2.5-pro",
    "gemini-3.1-flash-lite",
    "llama-3.3-70b",
    "llama-3.1-405b",
    "qwen3.5-397b",
    "deepseek-chat",
    "kimi-k2.6",
)


def _component_text(app):
    """Collect label, choices and string values from every Gradio component."""
    text_parts = []
    for component in app.blocks.values():
        label = getattr(component, "label", None)
        if label:
            text_parts.append(str(label))
        choices = getattr(component, "choices", None) or []
        for choice in choices:
            text_parts.append(str(choice))
        value = getattr(component, "value", None)
        if isinstance(value, str):
            text_parts.append(value)
    return text_parts


class TestLegacySelectorIsGone:
    """The retired global model/provider selectors must not be rendered."""

    def test_no_legacy_model_selector_in_ui(self):
        app = web_ui.create_ui()
        haystack = "\n".join(_component_text(app))
        for legacy in LEGACY_SELECTOR_STRINGS:
            assert legacy not in haystack, f"legacy UI string still rendered: {legacy}"

    def test_application_form_has_no_model_or_provider_component(self):
        with web_ui.gr.Blocks():
            form = web_ui.create_app_form(1)
        labels = [str(getattr(c, "label", "") or "") for c in form]
        assert not any("model" in label.lower() for label in labels)
        assert not any("provider" in label.lower() for label in labels)
        # The resume-variant selector is not a model selector and must survive.
        radios = [c for c in form if isinstance(c, web_ui.gr.Radio)]
        assert radios, "resume variant radio should still exist"
        assert all(getattr(r, "label", "") == "Resume variant" for r in radios)


class TestRetiredEnvWritesAreGone:
    """No UI code sets or forwards the retired global-writing env vars."""

    def test_run_pipeline_never_sets_retired_env_vars(self):
        source = inspect.getsource(web_ui._run_pipeline)
        for retired in web_ui.RETIRED_MODEL_ENV:
            assert f'full_env["{retired}"] =' not in source
            assert f"full_env['{retired}'] =" not in source

    def test_run_pipeline_scrubs_inherited_retired_env_vars(self):
        source = inspect.getsource(web_ui._run_pipeline)
        assert "RETIRED_MODEL_ENV" in source
        assert "full_env.pop(retired, None)" in source

    @pytest.mark.parametrize("callback", ["_run_pipeline", "run_slot_1", "run_slot_2", "run_slot_3"])
    def test_callbacks_accept_no_model_or_provider(self, callback):
        params = set(inspect.signature(getattr(web_ui, callback)).parameters)
        assert "provider" not in params
        assert "writing_model" not in params


class TestRoutingPanel:
    """The read-only panel must show the ACTIVE stage routing, from STAGE_ROUTES."""

    def test_panel_lists_every_stage_primary_and_fallback(self):
        display = web_ui.get_llm_routing_display()
        assert STAGE_ROUTES, "STAGE_ROUTES must be importable for the panel"
        for stage, route in STAGE_ROUTES.items():
            assert route["model"] in display, stage
            if route.get("fallback_model"):
                assert route["fallback_model"] in display, stage

    def test_panel_is_openrouter_and_stage_specific(self):
        display = web_ui.get_llm_routing_display()
        assert "OpenRouter" in display
        assert "per stage" in display
        assert "no global writing-model selector" in display
        assert "no per-application model choice" in display

    def test_panel_reflects_stage_env_overrides(self, monkeypatch):
        monkeypatch.setenv("TAILOR_MODEL", "vendor/override-slug")
        monkeypatch.setenv("TAILOR_FALLBACK_MODEL", "vendor/override-fallback")
        display = web_ui.get_llm_routing_display()
        assert "vendor/override-slug" in display
        assert "vendor/override-fallback" in display

    def test_panel_degrades_gracefully_without_routing_metadata(self, monkeypatch):
        monkeypatch.setattr(web_ui, "STAGE_ROUTES", {})
        display = web_ui.get_llm_routing_display()
        assert "read-only" in display
        assert "OpenRouter" in display

    def test_routing_panel_is_rendered_in_the_ui(self):
        app = web_ui.create_ui()
        values = [
            str(getattr(c, "value", "") or "")
            for c in app.blocks.values()
            if isinstance(getattr(c, "value", None), str)
        ]
        assert any("LLM Routing (read-only)" in value for value in values)
