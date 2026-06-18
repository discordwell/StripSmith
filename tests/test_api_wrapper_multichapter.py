"""Regression tests for multi-chapter wiring in the web ComicGenerator.

Three bugs are guarded here, all of which only surface with >1 chapter or a
real art style:

1. Panel image filenames must be scoped by chapter. ``global_panel_num``
   restarts at 1 each chapter, so unscoped names made chapter 2's panels
   overwrite chapter 1's, and the compositor then read the wrong images.
2. The project art style must be threaded into panel generation (the breakdown's
   panel dicts carry no "style" key, so panels otherwise default to generic art).
3. The panel breakdown must receive the *normalized* text the analyzer indexed,
   not the raw story text, or chapter paragraph spans are sliced from the wrong
   string.

Every pipeline class is mocked, so no network or API keys are needed.
"""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import backend.api_wrapper as api_wrapper
from backend.api_wrapper import ComicGenerator

JOB_ID = "pytest-multichapter"
NORMALIZED_TEXT = "Some normalized story."
ART_STYLE = "noir comic"


@pytest.fixture
def two_chapter_pipeline(monkeypatch):
    """Mock pipeline: 2 chapters, each one page with a single panel num=1."""
    normalizer_cls = MagicMock(name="StoryNormalizer")
    normalizer_cls.return_value.normalize.return_value = {
        "text": NORMALIZED_TEXT,
        "metadata": {"word_count": 3},
    }

    analyzer_cls = MagicMock(name="NarrativeAnalyzer")
    analyzer_cls.return_value.analyze.return_value = {
        "chapters": [{"number": 1}, {"number": 2}],
        "characters": [],
        "style": {"art_style": ART_STYLE},
    }

    templates_cls = MagicMock(name="CharacterTemplateManager")
    templates_cls.return_value.templates = {}

    generator_cls = MagicMock(name="ImageGenerator")
    generator_cls.return_value.get_total_cost.return_value = 0.0

    breakdown_cls = MagicMock(name="PanelBreakdown")

    def fake_breakdown(chapter, story_text, project_spec):
        # Each chapter independently numbers its single panel as 1.
        return {
            "chapter_number": chapter["number"],
            "pages": [
                {
                    "page_number": 1,
                    "layout": "splash",
                    "panels": [
                        {"global_panel_num": 1, "characters": [], "description": "d"}
                    ],
                }
            ],
        }

    breakdown_cls.return_value.breakdown_chapter.side_effect = fake_breakdown

    compositor_cls = MagicMock(name="PageCompositor")
    exporter_cls = MagicMock(name="ComicExporter")

    monkeypatch.setattr(api_wrapper, "StoryNormalizer", normalizer_cls)
    monkeypatch.setattr(api_wrapper, "NarrativeAnalyzer", analyzer_cls)
    monkeypatch.setattr(api_wrapper, "CharacterTemplateManager", templates_cls)
    monkeypatch.setattr(api_wrapper, "ImageGenerator", generator_cls)
    monkeypatch.setattr(api_wrapper, "PanelBreakdown", breakdown_cls)
    monkeypatch.setattr(api_wrapper, "PageCompositor", compositor_cls)
    monkeypatch.setattr(api_wrapper, "ComicExporter", exporter_cls)

    yield {
        "generator": generator_cls,
        "breakdown": breakdown_cls,
        "compositor": compositor_cls,
    }

    for sub in ("temp", "output"):
        shutil.rmtree(Path("data") / sub / JOB_ID, ignore_errors=True)


def _run(mocks):
    gen = ComicGenerator(
        openai_api_key="sk-openai-test",
        anthropic_api_key="sk-ant-test",
        job_manager=MagicMock(),
        job_id=JOB_ID,
    )
    asyncio.run(
        gen.generate_comic(story_text="A story.", style=None, chapters="all", output_format="pdf")
    )


def test_panel_filenames_are_chapter_scoped(two_chapter_pipeline):
    _run(two_chapter_pipeline)
    paths = [
        c.kwargs["output_path"]
        for c in two_chapter_pipeline["generator"].return_value.generate_panel.call_args_list
    ]
    assert len(paths) == 2
    assert len(set(paths)) == 2, f"panel image paths collided across chapters: {paths}"


def test_compositor_reads_distinct_panels_per_chapter(two_chapter_pipeline):
    _run(two_chapter_pipeline)
    compose_calls = two_chapter_pipeline["compositor"].return_value.compose_page.call_args_list
    assert len(compose_calls) == 2
    page_panel_paths = [c.kwargs["panel_images"][0] for c in compose_calls]
    assert page_panel_paths[0] != page_panel_paths[1], (
        "each chapter's page must reference its own panel image"
    )


def test_art_style_is_threaded_into_panels(two_chapter_pipeline):
    _run(two_chapter_pipeline)
    styles = {
        c.kwargs.get("style")
        for c in two_chapter_pipeline["generator"].return_value.generate_panel.call_args_list
    }
    assert styles == {ART_STYLE}


def test_breakdown_receives_normalized_text(two_chapter_pipeline):
    _run(two_chapter_pipeline)
    for call in two_chapter_pipeline["breakdown"].return_value.breakdown_chapter.call_args_list:
        # breakdown_chapter(chapter, story_text, project_spec) — positional.
        assert call.args[1] == NORMALIZED_TEXT
