# Server playlists saved to data/playlists.json. Songs can come from any source,
# so a Spotify/YouTube/Deezer playlist link can be imported with one "add" command.

import json
import os
import random

import discord
from discord.ext import commands

from .. import config
from ..sources import SourceError, Track
from ..utils import MusicError, fmt_duration, track_link

MAX_PLAYLIST_SIZE = 1000


class PlaylistStore:
    def __init__(self, path):
        self.path = path
        try:
            self.data = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            self.data = {}

    def save(self):
        self.path.parent.mkdir(exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=1), encoding="utf-8")
        os.replace(tmp, self.path)  # atomic, so a crash can't corrupt the file

    def guild(self, guild_id):
        return self.data.setdefault(str(guild_id), {})

    def get(self, guild_id, name):
        playlist = self.guild(guild_id).get(name.lower())
        if playlist is None:
            raise MusicError(f"No playlist named **{name}**. See `{config.PREFIX}playlist list`.")
        return playlist


class Playlists(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.store = PlaylistStore(config.DATA_DIR / "playlists.json")

    async def cog_check(self, ctx):
        if ctx.guild is None:
            raise commands.NoPrivateMessage()
        return True

    @property
    def music(self):
        return self.bot.get_cog("Music")

    def _editable(self, ctx, name):
        playlist = self.store.get(ctx.guild.id, name)
        if playlist["owner"] != ctx.author.id and not ctx.author.guild_permissions.manage_guild:
            raise MusicError("Only the playlist's creator (or a server manager) can change it.")
        return playlist

    @commands.hybrid_group(name="playlist", aliases=["pl"], fallback="list", invoke_without_command=True)
    async def playlist(self, ctx):
        """List this server's playlists."""
        playlists = self.store.guild(ctx.guild.id).values()
        if not playlists:
            raise MusicError(f"No playlists yet. Create one with `{config.PREFIX}playlist create <name>`.")
        lines = [f"• **{p['name']}** — {len(p['tracks'])} tracks (<@{p['owner']}>)" for p in playlists]
        await ctx.send(embed=discord.Embed(title="Playlists", description="\n".join(lines)[:4000],
                                           color=discord.Color.blurple()),
                       allowed_mentions=discord.AllowedMentions.none())

    @playlist.command()
    async def create(self, ctx, *, name: str):
        """Create an empty playlist."""
        playlists = self.store.guild(ctx.guild.id)
        if name.lower() in playlists:
            raise MusicError(f"**{name}** already exists.")
        playlists[name.lower()] = {"name": name, "owner": ctx.author.id, "tracks": []}
        self.store.save()
        await ctx.send(f"📁 Created playlist **{name}**. Add songs with `{config.PREFIX}playlist add \"{name}\" <song or link>`.")

    @playlist.command()
    async def delete(self, ctx, *, name: str):
        """Delete a playlist."""
        playlist = self._editable(ctx, name)
        del self.store.guild(ctx.guild.id)[name.lower()]
        self.store.save()
        await ctx.send(f"🗑️ Deleted playlist **{playlist['name']}**.")

    @playlist.command()
    async def add(self, ctx, name: str, *, query: str):
        """Add a song, or every song from a playlist/album link, to a playlist."""
        playlist = self._editable(ctx, name)
        await ctx.defer()
        try:
            tracks = await self.music.load_tracks(query.strip("<> "), "")
        except SourceError as e:
            raise MusicError(f"Couldn't load that: {e}")
        room = MAX_PLAYLIST_SIZE - len(playlist["tracks"])
        playlist["tracks"] += [t.to_dict() for t in tracks[:room]]
        self.store.save()
        what = track_link(tracks[0]) if len(tracks) == 1 else f"**{min(len(tracks), room)}** tracks"
        await ctx.send(f"➕ Added {what} to **{playlist['name']}**.")

    @playlist.command(name="remove")
    async def remove_track(self, ctx, name: str, position: int):
        """Remove a song from a playlist by its position."""
        playlist = self._editable(ctx, name)
        if not 1 <= position <= len(playlist["tracks"]):
            raise MusicError(f"Position must be between 1 and {len(playlist['tracks'])}.")
        removed = playlist["tracks"].pop(position - 1)
        self.store.save()
        await ctx.send(f"🗑️ Removed **{discord.utils.escape_markdown(removed['title'])}** from **{playlist['name']}**.")

    @playlist.command()
    async def save(self, ctx, *, name: str):
        """Save the current song and queue as a new playlist."""
        player = self.music.players.get(ctx.guild.id)
        tracks = ([player.current] if player and player.current else []) + list(player.queue if player else [])
        if not tracks:
            raise MusicError("There's nothing in the queue to save.")
        playlists = self.store.guild(ctx.guild.id)
        if name.lower() in playlists:
            raise MusicError(f"**{name}** already exists.")
        playlists[name.lower()] = {"name": name, "owner": ctx.author.id,
                                   "tracks": [t.to_dict() for t in tracks[:MAX_PLAYLIST_SIZE]]}
        self.store.save()
        await ctx.send(f"💾 Saved **{len(tracks)}** tracks as **{name}**.")

    @playlist.command()
    async def show(self, ctx, name: str, page: int = 1):
        """Show the songs in a playlist."""
        playlist = self.store.get(ctx.guild.id, name)
        tracks = [Track.from_dict(t) for t in playlist["tracks"]]
        pages = max(1, -(-len(tracks) // 15))
        page = min(max(page, 1), pages)
        start = (page - 1) * 15
        lines = [f"`{i}.` {track_link(t, 60)} `{fmt_duration(t.duration)}`"
                 for i, t in enumerate(tracks[start:start + 15], start + 1)]
        embed = discord.Embed(title=playlist["name"], description="\n".join(lines) or "*Empty*",
                              color=discord.Color.blurple())
        embed.set_footer(text=f"Page {page}/{pages} · {len(tracks)} tracks")
        await ctx.send(embed=embed)

    @playlist.command(name="play")
    async def play_playlist(self, ctx, name: str, shuffle: bool = False):
        """Queue a whole playlist (optionally shuffled)."""
        playlist = self.store.get(ctx.guild.id, name)
        if not playlist["tracks"]:
            raise MusicError(f"**{playlist['name']}** is empty.")
        tracks = [Track.from_dict(t, ctx.author.mention) for t in playlist["tracks"]]
        if shuffle:
            random.shuffle(tracks)
        await self.music.enqueue(ctx, tracks)


async def setup(bot):
    await bot.add_cog(Playlists(bot))
