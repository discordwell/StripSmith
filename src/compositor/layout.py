"""Page layout and panel composition (Stage 5)."""

import math
import os
from pathlib import Path
from typing import Dict, List, Tuple
from PIL import Image, ImageDraw, ImageFont

from src.utils.logger import get_logger
from src.utils.config import get_config

logger = get_logger("stripsmith.layout")


class PageCompositor:
    """Compose comic pages from panel images."""

    def __init__(self):
        """Initialize page compositor."""
        self.config = get_config()

        # Page settings
        self.page_width, self.page_height = self.config.get(
            "layout.page_size", [1200, 1600]
        )
        self.gutter = self.config.get("layout.gutter_width", 10)
        self.margin = self.config.get("layout.page_margin", 20)

        logger.info(f"Page compositor initialized: {self.page_width}x{self.page_height}")

    def compose_page(
        self,
        page_data: Dict,
        panel_images: List[str],
        output_path: str
    ) -> str:
        """
        Compose a comic page from panel images.

        Args:
            page_data: Page data with layout and panels
            panel_images: List of paths to panel images
            output_path: Path to save composed page

        Returns:
            Path to composed page image
        """
        page_num = page_data.get("page_number", 1)
        layout = page_data.get("layout", "3-panel-grid")

        logger.info(f"Composing page {page_num} with layout: {layout}")

        # Create blank page
        page = Image.new('RGB', (self.page_width, self.page_height), 'white')

        # Get panel positions
        positions = self._calculate_panel_positions(layout, len(panel_images))

        # Place panels
        for i, (panel_path, position) in enumerate(zip(panel_images, positions)):
            try:
                panel_img = Image.open(panel_path)
                panel_img = self._resize_panel(panel_img, position)
                page.paste(panel_img, (position[0], position[1]))

                logger.debug(f"Placed panel {i+1} at {position}")

            except Exception as e:
                logger.error(f"Failed to place panel {panel_path}: {e}")
                continue

        # Add panel borders
        self._draw_panel_borders(page, positions)

        # Save page
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        page.save(output_path, 'PNG', dpi=(300, 300))

        logger.info(f"Page saved: {output_path}")
        return output_path

    # How many columns each named layout's grid uses. Rows are derived from the
    # panel count, so the page always grows enough rows to hold *every* panel.
    _LAYOUT_COLUMNS = {
        "3-panel-grid": 1,   # full-width horizontal strips, stacked vertically
        "webtoon": 1,        # vertical scroll: full-width strips, stacked
        "4-panel-grid": 2,   # two columns
    }

    def _calculate_panel_positions(
        self,
        layout: str,
        panel_count: int
    ) -> List[Tuple[int, int, int, int]]:
        """
        Calculate panel positions for layout.

        Always returns exactly ``panel_count`` (x, y, width, height) rectangles
        so the compositor never drops a panel. ``compose_page`` ``zip``s the
        panel images against these positions, so if this returned fewer
        rectangles than there are panels, the surplus panels -- already
        generated and *paid for* in Stage 4 -- would vanish from the page with
        no warning. Instead the grid grows extra rows to fit whatever the
        breakdown placed on the page.

        Returns:
            List of (x, y, width, height) tuples, one per panel.
        """
        if panel_count <= 0:
            return []

        # Splash = a single full-bleed panel. Only meaningful for one panel; if
        # a breakdown ever marks a multi-panel page "splash", fall through to a
        # near-square grid so the extra panels are kept rather than discarded.
        if layout == "splash" and panel_count == 1:
            return [(
                self.margin,
                self.margin,
                self.page_width - (2 * self.margin),
                self.page_height - (2 * self.margin),
            )]

        if layout in self._LAYOUT_COLUMNS:
            cols = self._LAYOUT_COLUMNS[layout]
        elif layout == "splash":
            # Multi-panel "splash": keep panels as large as possible.
            cols = math.ceil(math.sqrt(panel_count))
        else:
            logger.warning(f"Unknown layout: {layout}, using stacked rows")
            cols = 1

        return self._grid_positions(cols, panel_count)

    def _grid_positions(
        self,
        cols: int,
        panel_count: int
    ) -> List[Tuple[int, int, int, int]]:
        """Lay out ``panel_count`` cells row-major in a grid ``cols`` wide.

        The row count is derived from ``panel_count`` so every panel gets a
        cell. Cells are gutter-separated and stay within the page margins.
        """
        cols = max(1, cols)
        rows = math.ceil(panel_count / cols)

        usable_width = self.page_width - (2 * self.margin)
        usable_height = self.page_height - (2 * self.margin)

        # Clamp to a positive size: with an absurd number of panels on one page
        # the floor division can reach 0 (or go negative once gutters dominate),
        # which would make PIL raise in _resize_panel/_draw_panel_borders and
        # abort the whole page (and the job). A degenerate-but-valid rect keeps
        # composition total — no realistic breakdown reaches this regime.
        cell_width = max(1, (usable_width - (cols - 1) * self.gutter) // cols)
        cell_height = max(1, (usable_height - (rows - 1) * self.gutter) // rows)

        positions = []
        for index in range(panel_count):
            row, col = divmod(index, cols)
            x = self.margin + col * (cell_width + self.gutter)
            y = self.margin + row * (cell_height + self.gutter)
            positions.append((x, y, cell_width, cell_height))

        return positions

    def _resize_panel(
        self,
        panel: Image.Image,
        position: Tuple[int, int, int, int]
    ) -> Image.Image:
        """Resize panel to fit position."""
        target_width = position[2]
        target_height = position[3]

        # Resize maintaining aspect ratio
        panel_resized = panel.copy()
        panel_resized.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)

        # Create centered version if aspect ratios don't match
        result = Image.new('RGB', (target_width, target_height), 'white')

        # Center the panel
        paste_x = (target_width - panel_resized.width) // 2
        paste_y = (target_height - panel_resized.height) // 2

        result.paste(panel_resized, (paste_x, paste_y))

        return result

    def _draw_panel_borders(
        self,
        page: Image.Image,
        positions: List[Tuple[int, int, int, int]]
    ):
        """Draw borders around panels."""
        draw = ImageDraw.Draw(page)

        for pos in positions:
            x, y, w, h = pos

            # Draw rectangle border
            draw.rectangle(
                [(x, y), (x + w, y + h)],
                outline='black',
                width=3
            )

    def add_text_overlay(
        self,
        page_path: str,
        panel_data: Dict,
        output_path: str
    ) -> str:
        """
        Add dialogue and narration text to a page.

        Args:
            page_path: Path to composed page
            panel_data: Panel data with dialogue
            output_path: Output path

        Returns:
            Path to page with text
        """
        logger.info("Adding text overlay...")

        page = Image.open(page_path)
        draw = ImageDraw.Draw(page)

        # Load font
        try:
            font_size = self.config.get("bubbles.font_size", 14)
            font = ImageFont.truetype("arial.ttf", font_size)
        except:
            font = ImageFont.load_default()

        # Add text for each panel (simplified - just caption text at bottom)
        # Full speech bubble implementation would be Phase 2

        page.save(output_path, 'PNG')
        logger.info(f"Text overlay complete: {output_path}")

        return output_path
