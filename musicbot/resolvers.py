# Metadata resolvers for services yt-dlp can't stream (Spotify, Deezer, Apple Music).
# They read track names and artists, then each track is matched on YouTube when it plays,
# so even a large playlist queues instantly. Also: internet radio search via radio-browser.info.

import base64
import json
import re
import time
from urllib.parse import parse_qs, urlparse

import aiohttp

from . import config
from .sources import Track, SourceError

UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) DiscordMusicBot"}

SPOTIFY_RE = re.compile(r"open\.spotify\.com/(?:intl-[\w-]+/)?(?:embed/)?(track|album|playlist|artist)/(\w+)")
DEEZER_RE = re.compile(r"deezer\.com/(?:[a-z]{2}/)?(track|album|playlist)/(\d+)")
APPLE_RE = re.compile(r"music\.apple\.com/([a-z]{2})/(album|playlist|song)/(?:[^/?#]+/)?([^/?#]+)")
SHORT_LINK_HOSTS = ("spotify.link", "link.deezer.com", "deezer.page.link")

RADIO_SERVERS = ("https://de1.api.radio-browser.info", "https://fi1.api.radio-browser.info",
                 "https://de2.api.radio-browser.info")


def _track(title, artists, requester, duration_ms=None, url=None):
    artists = artists.replace("\xa0", " ").strip(", ")
    name = f"{artists} - {title}" if artists else title
    return Track(title=name, source=f"ytsearch1:{name} audio", url=url, requester=requester,
                 duration=int(duration_ms / 1000) if duration_ms else None)


