"""Small, pure helpers shared by the CLI and web front ends.

These have no I/O or external-API dependencies so they can be unit-tested
directly, and — crucially — keep the *write* and *read* sides of panel image
files in sync. ``global_panel_num`` from the panel breakdown restarts at 1 for
every chapter (see ``src/panels/breakdown.py``), so panel filenames must be
scoped by chapter or a multi-chapter comic's panels collide on disk.
"""

from typing import Dict, List


def select_chapters(chapters: str, all_chapters: List[Dict]) -> List[Dict]:
    """Filter project-spec chapters by a front-end ``chapters`` selector.

    Args:
        chapters: One of ``None``/``""``/``"all"`` (every chapter), ``"N"`` (a
            single chapter), or ``"N-M"`` (an inclusive range). Surrounding
            whitespace and case (for ``"all"``) are tolerated.
        all_chapters: The ``chapters`` list from the project spec; each item is
            a dict with an integer ``"number"``.

    Returns:
        The subset of ``all_chapters`` matching the selector (a new list).

    Raises:
        ValueError: If the selector is malformed (e.g. ``"1-3-5"``, ``"abc"``,
            ``"5-1"``). A friendly message is raised instead of the opaque
            ``int()`` errors the previous inline parsing produced.
    """
    if not chapters or chapters.strip().lower() == "all":
        return list(all_chapters)

    spec = chapters.strip()

    if "-" in spec:
        parts = [p.strip() for p in spec.split("-")]
        if len(parts) != 2 or not all(p.isdigit() for p in parts):
            raise ValueError(
                f"Invalid chapter range: {chapters!r} (expected 'N-M', e.g. '1-3')"
            )
        start, end = int(parts[0]), int(parts[1])
        if start > end:
            raise ValueError(
                f"Invalid chapter range: {chapters!r} (start must not exceed end)"
            )
        return [c for c in all_chapters if start <= c.get("number", 0) <= end]

    if not spec.isdigit():
        raise ValueError(
            f"Invalid chapter selector: {chapters!r} (expected 'all', 'N', or 'N-M')"
        )

    target = int(spec)
    return [c for c in all_chapters if c.get("number") == target]


def panel_image_name(chapter_number: int, panel_number: int) -> str:
    """Filename for a generated panel image, scoped by chapter.

    Panel numbering (``global_panel_num``) restarts per chapter, so the chapter
    number must be part of the filename. Mirrors the page-image convention
    ``chapter_{n}_page_{m}.png`` used by the compositor.
    """
    return f"chapter_{chapter_number}_panel_{panel_number:03d}.png"
