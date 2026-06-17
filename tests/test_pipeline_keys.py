"""Contract tests for API-key handling in the pipeline components.

These constructors take an explicit key or fall back to an environment variable,
and raise if neither is present. The hosted backend relies on the explicit-key
path (its environment has no keys), which is why api_wrapper must pass them.
Constructing the SDK clients with a dummy key performs no network I/O.
"""

import pytest

from src.analysis.analyzer import NarrativeAnalyzer
from src.panels.breakdown import PanelBreakdown
from src.assets.generator import ImageGenerator


def test_analyzer_uses_explicit_key():
    assert NarrativeAnalyzer(api_key="sk-ant-explicit").api_key == "sk-ant-explicit"


def test_analyzer_requires_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError):
        NarrativeAnalyzer()


def test_breakdown_uses_explicit_key():
    assert PanelBreakdown(api_key="sk-ant-explicit").api_key == "sk-ant-explicit"


def test_breakdown_requires_a_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(ValueError):
        PanelBreakdown()


def test_image_generator_uses_explicit_key():
    assert ImageGenerator(api_key="sk-openai-explicit").api_key == "sk-openai-explicit"


def test_image_generator_requires_a_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(ValueError):
        ImageGenerator()
