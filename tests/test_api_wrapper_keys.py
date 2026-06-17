"""Tests that the web ComicGenerator threads user-supplied API keys into every
pipeline stage.

Regression guard for the bug where PanelBreakdown() was constructed with no
api_key: in the hosted backend there is no ANTHROPIC_API_KEY in the
environment, so that call raised "ANTHROPIC_API_KEY not found" and aborted
every web generation at Stage 3.
"""

import asyncio
import shutil
from pathlib import Path
from unittest.mock import MagicMock

import pytest

import backend.api_wrapper as api_wrapper
from backend.api_wrapper import ComicGenerator

OPENAI_KEY = "sk-openai-test"
ANTHROPIC_KEY = "sk-ant-test"
JOB_ID = "pytest-keywire"


@pytest.fixture
def patched_pipeline(monkeypatch):
    """Replace each pipeline class with a mock that returns minimal, valid data.

    Pages are empty, so the panel-generation and composition loops are no-ops —
    the test only needs the pipeline to run far enough to construct
    PanelBreakdown and reach the export step.
    """
    normalizer_cls = MagicMock(name="StoryNormalizer")
    normalizer_cls.return_value.normalize.return_value = {
        "text": "Some normalized story.",
        "metadata": {"word_count": 3},
    }

    analyzer_cls = MagicMock(name="NarrativeAnalyzer")
    analyzer_cls.return_value.analyze.return_value = {
        "chapters": [{"number": 1}],
        "characters": [],
    }

    templates_cls = MagicMock(name="CharacterTemplateManager")
    templates_cls.return_value.templates = {}

    generator_cls = MagicMock(name="ImageGenerator")
    generator_cls.return_value.get_total_cost.return_value = 0.0

    breakdown_cls = MagicMock(name="PanelBreakdown")
    breakdown_cls.return_value.breakdown_chapter.return_value = {
        "chapter_number": 1,
        "pages": [],
    }

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
        "analyzer": analyzer_cls,
        "generator": generator_cls,
        "breakdown": breakdown_cls,
    }

    # Clean up scratch dirs created under the gitignored data/ tree.
    for sub in ("temp", "output"):
        shutil.rmtree(Path("data") / sub / JOB_ID, ignore_errors=True)


def _run_generate(job_manager):
    gen = ComicGenerator(
        openai_api_key=OPENAI_KEY,
        anthropic_api_key=ANTHROPIC_KEY,
        job_manager=job_manager,
        job_id=JOB_ID,
    )
    return asyncio.run(
        gen.generate_comic(story_text="A story.", style="noir", chapters="all", output_format="pdf")
    )


def test_panel_breakdown_receives_user_anthropic_key(patched_pipeline):
    _run_generate(MagicMock())
    patched_pipeline["breakdown"].assert_called_once_with(api_key=ANTHROPIC_KEY)


def test_analyzer_receives_user_anthropic_key(patched_pipeline):
    _run_generate(MagicMock())
    patched_pipeline["analyzer"].assert_called_once_with(api_key=ANTHROPIC_KEY)


def test_image_generator_receives_user_openai_key(patched_pipeline):
    _run_generate(MagicMock())
    patched_pipeline["generator"].assert_called_once_with(api_key=OPENAI_KEY)


def test_progress_is_reported_to_job_manager(patched_pipeline):
    jm = MagicMock()
    _run_generate(jm)
    # Generation reports progress and finishes at 100%.
    assert jm.update_job_status.called
    final_calls = [c for c in jm.update_job_status.call_args_list
                   if c.kwargs.get("progress") == 100]
    assert final_calls, "expected a 100% progress update at completion"
