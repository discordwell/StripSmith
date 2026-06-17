"""Tests for the configuration loader and the Claude model defaults.

The model-ID tests are regression guards: the project previously shipped a
configured model (``claude-3-opus-20240229``) that Anthropic retired on
2026-01-05, plus an invalid in-code fallback (``claude-3-5-sonnet-20250514``).
Both made every analysis/breakdown call fail. These tests fail loudly if a
known-bad ID ever returns.
"""

import textwrap

import pytest

from src.utils.config import (
    Config,
    get_config,
    DEFAULT_LLM_MODEL,
    DEFAULT_LLM_MAX_TOKENS,
)

# IDs known to be retired or invalid — must never appear as a default.
RETIRED_OR_INVALID_MODELS = {
    "claude-3-opus-20240229",      # retired 2026-01-05
    "claude-3-5-sonnet-20250514",  # never a valid ID
    "claude-3-5-sonnet-20241022",  # retired 2025-10-28
    "claude-3-sonnet-20240229",    # retired
}


def test_dot_notation_get():
    cfg = get_config()
    assert cfg.get("image.size") == "1024x1024"
    assert cfg.get("layout.gutter_width") == 10


def test_missing_key_returns_default():
    cfg = get_config()
    assert cfg.get("does.not.exist") is None
    assert cfg.get("does.not.exist", "fallback") == "fallback"


def test_set_then_get_roundtrip():
    cfg = Config()
    cfg.set("image.quality", "hd")
    assert cfg.get("image.quality") == "hd"
    # Nested creation
    cfg.set("brand.new.key", 42)
    assert cfg.get("brand.new.key") == 42


def test_missing_config_file_is_tolerated(tmp_path):
    cfg = Config(config_path=tmp_path / "nope.yaml")
    assert cfg.get("anything") is None
    assert cfg.get("anything", "x") == "x"


def test_loads_custom_config(tmp_path):
    p = tmp_path / "c.yaml"
    p.write_text(textwrap.dedent("""\
        image:
          size: "512x512"
    """))
    cfg = Config(config_path=p)
    assert cfg.get("image.size") == "512x512"


def test_default_llm_model_is_not_retired():
    assert DEFAULT_LLM_MODEL not in RETIRED_OR_INVALID_MODELS
    assert DEFAULT_LLM_MODEL == "claude-opus-4-8"


def test_configured_llm_model_is_not_retired():
    """The shipped config must point at a live model."""
    configured = get_config().get("analysis.llm_model")
    assert configured is not None, "analysis.llm_model missing from config.yaml"
    assert configured not in RETIRED_OR_INVALID_MODELS, (
        f"config.yaml uses a retired/invalid model: {configured}"
    )


def test_max_output_tokens_default_is_sane():
    assert isinstance(DEFAULT_LLM_MAX_TOKENS, int)
    assert DEFAULT_LLM_MAX_TOKENS >= 4096
    assert get_config().get("analysis.max_output_tokens") == DEFAULT_LLM_MAX_TOKENS
