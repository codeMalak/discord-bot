import asyncio
from typing import Literal, Optional

import discord
from discord.ext import commands

from .. import config, sources
from ..player import GuildPlayer
from ..resolvers import Resolver
from ..sources import SourceError
from ..utils import MusicError, PickView, fmt_duration, track_link

PAGE_SIZE = 10


class Music(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.players: dict[int, GuildPlayer] = {}
        self.resolver = Resolver()
        self._alone_timers: dict[int, asyncio.Task] = {}

    async def cog_unload(self):
        for player in list(self.players.values()):
            await player.destroy()
        await self.resolver.close()

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    # ------------------------------------------------------------------ helpers

    async def _connect(self, ctx):
        """Join (or move to) the author's voice channel."""
        state = ctx.author.voice
        if not state or not state.channel:
            raise MusicError("Join a voice channel first.")
        vc = ctx.voice_client
        if vc is None:
            await state.channel.connect(self_deaf=True)
        elif vc.channel != state.channel:
            listeners = [m for m in vc.channel.members if not m.bot]
            if (vc.is_playing() or vc.is_paused()) and listeners:
                raise MusicError(f"I'm already playing in {vc.channel.mention}.")
            await vc.move_to(state.channel)

    def _player(self, ctx, create=False):
        player = self.players.get(ctx.guild.id)
        if player is None and create:
            player = GuildPlayer(self.bot, ctx.guild, on_destroy=self._forget)
            self.players[ctx.guild.id] = player
        if player:
            player.text_channel = ctx.channel
        return player

    def _forget(self, player):
        if self.players.get(player.guild.id) is player:
            del self.players[player.guild.id]

    def _active(self, ctx):
        """The player, provided something is loaded and the author is listening with the bot."""
        player = self._player(ctx)
        if not player or not ctx.voice_client:
            raise MusicError("Nothing is playing.")
        state = ctx.author.voice
        if not state or state.channel != ctx.voice_client.channel:
            raise MusicError("You need to be in my voice channel to do that.")
        return player

    async def load_tracks(self, query, requester):
        tracks = await self.resolver.resolve(query, requester)
        if tracks is None:
            tracks = await sources.load(query, requester)
        if not tracks:
            raise MusicError("No results found.")
        return tracks

    async def enqueue(self, ctx, tracks, front=False):
        await self._connect(ctx)
        player = self._player(ctx, create=True)
        was_idle = player.current is None and not player.queue
        player.add(tracks, front=front)
        if len(tracks) > 1:
            await ctx.send(f"➕ Queued **{len(tracks)}** tracks.")
        elif not was_idle:
            pos = 1 if front else len(player.queue)
            await ctx.send(f"➕ Queued {track_link(tracks[0])} at position **{pos}**.")
        elif ctx.interaction:  # slash commands must get a reply; "Now playing" follows
            await ctx.send(f"🔎 Loading {track_link(tracks[0])}…")

    async def _play(self, ctx, query, file, front):
        if file:
            query = file.url
        if not query:
            raise MusicError("Tell me what to play: a song name, a link, or attach an audio file.")
        if not ctx.author.voice:
            raise MusicError("Join a voice channel first.")
        await ctx.defer()
        try:
            tracks = await self.load_tracks(query.strip("<> "), ctx.author.mention)
        except SourceError as e:
            raise MusicError(f"Couldn't load that: {e}")
        await self.enqueue(ctx, tracks, front=front)

    # ------------------------------------------------------------------ playback commands

    @commands.hybrid_command(aliases=["p"])
    async def play(self, ctx, file: Optional[discord.Attachment] = None, *, query: Optional[str] = None):
        """Play a song name, link (YouTube, Spotify, SoundCloud, Deezer, Apple Music, ...) or audio file."""
        await self._play(ctx, query, file, front=False)

    @commands.hybrid_command(aliases=["pn"])
    async def playnext(self, ctx, *, query: str):
        """Put a song at the front of the queue."""
        await self._play(ctx, query, None, front=True)

    @commands.hybrid_command()
    async def search(self, ctx, *, query: str):
        """Search YouTube and pick from the top 5 results."""
        await ctx.defer()
        try:
            results = await sources.search(query, 5, ctx.author.mention)
        except SourceError as e:
            raise MusicError(f"Search failed: {e}")
        if not results:
            raise MusicError("No results found.")

        async def picked(i):
            await self.enqueue(ctx, [results[i]])

        view = PickView(ctx.author.id, [(t.title, fmt_duration(t.duration)) for t in results], picked)
        view.message = await ctx.send(f"Results for **{discord.utils.escape_markdown(query)}**:", view=view)

    @commands.hybrid_command()
    async def radio(self, ctx, *, name: str):
        """Search 40,000+ internet radio stations by name or genre."""
        await ctx.defer()
        try:
            stations = await self.resolver.search_radio(name)
        except SourceError as e:
            raise MusicError(str(e))
        if not stations:
            raise MusicError("No stations found.")

        async def picked(i):
            await self.enqueue(ctx, [Resolver.radio_track(stations[i], ctx.author.mention)])

        options = [(s["name"].strip(), ", ".join(filter(None, [s.get("country"), s.get("tags", "")[:60]])))
                   for s in stations]
        view = PickView(ctx.author.id, options, picked)
        view.message = await ctx.send(f"Stations matching **{discord.utils.escape_markdown(name)}**:", view=view)

    @commands.hybrid_command(aliases=["s", "next"])
    async def skip(self, ctx):
        """Skip the current song."""
        player = self._active(ctx)
        if not player.current:
            raise MusicError("Nothing is playing.")
        track = player.current
        player.skip()
        await ctx.send(f"⏭️ Skipped {track_link(track)}.")

    @commands.hybrid_command()
    async def stop(self, ctx):
        """Stop playing and clear the queue."""
        self._active(ctx).stop()
        await ctx.send("⏹️ Stopped and cleared the queue.")

    @commands.hybrid_command()
    async def pause(self, ctx):
        """Pause playback."""
        if not self._active(ctx).pause():
            raise MusicError("Nothing is playing.")
        await ctx.send("⏸️ Paused.")

    @commands.hybrid_command(aliases=["unpause"])
    async def resume(self, ctx):
        """Resume playback."""
        if not self._active(ctx).resume():
            raise MusicError("Playback isn't paused.")
        await ctx.send("▶️ Resumed.")

    @commands.hybrid_command(aliases=["np", "current"])
    async def nowplaying(self, ctx):
        """Show the current song."""
        player = self._player(ctx)
        if not player or not player.current:
            raise MusicError("Nothing is playing.")
        await ctx.send(embed=player.now_playing_embed())

    @commands.hybrid_command(aliases=["q"])
    async def queue(self, ctx, page: int = 1):
        """Show the queue."""
        player = self._player(ctx)
        if not player or (not player.current and not player.queue):
            raise MusicError("The queue is empty.")
        items = list(player.queue)
        pages = max(1, -(-len(items) // PAGE_SIZE))
        page = min(max(page, 1), pages)
        start = (page - 1) * PAGE_SIZE
        lines = [f"`{i}.` {track_link(t, 60)} `{fmt_duration(t.duration)}`"
                 for i, t in enumerate(items[start:start + PAGE_SIZE], start + 1)]
        desc = f"**Now playing:** {track_link(player.current, 70)}\n\n" if player.current else ""
        desc += "\n".join(lines) or "*Nothing queued after this.*"
        total = sum(t.duration or 0 for t in items)
        embed = discord.Embed(title="Queue", description=desc, color=discord.Color.blurple())
        embed.set_footer(text=f"Page {page}/{pages} · {len(items)} tracks · {fmt_duration(total)} · loop: {player.loop_mode}")
        await ctx.send(embed=embed)

    @commands.hybrid_command(aliases=["rm"])
    async def remove(self, ctx, position: int):
        """Remove a song from the queue by its position."""
        player = self._active(ctx)
        if not 1 <= position <= len(player.queue):
            raise MusicError(f"Position must be between 1 and {len(player.queue)}.")
        track = player.queue[position - 1]
        del player.queue[position - 1]
        await ctx.send(f"🗑️ Removed {track_link(track)}.")

    @commands.hybrid_command()
    async def clear(self, ctx):
        """Clear the queue (keeps the current song playing)."""
        self._active(ctx).queue.clear()
        await ctx.send("🧹 Cleared the queue.")

    @commands.hybrid_command()
    async def shuffle(self, ctx):
        """Shuffle the queue."""
        player = self._active(ctx)
        player.shuffle()
        await ctx.send(f"🔀 Shuffled {len(player.queue)} tracks.")

    @commands.hybrid_command()
    async def loop(self, ctx, mode: Optional[Literal["off", "track", "queue"]] = None):
        """Loop the current track or the whole queue (off / track / queue)."""
        player = self._active(ctx)
        if mode is None:  # cycle off -> track -> queue -> off
            mode = {"off": "track", "track": "queue", "queue": "off"}[player.loop_mode]
        player.loop_mode = mode
        await ctx.send({"off": "➡️ Looping off.", "track": "🔂 Looping the current track.",
                        "queue": "🔁 Looping the queue."}[mode])

    @commands.hybrid_command(aliases=["vol", "v"])
    async def volume(self, ctx, percent: Optional[commands.Range[int, 0, 150]] = None):
        """Show or set the volume (0-150)."""
        player = self._player(ctx)
        if percent is None:
            current = int((player.volume if player else config.DEFAULT_VOLUME / 100) * 100)
            return await ctx.send(f"🔊 Volume is **{current}%**.")
        self._active(ctx).set_volume(percent)
        await ctx.send(f"🔊 Volume set to **{percent}%**.")

    @commands.hybrid_command(aliases=["connect"])
    async def join(self, ctx):
        """Join your voice channel."""
        await self._connect(ctx)
        self._player(ctx, create=True)
        await ctx.send(f"👋 Joined {ctx.voice_client.channel.mention}.")

    @commands.hybrid_command(aliases=["dc", "disconnect"])
    async def leave(self, ctx):
        """Leave the voice channel and clear the queue."""
        player = self._player(ctx)
        if player:
            await player.destroy()
        elif ctx.voice_client:
            await ctx.voice_client.disconnect(force=True)
        else:
            raise MusicError("I'm not in a voice channel.")
        await ctx.send("👋 Left the voice channel.")

    # ------------------------------------------------------------------ voice events

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        guild = member.guild
        player = self.players.get(guild.id)
        if member.id == self.bot.user.id and after.channel is None and player:
            await player.destroy()  # kicked or disconnected
            return
        vc = guild.voice_client
        if not vc or not player:
            return
        alone = not any(not m.bot for m in vc.channel.members)
        timer = self._alone_timers.pop(guild.id, None)
        if timer:
            timer.cancel()
        if alone:
            self._alone_timers[guild.id] = asyncio.create_task(self._leave_if_alone(guild.id))

    async def _leave_if_alone(self, guild_id):
        await asyncio.sleep(config.ALONE_TIMEOUT)
        self._alone_timers.pop(guild_id, None)
        player = self.players.get(guild_id)
        vc = player and player.voice
        if vc and not any(not m.bot for m in vc.channel.members):
            await player.say("Everyone left the voice channel, so I did too. 👋")
            await player.destroy()


async def setup(bot):
    await bot.add_cog(Music(bot))
