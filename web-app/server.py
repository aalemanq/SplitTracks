#!/usr/bin/env python3
"""Split Tracks — web server for macOS / Windows / Linux."""

from __future__ import annotations

import json
import logging
import shutil
import sys
import threading
import uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import (
    AudioEngineError,
    SeparationCancelled,
    SeparationEngine,
    STEM_LABELS,
    STEM_ORDER,
)
from harmony import CifraClubProvider, guess_artist_title
from analysis import analyze_audio

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
_log = logging.getLogger("split-tracks")

STATIC_DIR = Path(__file__).resolve().parent / "static"
JOBS_DIR = Path.home() / "Split Tracks"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Split Tracks", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

engine = SeparationEngine()
cifra = CifraClubProvider()
_jobs: dict[str, dict] = {}
_job_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}


@app.get("/health")
def health():
    return {"status": "ok", "name": "Split Tracks"}


@app.post("/api/jobs")
async def create_job(
    file: UploadFile | None = File(None),
    url: str | None = Form(None),
    stems: str | None = Form(None),
):
    selected = json.loads(stems) if stems else list(STEM_ORDER)
    selected = [s for s in selected if s in STEM_ORDER]

    job_id = str(uuid.uuid4())[:8]
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)

    cancel = threading.Event()
    with _job_lock:
        _cancel_events[job_id] = cancel
        _jobs[job_id] = {"id": job_id, "status": "uploading", "progress": 0.0, "phase": "Recibiendo...", "stems": []}

    if file:
        tmp = job_dir / f"input_{file.filename or 'audio'}"
        with open(tmp, "wb") as f:
            while True:
                chunk = await file.read(1_048_576)
                if not chunk:
                    break
                f.write(chunk)
        audio_path = tmp
        artist, title = "", Path(file.filename or "audio").stem
    elif url:
        audio_path = None
        artist, title = "", ""
    else:
        raise HTTPException(400, "Archivo o URL requerido")

    thread = threading.Thread(
        target=_process_job,
        args=(job_id, audio_path if file else None, url if not file else None, artist, title, selected, cancel, job_dir),
        daemon=True,
    )
    thread.start()

    return {"id": job_id, "status": "uploading"}


def _process_job(job_id, audio_path, url, artist, title, selected, cancel, job_dir):
    try:
        if url:
            _update(job_id, "downloading", 0.1, "Descargando YouTube...")
            result = engine.download_youtube(
                url,
                progress=_progress(job_id, 0.1, 0.4, "YouTube"),
                cancel_event=cancel,
            )
            audio_path = result.path
            artist, title = guess_artist_title(result.title)

        _update(job_id, "analyzing", 0.4, "Analizando...")
        try:
            info = engine.probe(audio_path)
            analysis = analyze_audio(audio_path, cancel_event=cancel)
        except Exception:
            analysis = None
            info = engine.probe(audio_path)

        _update(job_id, "separating", 0.5, "Separando con Demucs...")
        result = engine.separate(
            audio_path,
            job_dir,
            tuple(selected),
            progress=_progress(job_id, 0.5, 0.95, "Demucs"),
            cancel_event=cancel,
        )

        stems_data = []
        for s in result.stems:
            stems_data.append({
                "name": s.name,
                "file": str(s.path.relative_to(job_dir)),
                "color": s.color,
                "kind": s.kind,
            })

        chart_info = {}
        if artist and title:
            try:
                candidates = cifra.search(artist, title)
                if candidates:
                    chart = cifra.fetch(candidates[0])
                    chart_info = {
                        "key": chart.key_name or "",
                        "scale": chart.scale or "",
                        "sections": [
                            {"title": s.title, "lines": [{"chords": l.chords} for l in s.lines]}
                            for s in chart.sections
                        ],
                    }
            except Exception:
                pass

        _update(job_id, "done", 1.0, "Listo", stems=stems_data)
        with _job_lock:
            job = _jobs.get(job_id)
            if job:
                job["bpm"] = round(analysis.bpm, 1) if analysis and analysis.bpm else 0
                job["key"] = chart_info.get("key", analysis.key_name if analysis else "")
                job["chord_sections"] = chart_info.get("sections", [])

    except SeparationCancelled:
        _cleanup(job_id)
    except AudioEngineError as e:
        _update(job_id, "error", 0, str(e))
    except Exception as e:
        _update(job_id, "error", 0, f"Error: {e}")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404)
    return job


@app.get("/api/jobs/{job_id}/stems/{stem_file:path}")
def serve_stem(job_id: str, stem_file: str):
    stem_path = JOBS_DIR / f"Split Tracks - {job_id}" / stem_file
    if not stem_path.exists():
        raise HTTPException(404)
    return FileResponse(stem_path, media_type="audio/wav")


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with _job_lock:
        cancel = _cancel_events.get(job_id)
    if cancel:
        cancel.set()
    return {"ok": True}


@app.post("/api/jobs/{job_id}/mix")
async def mix_job(job_id: str):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job or not job.get("stems"):
        raise HTTPException(400)
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"

    stems_for_mix = []
    for s in job["stems"]:
        stems_for_mix.append({
            "name": s["name"],
            "path": str(job_dir / s["file"]),
            "volume": 1.0,
            "mute": False,
            "solo": False,
        })

    try:
        output, _ = await run_in_threadpool(engine.mix, stems_for_mix, str(job_dir), 44100, 2)
    except AudioEngineError as e:
        raise HTTPException(500, str(e))

    return FileResponse(output, media_type="audio/mpeg", filename="mezcla.mp3")


@app.get("/api/search")
async def search_chords(artist: str = Query(""), title: str = Query("")):
    try:
        candidates = await run_in_threadpool(cifra.search, artist, title)
        return {
            "candidates": [
                {"url": c.url, "title": c.title, "version": c.version}
                for c in candidates
            ]
        }
    except Exception:
        return {"candidates": []}


@app.get("/api/chords/fetch")
async def fetch_chords(url: str = Query("")):
    try:
        from harmony import ChordCandidate
        candidates = await run_in_threadpool(cifra.search, "", "")
        match = next((c for c in candidates if c.url == url), None)
        if not match:
            match = ChordCandidate(url, url, "desconocida")
        chart = await run_in_threadpool(cifra.fetch, match)
        return {
            "key": chart.key_name or "",
            "scale": chart.scale or "",
            "sections": [
                {"title": s.title, "lines": [{"chords": l.chords} for l in s.lines]}
                for s in chart.sections
            ],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")


app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _progress(job_id: str, low: float, high: float, label: str):
    def cb(value: float, phase: str):
        pct = low + value * (high - low)
        _update(job_id, None, pct, f"{label}: {phase}")
    return cb


def _update(job_id: str, status: str | None, progress: float, phase: str, stems: list | None = None):
    with _job_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        if status:
            job["status"] = status
        job["progress"] = round(min(progress, 1.0), 3)
        job["phase"] = phase
        if stems is not None:
            job["stems"] = stems


def _cleanup(job_id: str):
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"
    shutil.rmtree(job_dir, ignore_errors=True)
    with _job_lock:
        _jobs.pop(job_id, None)
        _cancel_events.pop(job_id, None)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8745, log_level="info")
