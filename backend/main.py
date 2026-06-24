"""FastAPI backend for StripSmith web app."""

import os
import sys
import uuid
import asyncio
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional, Dict, Any

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
import uvicorn

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from backend.jobs import JobManager, JobStatus
from backend.api_wrapper import ComicGenerator

# Job manager instance (in-memory sessions + jobs)
job_manager = JobManager()


async def cleanup_old_jobs():
    """Remove jobs/sessions older than 2 hours, on a 10-minute loop."""
    while True:
        await asyncio.sleep(600)  # Every 10 minutes
        job_manager.cleanup_old_jobs(max_age_hours=2)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Run the periodic cleanup loop for the app's lifetime.

    Modern replacement for the deprecated ``@app.on_event("startup")`` hook;
    also cancels the loop cleanly on shutdown instead of leaking the task.
    """
    cleanup_task = asyncio.create_task(cleanup_old_jobs())
    try:
        yield
    finally:
        cleanup_task.cancel()


# Initialize FastAPI app
app = FastAPI(title="StripSmith API", version="1.0.0", lifespan=lifespan)

# CORS configuration - allow Vercel frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:5173",
        "https://*.vercel.app",
        "*"  # For development - restrict in production
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Models
class SetKeysRequest(BaseModel):
    openai_api_key: str
    anthropic_api_key: str


class GenerateRequest(BaseModel):
    session_id: str
    style: Optional[str] = None
    chapters: Optional[str] = None
    format: str = "pdf"


# Health check
@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "StripSmith API",
        "version": "1.0.0"
    }


@app.get("/health")
async def health():
    """Health check for Railway."""
    return {"status": "healthy"}


# Session management
@app.post("/api/session/create")
async def create_session():
    """
    Create a new session for storing API keys.

    Returns:
        session_id: Unique session identifier
    """
    session_id = str(uuid.uuid4())
    job_manager.create_session(session_id)
    return {
        "session_id": session_id,
        "expires_in": 7200  # 2 hours
    }


@app.post("/api/session/set-keys")
async def set_keys(request: SetKeysRequest):
    """
    Store API keys in session (memory only, never persisted).

    Args:
        openai_api_key: OpenAI API key
        anthropic_api_key: Anthropic API key

    Returns:
        session_id: Session identifier to use for generation
    """
    # Validate keys (basic check)
    if not request.openai_api_key.startswith("sk-"):
        raise HTTPException(status_code=400, detail="Invalid OpenAI API key format")

    if not request.anthropic_api_key.startswith("sk-ant-"):
        raise HTTPException(status_code=400, detail="Invalid Anthropic API key format")

    # Create session and store keys
    session_id = str(uuid.uuid4())
    job_manager.create_session(
        session_id,
        openai_key=request.openai_api_key,
        anthropic_key=request.anthropic_api_key
    )

    return {
        "session_id": session_id,
        "message": "API keys stored securely in session",
        "expires_in": 7200  # 2 hours
    }


# Comic generation
@app.post("/api/generate")
async def generate_comic(
    background_tasks: BackgroundTasks,
    session_id: str = Form(...),
    story_file: UploadFile = File(...),
    style: Optional[str] = Form(None),
    chapters: Optional[str] = Form("all"),
    output_format: str = Form("pdf")
):
    """
    Start comic generation job.

    Args:
        session_id: Session ID with stored API keys
        story_file: Story text file
        style: Art style (optional)
        chapters: Chapters to process (e.g., "1-3" or "all")
        output_format: Output format (pdf, png, cbz)

    Returns:
        job_id: Job identifier for tracking progress
    """
    # Validate session
    session = job_manager.get_session(session_id)
    if not session:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    if not session.get("openai_key") or not session.get("anthropic_key"):
        raise HTTPException(status_code=400, detail="API keys not set for this session")

    # Save uploaded file
    story_content = await story_file.read()
    story_text = story_content.decode('utf-8')

    # Create job
    job_id = str(uuid.uuid4())
    job_manager.create_job(
        job_id=job_id,
        session_id=session_id,
        story_text=story_text,
        story_filename=story_file.filename,
        style=style,
        chapters=chapters,
        output_format=output_format
    )

    # Start background processing
    background_tasks.add_task(
        process_comic_generation,
        job_id=job_id
    )

    return {
        "job_id": job_id,
        "status": "started",
        "message": "Comic generation started. Use /api/status/{job_id} to check progress."
    }


async def process_comic_generation(job_id: str):
    """Background task to process comic generation."""
    try:
        # Get the job, then its session. Check the job exists before indexing
        # it — a missing job (e.g. already cleaned up) would otherwise raise a
        # confusing TypeError on job["session_id"] before the guard below ran.
        job = job_manager.get_job(job_id)
        if not job:
            return

        session = job_manager.get_session(job["session_id"])
        if not session:
            return

        # Update status
        job_manager.update_job_status(job_id, JobStatus.PROCESSING, progress=0)

        # Create generator with user's API keys
        generator = ComicGenerator(
            openai_api_key=session["openai_key"],
            anthropic_api_key=session["anthropic_key"],
            job_manager=job_manager,
            job_id=job_id
        )

        # Run generation
        output_path = await generator.generate_comic(
            story_text=job["story_text"],
            style=job.get("style"),
            chapters=job.get("chapters", "all"),
            output_format=job.get("output_format", "pdf")
        )

        # Update job with result
        job_manager.update_job_status(
            job_id,
            JobStatus.COMPLETED,
            progress=100,
            result={"output_path": str(output_path)}
        )

    except Exception as e:
        # Update job with error
        job_manager.update_job_status(
            job_id,
            JobStatus.FAILED,
            error=str(e)
        )


@app.get("/api/status/{job_id}")
async def get_job_status(job_id: str):
    """
    Get job status and progress.

    Args:
        job_id: Job identifier

    Returns:
        Job status, progress, and result/error if available
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    response = {
        "job_id": job_id,
        "status": job["status"],
        "progress": job.get("progress", 0),
        "stage": job.get("stage", ""),
        "created_at": job["created_at"].isoformat(),
    }

    if job["status"] == JobStatus.COMPLETED:
        response["result"] = job.get("result", {})
        response["download_url"] = f"/api/download/{job_id}"

    if job["status"] == JobStatus.FAILED:
        response["error"] = job.get("error", "Unknown error")

    return response


