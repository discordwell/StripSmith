"""Tests for story normalization (Stage 0).

The smart-quote tests are a regression guard: the replacement table previously
had ASCII keys (the curly characters had been flattened on a prior save), so
real curly quotes from word processors were never normalized and dialogue
detection silently missed quoted speech.
"""

from src.analysis.normalizer import StoryNormalizer

# Build inputs from explicit codepoints so this test file can't be "fixed" by
# an editor flattening the curly characters (which is exactly the bug).
LDQUO, RDQUO = "“", "”"   # “ ”
LSQUO, RSQUO = "‘", "’"   # ‘ ’
LAQUO, RAQUO = "«", "»"   # « »


def test_double_curly_quotes_normalized():
    n = StoryNormalizer()
    out = n._normalize_quotes(f"{LDQUO}Hello{RDQUO}")
    assert out == '"Hello"'
    assert LDQUO not in out and RDQUO not in out


def test_single_curly_quotes_normalized():
    n = StoryNormalizer()
    out = n._normalize_quotes(f"It{RSQUO}s a {LSQUO}test{RSQUO}")
    assert out == "It's a 'test'"
    assert LSQUO not in out and RSQUO not in out


def test_angle_quotes_normalized():
    n = StoryNormalizer()
    out = n._normalize_quotes(f"{LAQUO}Bonjour{RAQUO}")
    assert out == '"Bonjour"'


def test_dialogue_detected_after_curly_quote_normalization():
    n = StoryNormalizer()
    result = n.normalize(f"Sarah said, {LDQUO}We need to talk.{RDQUO}")
    paras = result["paragraphs"]
    assert paras, "expected at least one annotated paragraph"
    assert any("[DIALOGUE]" in p or "[MIXED]" in p for p in paras), paras


def test_french_quote_dialogue_detected():
    n = StoryNormalizer()
    result = n.normalize(f"Le détective dit, {LAQUO}Nous devons parler.{RAQUO}")
    paras = result["paragraphs"]
    assert any("[DIALOGUE]" in p or "[MIXED]" in p for p in paras), paras


def test_curly_and_angle_dialogue_patterns_are_live():
    """The smart-double and French-angle dialogue patterns must actually match
    their quote characters -- the smart-quote pattern had previously been
    flattened to ASCII, making it a dead duplicate of the ASCII pattern. Match
    against UN-normalized text so this guards the patterns directly, not the
    quote normalization that runs ahead of them in normalize().
    """
    import re

    n = StoryNormalizer()
    smart = f"{LDQUO}hello{RDQUO}"
    french = f"{LAQUO}bonjour{RAQUO}"

    matches_smart = [bool(re.search(p, smart)) for p in n.dialogue_patterns]
    matches_french = [bool(re.search(p, french)) for p in n.dialogue_patterns]

    # The ASCII double-quote pattern (index 0) must NOT be what catches a smart
    # quote -- if it does, the dedicated smart-quote pattern has degenerated.
    assert not matches_smart[0]
    assert any(matches_smart), "no pattern matches smart double quotes"
    assert any(matches_french), "no pattern matches French angle quotes"


def test_pure_narration_is_annotated():
    n = StoryNormalizer()
    result = n.normalize("The rain fell on the empty street.")
    assert result["paragraphs"][0].startswith("[NARRATION]")


def test_whitespace_cleanup_collapses_runs():
    n = StoryNormalizer()
    out = n._clean_whitespace("a    b\n\n\n\n c   ")
    assert "    " not in out
    assert "\n\n\n" not in out
    assert out.strip() == out


def test_metadata_counts():
    n = StoryNormalizer()
    result = n.normalize("Chapter 1\n\nHello world here.\n\n---\n\nMore text.")
    meta = result["metadata"]
    assert meta["word_count"] > 0
    assert meta["paragraph_count"] >= 1
    # Scene break "---" contributes to the scene count
    assert meta["scene_count"] >= 1


def test_chapter_marker_detected():
    n = StoryNormalizer()
    result = n.normalize("Chapter 1\n\nIt begins.")
    assert result["structure"]["has_chapters"] is True


def test_extract_pov_first_person():
    n = StoryNormalizer()
    assert n.extract_pov("I walked to my car. I saw my friend. We left.") == "first"


def test_extract_pov_third_person():
    n = StoryNormalizer()
    assert n.extract_pov("She walked to her car. He saw them. They left.") == "third"


def test_extract_pov_unknown_on_empty():
    n = StoryNormalizer()
    assert n.extract_pov("123 456 789") == "unknown"
