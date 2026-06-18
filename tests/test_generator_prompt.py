"""Tests for ImageGenerator panel-prompt construction (no network I/O).

Constructing the OpenAI client with a dummy key makes no request, so
_build_panel_prompt can be exercised directly. Regression guard for the bug
where the project art style was dropped from every panel: the breakdown's panel
dicts have no "style" key, so the prompt always fell back to a generic
"comic book art" regardless of the user's chosen/inferred style.
"""

from src.assets.generator import ImageGenerator

PANEL = {
    "description": "A rain-soaked alley at night",
    "characters": ["Sarah"],
    "camera_angle": "close-up",
}
CHARACTER_PROMPTS = {"Sarah": "noir comic, Sarah, green eyes, trench coat"}


def _gen():
    return ImageGenerator(api_key="sk-dummy-no-network")


def test_explicit_style_is_used():
    prompt = _gen()._build_panel_prompt(PANEL, CHARACTER_PROMPTS, style="noir comic")
    assert prompt.startswith("noir comic,")
    assert "comic book art" not in prompt


def test_falls_back_to_generic_when_no_style():
    prompt = _gen()._build_panel_prompt(PANEL, CHARACTER_PROMPTS)
    assert prompt.startswith("comic book art,")


def test_panel_style_key_used_when_no_explicit_style():
    panel = {**PANEL, "style": "manga"}
    prompt = _gen()._build_panel_prompt(panel, CHARACTER_PROMPTS)
    assert prompt.startswith("manga,")


def test_explicit_style_overrides_panel_style():
    panel = {**PANEL, "style": "manga"}
    prompt = _gen()._build_panel_prompt(panel, CHARACTER_PROMPTS, style="noir comic")
    assert prompt.startswith("noir comic,")


def test_character_prompt_is_included():
    prompt = _gen()._build_panel_prompt(PANEL, CHARACTER_PROMPTS, style="noir comic")
    assert "trench coat" in prompt
    assert "close-up" in prompt


def test_content_policy_sanitization_still_applies():
    panel = {"description": "blood on the floor", "characters": [], "camera_angle": "wide"}
    prompt = _gen()._build_panel_prompt(panel, {}, style="noir comic")
    assert "blood" not in prompt
    assert "dark stains" in prompt