class Resolver:
    def __init__(self):
        self._session = None
        self._spotify_token = (None, 0.0)

    @property
    def session(self):
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(headers=UA, timeout=aiohttp.ClientTimeout(total=20))
        return self._session

    async def close(self):
        if self._session:
            await self._session.close()

    async def _get_json(self, url, **kw):
        async with self.session.get(url, **kw) as r:
            if r.status != 200:
                return None
            return await r.json(content_type=None)

    async def _get_text(self, url):
        async with self.session.get(url) as r:
            r.raise_for_status()
            return await r.text()

    # ------------------------------------------------------------------ entry point

    async def resolve(self, query, requester=""):
        """Return tracks for a Spotify/Deezer/Apple Music link, or None if it isn't one."""
        if urlparse(query).hostname in SHORT_LINK_HOSTS:
            async with self.session.get(query) as r:
                query = str(r.url)
        try:
            if m := SPOTIFY_RE.search(query):
                tracks = await self._spotify(*m.groups(), requester)
            elif m := DEEZER_RE.search(query):
                tracks = await self._deezer(*m.groups(), requester)
            elif m := APPLE_RE.search(query):
                tracks = await self._apple(query, *m.groups(), requester)
            else:
                return None
        except aiohttp.ClientError as e:
            raise SourceError(f"couldn't reach the service ({e.__class__.__name__})") from None
        if not tracks:
            raise SourceError("that link has no playable tracks (it may be private or region locked)")
        return tracks[: config.MAX_TRACKS]

    # ------------------------------------------------------------------ Spotify

    async def _spotify(self, kind, sid, requester):
        tracks = None
        if config.SPOTIFY_CLIENT_ID and config.SPOTIFY_CLIENT_SECRET:
            tracks = await self._spotify_api(kind, sid, requester)
        if tracks is None:  # no credentials, or API refused (it needs a Premium app owner)
            tracks = await self._spotify_embed(kind, sid, requester)
        return tracks

    async def _spotify_auth(self):
        token, expires = self._spotify_token
        if token and time.time() < expires:
            return token
        creds = base64.b64encode(f"{config.SPOTIFY_CLIENT_ID}:{config.SPOTIFY_CLIENT_SECRET}".encode()).decode()
        async with self.session.post("https://accounts.spotify.com/api/token",
                                     data={"grant_type": "client_credentials"},
                                     headers={"Authorization": f"Basic {creds}"}) as r:
            if r.status != 200:
                return None
            data = await r.json()
        self._spotify_token = (data["access_token"], time.time() + data["expires_in"] - 60)
        return data["access_token"]

    async def _spotify_api(self, kind, sid, requester):
        token = await self._spotify_auth()
        if not token:
            return None
        headers = {"Authorization": f"Bearer {token}"}
        api = "https://api.spotify.com/v1"

        def make(t):
            if not t or not t.get("name"):
                return None
            return _track(t["name"], ", ".join(a["name"] for a in t.get("artists", [])), requester,
                          t.get("duration_ms"), (t.get("external_urls") or {}).get("spotify"))

        if kind == "track":
            data = await self._get_json(f"{api}/tracks/{sid}", headers=headers)
            return [make(data)] if data else None
        if kind == "artist":
            data = await self._get_json(f"{api}/artists/{sid}/top-tracks?market=US", headers=headers)
            return [make(t) for t in data["tracks"]] if data else None

        url = f"{api}/albums/{sid}/tracks?limit=50" if kind == "album" else f"{api}/playlists/{sid}/items?limit=100"
        tracks = []
        while url and len(tracks) < config.MAX_TRACKS:
            data = await self._get_json(url, headers=headers)
            if data is None:
                return None if not tracks else tracks
            for item in data.get("items", []):
                t = (item.get("item") or item.get("track")) if kind == "playlist" else item
                if tr := make(t):
                    tracks.append(tr)
            url = data.get("next")
        return tracks

    async def _spotify_embed(self, kind, sid, requester):
        # Spotify's embed player pages are public and include the track list (first ~100).
        html = await self._get_text(f"https://open.spotify.com/embed/{kind}/{sid}")
        m = re.search(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', html, re.S)
        if not m:
            raise SourceError("couldn't read that Spotify link")
        entity = json.loads(m.group(1))["props"]["pageProps"]["state"]["data"]["entity"]
        if kind == "track":
            artists = ", ".join(a["name"] for a in entity.get("artists", []))
            return [_track(entity["name"], artists, requester, entity.get("duration"),
                           f"https://open.spotify.com/track/{sid}")]
        return [
            _track(t["title"], t.get("subtitle", ""), requester, t.get("duration"),
                   "https://open.spotify.com/track/" + t["uri"].rsplit(":", 1)[-1])
            for t in entity.get("trackList", []) if t.get("isPlayable", True)
        ]

    # ------------------------------------------------------------------ Deezer (public API)

    async def _deezer(self, kind, did, requester):
        def make(t):
            return _track(t["title"], t["artist"]["name"], requester, t.get("duration", 0) * 1000, t.get("link"))

        if kind == "track":
            data = await self._get_json(f"https://api.deezer.com/track/{did}")
            return [make(data)] if data and "error" not in data else []
        url = f"https://api.deezer.com/{kind}/{did}/tracks?limit=100"
        tracks = []
        while url and len(tracks) < config.MAX_TRACKS:
            data = await self._get_json(url)
            if not data or "error" in data:
                break
            tracks += [make(t) for t in data.get("data", []) if t.get("readable", True)]
            url = data.get("next")
        return tracks

    # ------------------------------------------------------------------ Apple Music

    async def _apple(self, url, country, kind, aid, requester):
        def make(r):
            return _track(r["trackName"], r["artistName"], requester, r.get("trackTimeMillis"), r.get("trackViewUrl"))

        song_id = parse_qs(urlparse(url).query).get("i", [None])[0] or (aid if kind == "song" else None)
        if song_id or kind == "album":
            lookup = f"https://itunes.apple.com/lookup?id={song_id or aid}&country={country}"
            if not song_id:
                lookup += "&entity=song&limit=200"
            data = await self._get_json(lookup)
            return [make(r) for r in (data or {}).get("results", []) if r.get("wrapperType") == "track"]

        # Playlists have no public API; read the track list embedded in the web page.
        html = await self._get_text(url)
        m = re.search(r'id="serialized-server-data">(.*?)</script>', html, re.S)
        if not m:
            return []
        tracks = []

        def walk(o):
            if isinstance(o, dict):
                if str(o.get("id", "")).startswith("track-lockup") and o.get("title") and o.get("artistName"):
                    tracks.append(_track(o["title"], o["artistName"], requester))
                    return
                for v in o.values():
                    walk(v)
            elif isinstance(o, list):
                for v in o:
                    walk(v)

        walk(json.loads(m.group(1)))
        return tracks

    # ------------------------------------------------------------------ Internet radio

    async def search_radio(self, name, limit=5):
        params = {"name": name, "limit": limit, "hidebroken": "true", "order": "clickcount", "reverse": "true"}
        for server in RADIO_SERVERS:
            try:
                data = await self._get_json(f"{server}/json/stations/search", params=params)
            except aiohttp.ClientError:
                continue
            if data is not None:
                return data
        raise SourceError("the radio directory is unreachable right now")

    @staticmethod
    def radio_track(station, requester=""):
        return Track(title=station["name"].strip()[:200], source=station["url_resolved"] or station["url"],
                     url=station.get("homepage") or None, requester=requester, direct=True, is_live=True)
