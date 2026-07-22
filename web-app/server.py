#!/usr/bin/env python3
"""Split Tracks — web server for macOS / Windows / Linux."""

from __future__ import annotations

import json, logging, shutil, sys, threading, uuid
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.concurrency import run_in_threadpool

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from engine import (AudioEngineError, SeparationCancelled, SeparationEngine, STEM_LABELS, STEM_ORDER)
from harmony import ChordCandidate, ChordChart, CifraClubProvider, HarmonyError, guess_artist_title
from analysis import AudioAnalysis, analyze_audio, transpose_note_name

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
_log = logging.getLogger("split-tracks")

STATIC_DIR = Path(__file__).resolve().parent / "static"
JOBS_DIR = Path.home() / "Split Tracks"
JOBS_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Split Tracks", version="2.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

engine = SeparationEngine()
cifra = CifraClubProvider()
_jobs: dict[str, dict] = {}
_job_lock = threading.Lock()
_cancel_events: dict[str, threading.Event] = {}


@app.get("/health")
def health():
    return {"status": "ok", "name": "Split Tracks", "version": "2.0.0"}


# ── Job creation ──────────────────────────────────────────────

@app.post("/api/jobs")
async def create_job(file: UploadFile | None = File(None), url: str | None = Form(None), stems: str | None = Form(None)):
    selected = json.loads(stems) if stems else list(STEM_ORDER)
    selected = [s for s in selected if s in STEM_ORDER]
    job_id = str(uuid.uuid4())[:8]
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"
    job_dir.mkdir(parents=True, exist_ok=True)
    cancel = threading.Event()

    with _job_lock:
        _cancel_events[job_id] = cancel
        _jobs[job_id] = {"id": job_id, "status": "uploading", "progress": 0, "phase": "Recibiendo...", "stems": [], "pitch": 0}

    if file:
        tmp = job_dir / f"input_{file.filename or 'audio'}"
        with open(tmp, "wb") as f:
            while True:
                chunk = await file.read(1_048_576)
                if not chunk: break
                f.write(chunk)
        audio_path, artist, title = tmp, "", Path(file.filename or "audio").stem
    elif url:
        audio_path, artist, title = None, "", ""
    else:
        raise HTTPException(400, "Archivo o URL requerido")

    threading.Thread(target=_process_job, args=(job_id, audio_path if file else None, url if not file else None, artist, title, selected, cancel, job_dir), daemon=True).start()
    return {"id": job_id, "status": "uploading"}


def _progress(job_id: str, low: float, high: float, label: str):
    def cb(value: float, phase: str):
        _update(job_id, None, low + value * (high - low), f"{label}: {phase}")
    return cb


def _update(job_id: str, status: str | None, progress: float, phase: str, stems: list | None = None, **extra):
    with _job_lock:
        job = _jobs.get(job_id)
        if not job: return
        if status: job["status"] = status
        job["progress"] = round(min(progress, 1.0), 3)
        job["phase"] = phase
        if stems is not None: job["stems"] = stems
        for k, v in extra.items(): job[k] = v


def _cleanup(job_id: str):
    shutil.rmtree(JOBS_DIR / f"Split Tracks - {job_id}", ignore_errors=True)
    with _job_lock:
        _jobs.pop(job_id, None)
        _cancel_events.pop(job_id, None)


def _process_job(job_id, audio_path, url, artist, title, selected, cancel, job_dir):
    try:
        if url:
            _update(job_id, "downloading", 0.1, "Descargando YouTube...")
            result = engine.download_youtube(url, progress=_progress(job_id, 0.1, 0.4, "YouTube"), cancel_event=cancel)
            audio_path = result.path
            artist, title = guess_artist_title(result.title, fallback_artist=result.artist)
            if not artist and result.artist: artist = result.artist

        _update(job_id, "analyzing", 0.4, "Analizando...")
        try:
            info = engine.probe(audio_path)
            analysis = analyze_audio(audio_path, cancel_event=cancel)
        except Exception:
            analysis = None
            info = engine.probe(audio_path)

        _update(job_id, "separating", 0.5, "Separando con Demucs...")
        result = engine.separate(audio_path, job_dir, tuple(selected), progress=_progress(job_id, 0.5, 0.95, "Demucs"), cancel_event=cancel)

        stems_data = [{"name": s.name, "file": str(s.path.relative_to(job_dir)), "color": s.color, "kind": s.kind} for s in result.stems]

        chart_info = {}
        if artist and title:
            try:
                candidates = cifra.search(artist, title)
                if candidates:
                    chart = cifra.fetch(candidates[0])
                    chart_info = _chart_to_dict(chart)
                    analysis_dict["chord_count"] = chart.chord_count
            except Exception as e:
                _log.warning("Chord fetch failed: %s", e)

        analysis_dict = _analysis_to_dict(analysis, info)
        _update(job_id, "done", 1.0, "Listo", stems=stems_data, **analysis_dict, chart=chart_info, artist=artist, title=title)

    except SeparationCancelled:
        _cleanup(job_id)
    except AudioEngineError as e:
        _update(job_id, "error", 0, str(e))
    except Exception as e:
        _update(job_id, "error", 0, f"Error: {e}")


