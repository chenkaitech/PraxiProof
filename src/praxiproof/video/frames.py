import json
import subprocess
from pathlib import Path

from pydantic import BaseModel


class VideoMeta(BaseModel):
    duration: float
    fps: float
    width: int
    height: int
    codec: str
    format_name: str


class FFmpegError(RuntimeError):
    pass


def probe(path: Path) -> VideoMeta:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-print_format", "json", "-show_format", "-show_streams", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise FFmpegError(f"ffprobe failed for {path.name}: {result.stderr.strip()[:300]}")
    info = json.loads(result.stdout)
    stream = next((s for s in info.get("streams", []) if s.get("codec_type") == "video"), None)
    if stream is None:
        raise FFmpegError(f"{path.name} has no video stream")
    num, _, den = stream.get("avg_frame_rate", "0/1").partition("/")
    fps = float(num) / float(den or 1) if float(den or 1) else 0.0
    duration = float(stream.get("duration") or info["format"].get("duration") or 0.0)
    return VideoMeta(
        duration=duration,
        fps=fps or 30.0,
        width=int(stream.get("width", 0)),
        height=int(stream.get("height", 0)),
        codec=stream.get("codec_name", "unknown"),
        format_name=info["format"].get("format_name", "unknown").split(",")[0],
    )


def frame_at(path: Path, seconds: float, width: int = 640) -> bytes:
    result = subprocess.run(
        [
            "ffmpeg", "-v", "error", "-ss", f"{max(seconds, 0.0):.3f}", "-i", str(path),
            "-frames:v", "1", "-vf", f"scale={width}:-2", "-f", "image2", "-c:v", "mjpeg", "-q:v", "4", "pipe:1",
        ],
        capture_output=True,
    )
    if result.returncode != 0 or not result.stdout:
        raise FFmpegError(f"could not extract frame at {seconds:.2f}s: {result.stderr.decode(errors='ignore')[:300]}")
    return result.stdout


def sample_times(start: float, end: float, count: int) -> list[float]:
    if count <= 1 or end <= start:
        return [round(start, 3)]
    step = (end - start) / count
    return [round(start + step * (i + 0.5), 3) for i in range(count)]
