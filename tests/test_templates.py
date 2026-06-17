"""Tests for character prompt templating (Stage 2 prompt construction)."""

import pytest

from src.assets.templates import CharacterTemplateManager

STYLE = {"art_style": "noir comic", "mood": "dark", "era": "1940s"}
CHAR = {
    "name": "Sarah Chen",
    "age": "mid-30s",
    "gender": "female",
    "physical_features": "blonde hair, green eyes",
    "clothing": "grey trench coat",
    "accessories": "badge",
}


def test_create_template_includes_visual_fields():
    mgr = CharacterTemplateManager()
    prompt = mgr.create_template(CHAR, STYLE)
    assert "noir comic" in prompt
    assert "Sarah Chen" in prompt
    assert "blonde hair, green eyes" in prompt
    assert "grey trench coat" in prompt
    # Template is stored for later reuse
    assert "Sarah Chen" in mgr.templates
    assert mgr.templates["Sarah Chen"]["base_prompt"] == prompt


def test_create_all_templates_returns_map():
    mgr = CharacterTemplateManager()
    spec = {"characters": [CHAR], "style": STYLE}
    result = mgr.create_all_templates(spec)
    assert set(result.keys()) == {"Sarah Chen"}


def test_get_character_prompt_adds_angle_and_shot():
    mgr = CharacterTemplateManager()
    mgr.create_template(CHAR, STYLE)
    prompt = mgr.get_character_prompt("Sarah Chen", angle="profile", shot_type="full-body")
    assert "side profile" in prompt
    assert "full body shot" in prompt


def test_get_character_prompt_unknown_raises():
    mgr = CharacterTemplateManager()
    with pytest.raises(ValueError):
        mgr.get_character_prompt("Nobody")


def test_character_sheet_prompts_default_angles():
    mgr = CharacterTemplateManager()
    mgr.create_template(CHAR, STYLE)
    prompts = mgr.create_character_sheet_prompts("Sarah Chen")
    angles = {p["angle"] for p in prompts}
    assert angles == {"front", "3/4", "profile"}
    for p in prompts:
        assert p["character"] == "Sarah Chen"
        assert "reference sheet" in p["prompt"]


def test_missing_optional_fields_have_defaults():
    mgr = CharacterTemplateManager()
    minimal = {"name": "Ghost"}
    prompt = mgr.create_template(minimal, {})
    assert "Ghost" in prompt
    # No crash, and falls back to sensible defaults for clothing/style
    assert "comic book art" in prompt