# ── Job status ────────────────────────────────────────────────

@app.get("/api/jobs/{job_id}")
def get_job(job_id: str):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job: raise HTTPException(404)
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str):
    with _job_lock:
        cancel = _cancel_events.get(job_id)
    if cancel: cancel.set()
    return {"ok": True}


@app.get("/api/jobs/{job_id}/stems/{stem_file:path}")
def serve_stem(job_id: str, stem_file: str):
    p = JOBS_DIR / f"Split Tracks - {job_id}" / stem_file
    if not p.exists(): raise HTTPException(404)
    return FileResponse(p, media_type="audio/wav")


@app.get("/api/jobs/{job_id}/stems-mp3/{stem_file:path}")
async def serve_stem_mp3(job_id: str, stem_file: str):
    p = JOBS_DIR / f"Split Tracks - {job_id}" / stem_file
    if not p.exists(): raise HTTPException(404)
    mp3 = p.with_suffix(".mp3")
    if not mp3.exists():
        await run_in_threadpool(engine._render_audio, (p,), mp3, 44100, 2)
    return FileResponse(mp3, media_type="audio/mpeg", filename=p.stem + ".mp3")


# ── Chords ────────────────────────────────────────────────────

@app.get("/api/chords/search")
def search_chords(artist: str = Query(""), title: str = Query("")):
    try:
        candidates = cifra.search(artist, title)
        return {"candidates": [{
            "url": c.url, "source": c.source_name, "version": c.version,
            "artist": c.artist, "title": c.title,
            "key": c.key_name or "", "scale": c.scale or "",
            "capo": c.capo, "instrument": c.instrument,
            "reviewed": c.reviewed, "rating": c.rating, "votes": c.votes,
        } for c in candidates]}
    except Exception as e:
        return {"candidates": [], "error": str(e)}


@app.get("/api/chords/fetch")
def fetch_chords(url: str = Query("")):
    try:
        # Create a minimal candidate from URL
        c = ChordCandidate("cifra", "Cifra Club", url, "", "", url.split("/")[-2] if "/" in url else "")
        chart = cifra.fetch(c)
        return {"chart": _chart_to_dict(chart)}
    except HarmonyError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))


@app.post("/api/chords/transpose")
async def transpose_chords(request: dict = None):
    body = request or {}
    url = body.get("url", "")
    semitones = body.get("semitones", 0)
    try:
        c = ChordCandidate("cifra", "Cifra Club", url, "", "", url.split("/")[-2] if "/" in url else "")
        chart = cifra.fetch(c)
        transposed = chart.transposed_sections(semitones)
        degrees = chart.degrees(semitones)
        return {
            "url": url,
            "key": chart.transposed_key(semitones) or chart.display_key or "",
            "scale": chart.scale or "",
            "sections": [_section_to_dict(s) for s in transposed],
            "degrees": [_section_to_dict(s, use_degrees=True) for s in degrees],
        }
    except Exception as e:
        raise HTTPException(500, str(e))


# ── Pitch / Transpose ─────────────────────────────────────────

