"""Tests for the shared front-end helpers in src.utils.pipeline.

panel_image_name is a regression guard for the multi-chapter collision bug:
panel numbering restarts at 1 each chapter, so an unscoped filename made
chapter 2's panels overwrite chapter 1's on disk (and the compositor then read
the wrong images). select_chapters consolidates + hardens the chapter-selector
parsing that the CLI and web backend previously duplicated inline.
"""

import pytest

from src.utils.pipeline import select_chapters, panel_image_name


CHAPTERS = [{"number": 1}, {"number": 2}, {"number": 3}]


# --- select_chapters -------------------------------------------------------

def test_select_all_with_none():
    assert select_chapters(None, CHAPTERS) == CHAPTERS


def test_select_all_keyword_is_case_insensitive_and_returns_copy():
    out = select_chapters("ALL", CHAPTERS)
    assert out == CHAPTERS
    assert out is not CHAPTERS  # a new list, not the original


def test_select_single_chapter():
    assert select_chapters("2", CHAPTERS) == [{"number": 2}]


def test_select_inclusive_range():
    assert select_chapters("1-2", CHAPTERS) == [{"number": 1}, {"number": 2}]


def test_select_range_with_whitespace():
    assert select_chapters("  2 - 3 ", CHAPTERS) == [{"number": 2}, {"number": 3}]


def test_select_unknown_chapter_returns_empty():
    assert select_chapters("9", CHAPTERS) == []


def test_empty_string_means_all():
    # Empty string is treated like None ("all"), not an error.
    assert select_chapters("", CHAPTERS) == CHAPTERS


# Assert on the *message*, not just the type: the old inline
# ``map(int, chapters.split('-'))`` also raised a (bare, opaque) ValueError on
# these inputs, so `pytest.raises(ValueError)` alone wouldn't distinguish the
# friendly-error improvement from the buggy parser. Matching the message does.
@pytest.mark.parametrize("bad", ["1-3-5", "1-", "-2", "1-x"])
def test_malformed_range_gives_friendly_error(bad):
    with pytest.raises(ValueError, match="Invalid chapter range"):
        select_chapters(bad, CHAPTERS)


def test_non_numeric_selector_gives_friendly_error():
    with pytest.raises(ValueError, match="Invalid chapter selector"):
        select_chapters("abc", CHAPTERS)


def test_reversed_range_is_rejected():
    # The old parser silently returned [] here; the new one rejects it.
    with pytest.raises(ValueError, match="start must not exceed end"):
        select_chapters("3-1", CHAPTERS)


# --- panel_image_name ------------------------------------------------------

def test_panel_name_is_zero_padded():
    assert panel_image_name(1, 7) == "chapter_1_panel_007.png"


def test_panel_names_are_unique_across_chapters_for_same_panel_num():
    # The exact bug: global_panel_num restarts at 1 each chapter.
    n1 = panel_image_name(1, 1)
    n2 = panel_image_name(2, 1)
    assert n1 != n2, "panel filenames must be scoped by chapter"
