"""Tests for the page layout engine (Stage 5 panel placement).

The "no panel dropped" tests are a regression guard: ``_calculate_panel_positions``
used to cap the number of rectangles at each template's nominal capacity (3, 4,
1, 6). ``compose_page`` then ``zip``s the panel images against those rectangles,
so any panel beyond the cap -- already generated and paid for in Stage 4 --
silently vanished from the page. The engine must now emit one rectangle per
panel for every layout.
"""

import pytest

from PIL import Image

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


def test_four_panel_grid_is_two_by_two():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("4-panel-grid", 4)
    assert len(positions) == 4
    xs = sorted({p[0] for p in positions})
    ys = sorted({p[1] for p in positions})
    assert len(xs) == 2  # two columns
    assert len(ys) == 2  # two rows


def test_single_splash_is_full_page_panel():
    comp = PageCompositor()
    positions = comp._calculate_panel_positions("splash", 1)
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


def test_unknown_layout_falls_back_to_stacked_rows():
    comp = PageCompositor()
    fallback = comp._calculate_panel_positions("nonexistent-layout", 3)
    expected = comp._calculate_panel_positions("3-panel-grid", 3)
    assert fallback == expected


@pytest.mark.parametrize("layout", ["3-panel-grid", "4-panel-grid", "splash", "webtoon"])
@pytest.mark.parametrize("panel_count", [1, 2, 5, 7, 12])
def test_no_panel_is_ever_dropped(layout, panel_count):
    """Every panel must get its own rectangle, even past the template capacity.

    This is the core regression guard: ``compose_page`` zips images against
    these rectangles, so ``len(positions) < panel_count`` means lost panels.
    """
    comp = PageCompositor()
    positions = comp._calculate_panel_positions(layout, panel_count)
    assert len(positions) == panel_count


def test_zero_panels_yields_no_positions():
    comp = PageCompositor()
    assert comp._calculate_panel_positions("3-panel-grid", 0) == []


@pytest.mark.parametrize("layout", ["3-panel-grid", "4-panel-grid", "splash", "webtoon"])
def test_pathological_panel_count_keeps_positive_cells(layout):
    """An absurd panel count on one page must still yield positive-area rects.

    Without the size clamp, floor division drives cell width/height to 0 (then
    negative), and PIL raises inside compose_page's unguarded border drawing,
    aborting the whole page/job. This guards the clamp.
    """
    comp = PageCompositor()
    positions = comp._calculate_panel_positions(layout, 250)
    assert len(positions) == 250
    assert all(w > 0 and h > 0 for (_, _, w, h) in positions)


def test_positions_stay_within_page_bounds():
    comp = PageCompositor()
    for layout in ("3-panel-grid", "4-panel-grid", "splash", "webtoon"):
        # Include over-capacity counts so the grown grid is bounds-checked too.
        for panel_count in (1, 4, 9):
            for pos in comp._calculate_panel_positions(layout, panel_count):
                x, y, w, h = pos
                assert x >= 0 and y >= 0
                assert w > 0 and h > 0
                assert x + w <= comp.page_width
                assert y + h <= comp.page_height


def test_compose_page_places_every_panel(tmp_path):
    """End-to-end guard: a page with more panels than the template's nominal
    capacity must still render all of them onto the page (none silently lost).
    """
    comp = PageCompositor()

    # Five distinct solid-color panels on a nominally 3-row grid.
    colors = ["red", "green", "blue", "yellow", "purple"]
    panel_paths = []
    for i, color in enumerate(colors):
        p = tmp_path / f"panel_{i}.png"
        Image.new("RGB", (400, 400), color).save(p)
        panel_paths.append(str(p))

    page_data = {
        "page_number": 1,
        "layout": "3-panel-grid",
        "panels": [{"global_panel_num": i + 1} for i in range(len(colors))],
    }
    out_path = tmp_path / "page_001.png"

    comp.compose_page(page_data, panel_paths, str(out_path))

    assert out_path.exists()
    page = Image.open(out_path).convert("RGB")
    assert page.size == (comp.page_width, comp.page_height)

    # Each panel occupies its own rectangle; sample the center of each and
    # confirm all five colors made it onto the page (zip-dropping would lose the
    # 4th and 5th).
    positions = comp._calculate_panel_positions("3-panel-grid", len(colors))
    seen = set()
    for (x, y, w, h) in positions:
        seen.add(page.getpixel((x + w // 2, y + h // 2)))
    # 5 distinct strong colors -> 5 distinct samples (allowing for resampling,
    # they remain clearly distinct), proving no panel was dropped.
    assert len(seen) == len(colors)
