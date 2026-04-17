from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import yt_dlp
import uuid
import os
import shutil
import threading
import zipfile
from pathlib import Path
from typing import Dict, Any

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DOWNLOADS_DIR = Path(os.getenv("DOWNLOADS_DIR", "/app/downloads"))
DOWNLOADS_DIR.mkdir(exist_ok=True)

tasks: Dict[str, Dict[str, Any]] = {}


class InfoRequest(BaseModel):
    url: str


class DownloadRequest(BaseModel):
    url: str
    format_type: str  # "video" or "audio"
    quality: str


@app.post("/api/info")
async def get_info(request: InfoRequest):
    try:
        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": "in_playlist",
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(request.url, download=False)

        if "entries" in info:
            entries = [e for e in info["entries"] if e]
            return {
                "type": "playlist",
                "title": info.get("title", "Playlist"),
                "count": len(entries),
                "entries": [
                    {
                        "title": e.get("title", "Unknown"),
                        "duration": e.get("duration", 0),
                        "thumbnail": e.get("thumbnail", ""),
                    }
                    for e in entries[:20]
                ],
                "video_qualities": ["best", "1080", "720", "480", "360"],
                "audio_qualities": ["best", "320", "192", "128"],
            }
        else:
            # For single video, re-fetch with full format info
            full_opts = {"quiet": True, "no_warnings": True}
            with yt_dlp.YoutubeDL(full_opts) as ydl:
                info = ydl.extract_info(request.url, download=False)

            formats = info.get("formats", [])
            video_heights = sorted(
                set(
                    f.get("height")
                    for f in formats
                    if f.get("height") and f.get("vcodec", "none") != "none"
                ),
                reverse=True,
            )
            video_qualities = [str(h) for h in video_heights if h]
            if not video_qualities:
                video_qualities = ["best"]
            else:
                video_qualities = ["best"] + video_qualities

            return {
                "type": "video",
                "title": info.get("title", ""),
                "duration": info.get("duration", 0),
                "thumbnail": info.get("thumbnail", ""),
                "uploader": info.get("uploader", ""),
                "view_count": info.get("view_count", 0),
                "video_qualities": video_qualities,
                "audio_qualities": ["best", "320", "192", "128"],
            }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


def build_ydl_opts(format_type: str, quality: str, output_dir: Path, progress_hook):
    if format_type == "audio":
        audio_quality = quality if quality != "best" else "192"
        return {
            "format": "bestaudio/best",
            "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
            "postprocessors": [
                {
                    "key": "FFmpegExtractAudio",
                    "preferredcodec": "mp3",
                    "preferredquality": audio_quality,
                }
            ],
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }
    else:
        if quality == "best":
            fmt = "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best"
        else:
            fmt = (
                f"bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]"
                f"/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best"
            )
        return {
            "format": fmt,
            "outtmpl": str(output_dir / "%(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks": [progress_hook],
            "quiet": True,
            "no_warnings": True,
        }


def sanitize_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in " ._-").strip() or "download"


def run_download(task_id: str, url: str, format_type: str, quality: str):
    task_dir = DOWNLOADS_DIR / task_id
    task_dir.mkdir(exist_ok=True)
    tasks[task_id].update({"status": "downloading", "progress": 0})

    downloaded_count = [0]
    total_count = [1]

    def progress_hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            downloaded = d.get("downloaded_bytes", 0)
            if total:
                file_progress = downloaded / total
                base = (downloaded_count[0] / total_count[0]) * 100
                add = (file_progress / total_count[0]) * 100
                tasks[task_id]["progress"] = min(int(base + add), 99)
        elif d["status"] == "finished":
            downloaded_count[0] += 1
            tasks[task_id]["progress"] = min(
                int((downloaded_count[0] / total_count[0]) * 100), 99
            )

    try:
        check_opts = {"quiet": True, "no_warnings": True, "extract_flat": "in_playlist"}
        with yt_dlp.YoutubeDL(check_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        is_playlist = "entries" in info

        if is_playlist:
            entries = [e for e in info["entries"] if e]
            total_count[0] = max(len(entries), 1)
            tasks[task_id]["total"] = len(entries)

            ydl_opts = build_ydl_opts(format_type, quality, task_dir, progress_hook)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            files = list(task_dir.glob("*"))
            if not files:
                raise Exception("No files downloaded")

            playlist_title = sanitize_filename(info.get("title", "playlist"))
            zip_name = f"{playlist_title}.zip"
            zip_path = task_dir / zip_name

            with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
                for f in files:
                    zf.write(f, f.name)
            for f in files:
                f.unlink()

            tasks[task_id].update(
                {"status": "complete", "progress": 100, "filename": zip_name}
            )
        else:
            ydl_opts = build_ydl_opts(format_type, quality, task_dir, progress_hook)
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            files = list(task_dir.glob("*"))
            if not files:
                raise Exception("No file found after download")

            tasks[task_id].update(
                {"status": "complete", "progress": 100, "filename": files[0].name}
            )

    except Exception as e:
        tasks[task_id].update({"status": "error", "error": str(e)})
        shutil.rmtree(str(task_dir), ignore_errors=True)


@app.post("/api/download")
async def start_download(request: DownloadRequest):
    task_id = str(uuid.uuid4())
    tasks[task_id] = {
        "status": "pending",
        "progress": 0,
        "filename": None,
        "error": None,
        "total": 1,
    }
    thread = threading.Thread(
        target=run_download,
        args=(task_id, request.url, request.format_type, request.quality),
        daemon=True,
    )
    thread.start()
    return {"task_id": task_id}


@app.get("/api/status/{task_id}")
async def get_status(task_id: str):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")
    return tasks[task_id]


@app.get("/api/file/{task_id}")
async def get_file(task_id: str, background_tasks: BackgroundTasks):
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="Task not found")

    task = tasks[task_id]
    if task["status"] != "complete":
        raise HTTPException(status_code=400, detail="File not ready")

    task_dir = DOWNLOADS_DIR / task_id
    filename = task["filename"]
    file_path = task_dir / filename

    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    def cleanup():
        shutil.rmtree(str(task_dir), ignore_errors=True)
        tasks.pop(task_id, None)

    background_tasks.add_task(cleanup)

    return FileResponse(
        path=str(file_path),
        filename=filename,
        media_type="application/octet-stream",
    )