@app.post("/api/jobs/{job_id}/pitch")
async def set_pitch(job_id: str, request: dict = None):
    body = request or {}
    semitones = body.get("semitones", 0)
    with _job_lock:
        job = _jobs.get(job_id)
        if not job: raise HTTPException(404)
        job["pitch"] = semitones

    if job.get("chart", {}).get("url"):
        try:
            chart_data = job["chart"]
            c = ChordCandidate("cifra", "Cifra Club", chart_data["url"], "", "", "")
            chart = cifra.fetch(c)
            transposed = chart.transposed_sections(semitones)
            degrees = chart.degrees(semitones)
            return {
                "semitones": semitones,
                "key": chart.transposed_key(semitones) or chart.display_key or "",
                "sections": [_section_to_dict(s) for s in transposed],
                "degrees": [_section_to_dict(s, use_degrees=True) for s in degrees],
            }
        except Exception:
            pass

    # Fallback: transpose from analysis
    analysis_key = job.get("key_name", "")
    if analysis_key:
        new_key = transpose_note_name(analysis_key, semitones) or analysis_key
    else:
        new_key = ""
    return {"semitones": semitones, "key": new_key, "sections": [], "degrees": []}


# ── Export ────────────────────────────────────────────────────

@app.post("/api/jobs/{job_id}/export/mix")
async def export_mix(job_id: str, request: dict = None):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job or not job.get("stems"): raise HTTPException(400)
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"
    body = request or {}
    stems = body.get("stems", job["stems"])
    stems_for_mix = [{"name": s["name"], "path": str(job_dir / s["file"]), "volume": s.get("volume", 1), "mute": s.get("mute", False), "solo": s.get("solo", False)} for s in stems]
    try:
        output, _ = await run_in_threadpool(engine.mix, stems_for_mix, str(job_dir), 44100, 2)
        return FileResponse(output, media_type="audio/mpeg", filename="mezcla.mp3")
    except AudioEngineError as e:
        raise HTTPException(500, str(e))


@app.post("/api/jobs/{job_id}/export/stems")
async def export_stems(job_id: str, request: dict = None):
    with _job_lock:
        job = _jobs.get(job_id)
    if not job or not job.get("stems"): raise HTTPException(400)
    job_dir = JOBS_DIR / f"Split Tracks - {job_id}"
    body = request or {}
    stems = body.get("stems", [])
    paths = []
    for s in stems:
        p = job_dir / s["file"]
        if p.exists():
            mp3 = p.with_suffix(".mp3")
            if not mp3.exists():
                await run_in_threadpool(engine._render_audio, (p,), mp3, 44100, 2)
            paths.append({"name": s["name"], "url": f"/api/jobs/{job_id}/stems-mp3/{s['file']}"})
    return {"files": paths}


# ── Helpers ───────────────────────────────────────────────────

def _chart_to_dict(chart: ChordChart) -> dict:
    return {
        "url": chart.url, "source": chart.source_name, "version": chart.version,
        "artist": chart.artist, "title": chart.title,
        "key": chart.key_name or "", "scale": chart.scale or "",
        "capo": chart.capo, "instrument": chart.instrument, "reviewed": chart.reviewed,
        "sections": [_section_to_dict(s) for s in chart.sections],
        "display_key": chart.display_key or "",
    }


def _section_to_dict(s, use_degrees=False) -> dict:
    return {
        "title": s.title,
        "lines": [{"chords": list(l.chords), "bars": l.bars} for l in s.lines],
    }


def _analysis_to_dict(analysis: AudioAnalysis | None, info) -> dict:
    if analysis is None:
        return {}
    return {
        "bpm": round(analysis.bpm, 1) if analysis.bpm is not None else 0,
        "key_name": analysis.key_name or "",
        "key_confidence": round(analysis.key_confidence * 100) if analysis.key_confidence is not None else 0,
        "scale": analysis.scale or "",
        "lufs": round(analysis.lufs, 1) if analysis.lufs is not None else 0,
        "dynamic_range_db": round(analysis.dynamic_range_db, 1) if analysis.dynamic_range_db is not None else 0,
        "peak_dbfs": round(analysis.peak_dbfs, 1) if analysis.peak_dbfs is not None else 0,
        "tempo_confidence": round(analysis.tempo_confidence * 100) if analysis.tempo_confidence is not None else 0,
        "format_name": info.format_name if info else "",
        "sample_rate_label": info.sample_rate_label if info else "",
        "channels": info.channels if info else 0,
        "duration_label": info.duration_label if info else "",
        "channel_layout": info.channel_layout if info else "",
    }


# ── Static files ──────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
def index():
    return FileResponse(STATIC_DIR / "index.html")

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8745, log_level="info")
