# Settings are read from the .env file in the project root (see .env.example).

import os
import shutil
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN", "")
PREFIX = os.getenv("COMMAND_PREFIX", "$")

# Optional. Spotify's Web API only works if the app owner has Premium; without it
# the bot falls back to reading Spotify's public embed pages.
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID", "")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET", "")

IDLE_TIMEOUT = int(os.getenv("IDLE_TIMEOUT", "300"))        # seconds with an empty queue before leaving
ALONE_TIMEOUT = int(os.getenv("ALONE_TIMEOUT", "60"))       # seconds alone in a voice channel before leaving
DEFAULT_VOLUME = int(os.getenv("DEFAULT_VOLUME", "50"))     # percent
MAX_TRACKS = int(os.getenv("MAX_TRACKS", "500"))            # cap when loading a playlist/album

DATA_DIR = ROOT / "data"


def _find_exe(name):
    # Prefer a copy in the project folder or the venv's Scripts/bin folder, then PATH.
    exe = name + (".exe" if os.name == "nt" else "")
    for folder in (ROOT, Path(sys.executable).parent):
        if (folder / exe).exists():
            return str(folder / exe)
    return shutil.which(name)


FFMPEG = _find_exe("ffmpeg") or "ffmpeg"
DENO = _find_exe("deno")  # yt-dlp needs a JS runtime to read YouTube