@app.get("/api/download/{job_id}")
async def download_result(job_id: str):
    """
    Download generated comic.

    Args:
        job_id: Job identifier

    Returns:
        Generated comic file
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] != JobStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="Job not completed yet")

    result = job.get("result", {})
    output_path = result.get("output_path")

    if not output_path or not Path(output_path).exists():
        raise HTTPException(status_code=404, detail="Output file not found")

    download_path = Path(output_path)

    # PNG output is a *directory* of page images, but FileResponse can only
    # serve a regular file (it raises at send time on a directory), and the
    # frontend download link expects a single file. Package the pages into one
    # .zip for delivery. PDF/CBZ outputs are already single files and pass
    # straight through.
    if download_path.is_dir():
        zip_path = download_path.with_suffix(".zip")
        if not zip_path.exists():
            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for page in sorted(download_path.iterdir()):
                    if page.is_file():
                        zf.write(page, page.name)
        download_path = zip_path

    return FileResponse(
        str(download_path),
        media_type="application/octet-stream",
        filename=download_path.name
    )


@app.delete("/api/job/{job_id}")
async def cancel_job(job_id: str):
    """
    Cancel a running job.

    Args:
        job_id: Job identifier
    """
    job = job_manager.get_job(job_id)

    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    if job["status"] in [JobStatus.COMPLETED, JobStatus.FAILED]:
        raise HTTPException(status_code=400, detail="Job already finished")

    job_manager.update_job_status(job_id, JobStatus.FAILED, error="Cancelled by user")

    return {"message": "Job cancelled"}


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=True
    )
