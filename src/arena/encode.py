"""ffmpeg wrapper: raw RGB frames from stdin + WAV -> Instagram-ready MP4."""
from __future__ import annotations

import subprocess
from pathlib import Path

import imageio_ffmpeg

from .config import ASSETS


def ffmpeg_exe() -> str:
    return imageio_ffmpeg.get_ffmpeg_exe()


def _music_file() -> Path | None:
    files = sorted(p for p in (ASSETS / "music").glob("*") if p.suffix.lower() in {".mp3", ".wav", ".ogg", ".m4a", ".flac"})
    return files[0] if files else None


class VideoWriter:
    def __init__(self, out: Path, wav: Path, w: int, h: int, fps: int, crf: int = 19, preset: str = "veryfast",
                 music_volume: float = 0.35):
        cmd = [ffmpeg_exe(), "-y", "-loglevel", "error",
               "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}", "-r", str(fps), "-i", "-",
               "-i", str(wav)]
        music = _music_file()
        if music:
            cmd += ["-stream_loop", "-1", "-i", str(music),
                    "-filter_complex",
                    f"[2:a]volume={music_volume}[m];[1:a][m]amix=inputs=2:duration=first:normalize=0[a]",
                    "-map", "0:v", "-map", "[a]"]
        else:
            cmd += ["-map", "0:v", "-map", "1:a"]
        cmd += ["-c:v", "libx264", "-preset", preset, "-crf", str(crf), "-pix_fmt", "yuv420p",
                "-profile:v", "high", "-level", "4.2", "-g", str(fps * 2),
                "-c:a", "aac", "-b:a", "192k", "-ar", "48000",
                "-movflags", "+faststart", "-shortest", str(out)]
        self.proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)

    def write(self, data: bytes):
        assert self.proc.stdin is not None
        self.proc.stdin.write(data)

    def close(self):
        assert self.proc.stdin is not None
        self.proc.stdin.close()
        code = self.proc.wait()
        if code != 0:
            raise RuntimeError(f"ffmpeg failed with exit code {code}")


def probe(path: Path) -> str:
    """Return ffmpeg's stream description (used by tests / verification)."""
    r = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True)
    return r.stderr
