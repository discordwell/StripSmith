"""Tests for the page layout engine (Stage 5 panel placement)."""

import pytest

from src.compositor.layout import PageCompositor


def test_three_panel_grid_positions():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("3-panel-grid", 3)
    assert len(positions) == 3
    # Stacked vertically: each row shares x and width, y increases
    xs = {p[0] for p in positions}
    assert len(xs) == 1  # same left margin
    ys = [p[1] for p in positions]
    assert ys == sorted(ys)
    assert ys[0] < ys[1] < ys[2]


def test_three_panel_grid_caps_at_three():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("3-panel-grid", 10)
    assert len(positions) == 3


def test_four_panel_grid_is_two_by_two():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("4-panel-grid", 4)
    assert len(positions) == 4
    xs = sorted({p[0] for p in positions})
    ys = sorted({p[1] for p in positions})
    assert len(xs) == 2  # two columns
    assert len(ys) == 2  # two rows


def test_splash_is_single_full_panel():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("splash", 5)
    assert len(positions) == 1
    x, y, w, h = positions[0]
    assert w == comp.page_width - 2 * comp.margin
    assert h == comp.page_height - 2 * comp.margin


def test_webtoon_stacks_vertically():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("webtoon", 4)
    assert len(positions) == 4
    ys = [p[1] for p in positions]
    assert ys == sorted(ys)


def test_unknown_layout_falls_back_to_three_panel():
    comp = PageCompositor()
    fallback = comp._calculate_panel_positions("nonexistent-layout", 3)
    expected = comp._calculate_panel_positions("3-panel-grid", 3)
    assert fallback == expected


def test_positions_stay_within_page_bounds():
    comp = PageCompositor()
    for layout in ("3-panel-grid", "4-panel-grid", "splash", "webtoon"):
        for pos in comp._calculate_panel_positions(layout, 4):
            x, y, w, h = pos
            assert x >= 0 and y >= 0
            assert x + w <= comp.page_width
            assert y + h <= comp.page_height
