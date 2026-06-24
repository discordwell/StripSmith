"""Regression tests for character-sheet filename construction (offline).

The default character-sheet angles include ``"3/4"``. Built naively as
``f"{name}_{angle}.png"`` that yields ``"Sarah_3/4.png"``, which the filesystem
reads as a nested ``Sarah_3/`` directory containing ``4.png`` — silently
scattering the reference sheet instead of writing one flat file per angle. The
character name was also used raw in the filename while its directory was
sanitized, so they could disagree. These guard that every angle (slashes
included) produces a single file inside the character's directory, named
consistently with that directory.

Constructing the OpenAI client with a dummy key makes no network request, so the
generator can be exercised directly (matching test_generator_prompt.py).
"""

from pathlib import Path

from src.assets.generator import ImageGenerator


def _gen():
    return ImageGenerator(api_key="sk-dummy-no-network")


def test_sanitize_maps_slash_to_dash_not_dropped():
    g = _gen()
    assert g._sanitize_filename("3/4") == "3-4"
    assert "/" not in g._sanitize_filename("a/b/c")


def test_sanitize_preserves_normal_names_and_unicode():
    g = _gen()
    assert g._sanitize_filename("Sarah Chen") == "Sarah_Chen"
    assert g._sanitize_filename("Anne-Marie") == "Anne-Marie"
    # Accented letters survive: str.isalnum() is Unicode-aware, so they are not
    # mapped to a separator the way punctuation is.
    assert g._sanitize_filename("José") == "José"


def test_sanitize_never_returns_empty():
    g = _gen()
    # An all-punctuation name must not collapse to "" (which would write into
    # the parent directory) — fall back to a placeholder instead.
    assert g._sanitize_filename("///") == "unnamed"
    assert g._sanitize_filename("   ") == "unnamed"


def test_character_sheet_writes_flat_files_for_every_angle(tmp_path, monkeypatch):
    g = _gen()

    # Stub the network call: record where each image is written and create the
    # file, so the on-disk layout reflects the real generate_character_sheet
    # code path without touching DALL-E.
    recorded = []

    def fake_generate_image(prompt, output_path, **kwargs):
        recorded.append(Path(output_path))
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        Path(output_path).write_bytes(b"")
        return {"path": output_path, "cost": 0.0}

    monkeypatch.setattr(g, "generate_image", fake_generate_image)
    # Skip the inter-image rate-limit sleep so the test is fast.
    monkeypatch.setattr("src.assets.generator.time.sleep", lambda *a, **k: None)

    prompts = [
        {"angle": "front", "prompt": "p"},
        {"angle": "3/4", "prompt": "p"},
        {"angle": "profile", "prompt": "p"},
    ]
    g.generate_character_sheet("Sarah Chen", prompts, str(tmp_path))

    char_dir = tmp_path / "Sarah_Chen"

    # Exactly the three expected files, all directly inside the character dir.
    assert sorted(p.name for p in char_dir.iterdir()) == [
        "Sarah_Chen_3-4.png",
        "Sarah_Chen_front.png",
        "Sarah_Chen_profile.png",
    ]
    # No surprise nested subdirectory (the old "3/4" -> "Sarah_3/4.png" bug).
    assert all(p.is_file() for p in char_dir.iterdir())
    assert {p.parent for p in recorded} == {char_dir}
