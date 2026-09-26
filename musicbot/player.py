# One GuildPlayer per server: owns the queue and plays tracks one after another.

import asyncio
import logging
import random
import time
from collections import deque

import discord

from . import config
from .sources import SourceError, resolve_stream
from .utils import fmt_duration, track_link

log = logging.getLogger(__name__)

FFMPEG_BEFORE = "-nostdin -reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5"


class GuildPlayer:
    def __init__(self, bot, guild, on_destroy):
        self.bot = bot
        self.guild = guild
        self.text_channel = None
        self.queue = deque()
        self.current = None
        self.loop_mode = "off"  # off | track | queue
        self.volume = config.DEFAULT_VOLUME / 100
        self._on_destroy = on_destroy
        self._wake = asyncio.Event()
        self._finished = asyncio.Event()
        self._skipped = False
        self._stopped = False
        self._started = 0.0
        self._paused_at = None
        self._destroyed = False
        self._task = asyncio.create_task(self._run())

    @property
    def voice(self):
        return self.guild.voice_client

    @property
    def position(self):
        """Seconds into the current track."""
        if not self.current:
            return 0
        end = self._paused_at or time.monotonic()
        return int(end - self._started)

    # ------------------------------------------------------------------ queue control

    def add(self, tracks, front=False):
        if front:
            self.queue.extendleft(reversed(tracks))
        else:
            self.queue.extend(tracks)
        self._wake.set()

    def skip(self):
        self._skipped = True
        if self.voice:
            self.voice.stop()  # triggers the after-callback, which advances the queue

    def stop(self):
        self.queue.clear()
        self._stopped = True
        self.skip()

    def shuffle(self):
        items = list(self.queue)
        random.shuffle(items)
        self.queue = deque(items)

    def pause(self):
        if self.voice and self.voice.is_playing():
            self.voice.pause()
            self._paused_at = time.monotonic()
            return True
        return False

    def resume(self):
        if self.voice and self.voice.is_paused():
            self.voice.resume()
            self._started += time.monotonic() - self._paused_at
            self._paused_at = None
            return True
        return False

    def set_volume(self, percent):
        self.volume = percent / 100
        if self.voice and isinstance(self.voice.source, discord.PCMVolumeTransformer):
            self.voice.source.volume = self.volume

    # ------------------------------------------------------------------ playback loop

    async def _next_track(self):
        while not self.queue:
            self._wake.clear()
            try:
                await asyncio.wait_for(self._wake.wait(), config.IDLE_TIMEOUT)
            except asyncio.TimeoutError:
                return None
        return self.queue.popleft()

    async def _run(self):
        try:
            while True:
                track = await self._next_track()
                if track is None:
                    await self.say("Queue has been empty for a while, leaving the voice channel. 👋")
                    return
                if not self.voice or not self.voice.is_connected():
                    return
                try:
                    stream_url, headers = await resolve_stream(track)
                except SourceError as e:
                    await self.say(f"⚠️ Skipping **{discord.utils.escape_markdown(track.title)}**: {e}")
                    continue

                before = FFMPEG_BEFORE
                if headers:
                    header_str = "".join(f"{k}: {v}\r\n" for k, v in headers.items())
                    before += f' -headers "{header_str}"'
                audio = discord.FFmpegPCMAudio(stream_url, executable=config.FFMPEG,
                                               before_options=before, options="-vn")
                source = discord.PCMVolumeTransformer(audio, volume=self.volume)

                self._finished.clear()
                self._skipped = self._stopped = False
                self.current = track
                self._started, self._paused_at = time.monotonic(), None
                try:
                    self.voice.play(source, after=self._after)
                except discord.ClientException:  # disconnected between checks
                    return
                await self.say(embed=self.now_playing_embed(title="Now playing"))
                await self._finished.wait()

                self.current = None
                if self.loop_mode == "track" and not self._skipped:
                    self.queue.appendleft(track.copy())
                elif self.loop_mode == "queue" and not self._stopped:
                    self.queue.append(track.copy())
        except asyncio.CancelledError:
            pass
        except Exception:
            log.exception("Player loop crashed in guild %s", self.guild.id)
        finally:
            await self.destroy()

    def _after(self, error):
        if error:
            log.warning("Playback error in guild %s: %s", self.guild.id, error)
        self.bot.loop.call_soon_threadsafe(self._finished.set)

    async def destroy(self):
        if self._destroyed:
            return
        self._destroyed = True
        self.queue.clear()
        if self.voice:
            await self.voice.disconnect(force=True)
        if self._task is not asyncio.current_task():
            self._task.cancel()
        self._on_destroy(self)

    # ------------------------------------------------------------------ messages

    async def say(self, content=None, **kw):
        if self.text_channel:
            try:
                await self.text_channel.send(content, **kw)
            except discord.HTTPException:
                pass

    def now_playing_embed(self, title="Now playing"):
        t = self.current
        embed = discord.Embed(title=title, description=track_link(t), color=discord.Color.blurple())
        if t.is_live:
            embed.add_field(name="Duration", value="🔴 Live")
        elif t.duration:
            pos = min(self.position, t.duration)
            filled = int(20 * pos / t.duration)
            bar = "▬" * filled + "🔘" + "▬" * (20 - filled)
            embed.add_field(name="Progress", value=f"{bar}\n`{fmt_duration(pos)} / {fmt_duration(t.duration)}`",
                            inline=False)
        if t.requester:
            embed.add_field(name="Requested by", value=t.requester)
        if self.loop_mode != "off":
            embed.add_field(name="Loop", value=self.loop_mode)
        if self.queue:
            embed.set_footer(text=f"{len(self.queue)} more in queue · up next: {self.queue[0].title[:80]}")
        return embed
