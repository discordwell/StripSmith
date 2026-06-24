"""Regression tests for the web download endpoint (offline, via TestClient).

Guards two backend bugs:

* PNG output is a *directory* of page images. ``download_result`` served it with
  ``FileResponse(directory)``, which raises at send time — so a user picking the
  frontend's "PNG Images" format got a broken download. It must instead deliver
  a single ``.zip`` of the pages (the frontend download link expects one file).
* ``process_comic_generation`` indexed ``job["session_id"]`` before checking the
  job existed, so a missing job became a confusing TypeError instead of a clean
  no-op.

No API keys or network: jobs are completed directly through the JobManager.
"""

import asyncio
import io
import zipfile

from fastapi.testclient import TestClient
from PIL import Image

from backend import main
from backend.jobs import JobStatus


def _client():
    # Not used as a context manager on purpose: that would fire the startup
    # event and spawn the long-lived cleanup loop. We only need request routing.
    return TestClient(main.app)


def _complete_job(job_id, output_path, output_format):
    # Distinct job_id per test: main.job_manager is a module-level singleton
    # shared across tests, so reusing an id would couple unrelated tests.
    jm = main.job_manager
    jm.create_job(
        job_id=job_id,
        session_id="s",
        story_text="x",
        story_filename="x.txt",
        output_format=output_format,
    )
    jm.update_job_status(
        job_id,
        JobStatus.COMPLETED,
        progress=100,
        result={"output_path": str(output_path)},
    )
    return job_id


def test_png_download_returns_zip_of_pages(tmp_path):
    pages_dir = tmp_path / "pages"
    pages_dir.mkdir()
    for i in (1, 2):
        Image.new("RGB", (4, 4), "white").save(pages_dir / f"page_{i:03d}.png")

    job_id = _complete_job("dl-png", pages_dir, "png")
    resp = _client().get(f"/api/download/{job_id}")

    assert resp.status_code == 200
    # A real zip containing exactly the page images (was: 500 on a directory).
    archive = zipfile.ZipFile(io.BytesIO(resp.content))
    assert sorted(archive.namelist()) == ["page_001.png", "page_002.png"]


def test_single_file_download_passes_through(tmp_path):
    pdf = tmp_path / "comic.pdf"
    pdf.write_bytes(b"%PDF-1.4 fake")

    job_id = _complete_job("dl-pdf-passthrough", pdf, "pdf")
    resp = _client().get(f"/api/download/{job_id}")

    assert resp.status_code == 200
    assert resp.content == b"%PDF-1.4 fake"


def test_download_missing_output_is_404(tmp_path):
    job_id = _complete_job("dl-pdf-missing", tmp_path / "does_not_exist.pdf", "pdf")
    resp = _client().get(f"/api/download/{job_id}")
    assert resp.status_code == 404


def test_process_missing_job_is_clean_noop(monkeypatch):
    # A job that was never created must be a clean early return. With the old
    # dereference-before-check ordering, job["session_id"] raised TypeError on
    # the missing (None) job, which the surrounding except caught and recorded
    # as a FAILED status update — so spying on update_job_status distinguishes
    # the bug (one call) from the fix (no calls). asyncio.run in a sync test
    # follows the repo's convention for async code.
    calls = []
    monkeypatch.setattr(
        main.job_manager,
        "update_job_status",
        lambda *a, **k: calls.append((a, k)),
    )
    asyncio.run(main.process_comic_generation("no-such-job-id"))
    assert calls == []
