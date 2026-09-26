# Turns user input (search terms or links) into Track objects and resolves playable
# stream URLs with yt-dlp. yt-dlp covers YouTube, YouTube Music, SoundCloud, Bandcamp,
# Mixcloud, Vimeo, Twitch, direct audio links and Discord attachments.

import asyncio
import dataclasses
from dataclasses import dataclass, field

import yt_dlp

from . import config

YTDL_OPTS = {
    "format": "bestaudio/best",
    "quiet": True,
    "no_warnings": True,
    "noplaylist": True,
    "default_search": "ytsearch",
    "source_address": "0.0.0.0",
    "extract_flat": "in_playlist",  # list playlist entries without resolving each one
    "playlistend": config.MAX_TRACKS,
}
if config.DENO:
    YTDL_OPTS["js_runtimes"] = {"deno": {"path": config.DENO}}


@dataclass
class Track:
    title: str
    source: str                   # URL or "ytsearch1:..." query handed to yt-dlp
    url: str | None = None        # page link shown in chat
    duration: int | None = None   # seconds; None for live streams
    requester: str = ""
    direct: bool = False          # source is already a raw stream (radio) – skip yt-dlp
    is_live: bool = False
    _stream: tuple | None = field(default=None, repr=False)  # pre-resolved (url, headers), used once

    def copy(self):
        return dataclasses.replace(self, _stream=None)

    def to_dict(self):
        return {"title": self.title, "source": self.source, "url": self.url,
                "duration": self.duration, "direct": self.direct, "is_live": self.is_live}

    @classmethod
    def from_dict(cls, d, requester=""):
        return cls(title=d["title"], source=d["source"], url=d.get("url"), duration=d.get("duration"),
                   direct=d.get("direct", False), is_live=d.get("is_live", False), requester=requester)


class SourceError(Exception):
    pass


def _extract(query, **overrides):
    opts = {**YTDL_OPTS, **overrides}
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(query, download=False)
    except yt_dlp.utils.DownloadError as e:
        raise SourceError(str(e).removeprefix("ERROR: ").split("\n")[0][:300]) from None


def _duration(info):
    d = info.get("duration")
    return int(d) if d else None


def _track_from_info(info, requester):
    url = info.get("webpage_url") or info.get("original_url") or info.get("url")
    track = Track(
        title=info.get("title") or url,
        source=url,
        url=url if url and url.startswith("http") else None,
        duration=_duration(info),
        requester=requester,
        is_live=bool(info.get("is_live")),
    )
    if info.get("url") and info.get("url") != url:  # full extraction: keep the stream for the first play
        track._stream = (info["url"], info.get("http_headers") or {})
    return track


async def load(query, requester=""):
    """Search or load a URL. Returns a list of tracks (several for playlists)."""
    if not query.startswith(("http://", "https://")):
        query = f"ytsearch1:{query}"
    info = await asyncio.to_thread(_extract, query)
    if info is None:
        return []
    if "entries" in info:
        entries = [e for e in info["entries"] if e]
        return [_track_from_info(e, requester) for e in entries[: config.MAX_TRACKS]]
    return [_track_from_info(info, requester)]


async def search(query, limit=5, requester=""):
    info = await asyncio.to_thread(_extract, f"ytsearch{limit}:{query}")
    return [_track_from_info(e, requester) for e in (info or {}).get("entries", []) if e]


async def resolve_stream(track):
    """Return (stream_url, http_headers) for a track, resolving it with yt-dlp if needed."""
    if track.direct:
        return track.source, {}
    if track._stream:
        stream, track._stream = track._stream, None
        return stream
    info = await asyncio.to_thread(_extract, track.source, extract_flat=False)
    if info and "entries" in info:  # a search query returns a one-item playlist
        info = next((e for e in info["entries"] if e), None)
    if not info or not info.get("url"):
        raise SourceError("no playable audio found")
    # Metadata-only tracks (Spotify, Deezer, ...) get a real link once matched.
    track.url = info.get("webpage_url") or track.url
    track.duration = track.duration or _duration(info)
    track.is_live = bool(info.get("is_live"))
    return info["url"], info.get("http_headers") or {}
