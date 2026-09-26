# $help shows an overview of every command; $help <command> shows how one command works.

import discord
from discord import app_commands
from discord.ext import commands

from .. import config

# name -> (arguments, one-line summary, how it works, examples)
SECTIONS = {
    "🎵 Playback": {
        "play": ("<song | link | attachment>", "Play a song, or add it to the queue",
                 "Searches YouTube for a song name, or plays a link directly. Works with YouTube, YouTube Music, "
                 "Spotify, SoundCloud, Deezer, Apple Music, Bandcamp, Mixcloud, Vimeo, Twitch and direct audio "
                 "links. You can also attach an audio file to the message.\n\n"
                 "Playlist and album links add every song. Spotify, Deezer and Apple Music songs are matched "
                 "on YouTube when their turn comes, so big playlists queue instantly.\n\n"
                 "If something is already playing, the song goes to the end of the queue. "
                 "You must be in a voice channel.",
                 ["play never gonna give you up", "play https://open.spotify.com/playlist/...",
                  "play https://soundcloud.com/..."]),
        "playnext": ("<song | link>", "Queue a song to play right after the current one",
                     "Works like `play`, but puts the song at the front of the queue instead of the end.",
                     ["playnext bohemian rhapsody"]),
        "search": ("<song>", "Choose from the top 5 YouTube results",
                   "Shows a dropdown menu with the top 5 YouTube results. Pick one to queue it. "
                   "Only the person who searched can use the menu, and it expires after 60 seconds.",
                   ["search lofi hip hop"]),
        "radio": ("<name | genre>", "Play an internet radio station",
                  "Searches about 40,000 stations from radio-browser.info by name or genre and shows the "
                  "5 most popular matches in a dropdown. Radio plays until you skip or stop it.",
                  ["radio lofi", "radio jazz", "radio bbc radio 1"]),
        "pause": ("", "Pause the current song", "Pauses playback. Use `resume` to continue.", ["pause"]),
        "resume": ("", "Resume a paused song", "Continues playback from where it was paused.", ["resume"]),
        "skip": ("", "Skip to the next song",
                 "Stops the current song and plays the next one in the queue. "
                 "Skipping also moves past a song that's on repeat with `loop track`.", ["skip"]),
        "stop": ("", "Stop playing and clear the queue",
                 "Stops the current song and removes everything from the queue. The bot stays in the "
                 "voice channel; use `leave` to disconnect it.", ["stop"]),
        "nowplaying": ("", "Show the current song",
                       "Shows the current song with a progress bar, who requested it, the loop mode, and "
                       "what's up next.", ["nowplaying"]),
        "volume": ("[0-150]", "Show or change the volume",
                   "Without a number, shows the current volume. With a number, sets it as a percentage "
                   "(0-150). The change applies immediately and lasts until the bot leaves. The default is "
                   f"{config.DEFAULT_VOLUME}%.", ["volume", "volume 80"]),
        "join": ("", "Bring the bot into your voice channel",
                 "Joins the voice channel you're in. You usually don't need this: `play` joins automatically.",
                 ["join"]),
        "leave": ("", "Disconnect the bot",
                  "Leaves the voice channel and clears the queue. The bot also leaves on its own after "
                  f"{config.IDLE_TIMEOUT // 60} minutes with nothing queued, or {config.ALONE_TIMEOUT} seconds "
                  "after everyone else leaves the channel.", ["leave"]),
    },
    "📜 Queue": {
        "queue": ("[page]", "Show the upcoming songs",
                  "Lists the current song and the queue, 10 songs per page, with the total length and "
                  "loop mode.", ["queue", "queue 2"]),
        "loop": ("[off | track | queue]", "Repeat the current song or the whole queue",
                 "`track` repeats the current song. `queue` sends each song to the back of the queue when it "
                 "finishes, so the queue plays forever. `off` stops repeating. With no option, it cycles "
                 "off → track → queue → off.", ["loop", "loop track", "loop off"]),
        "shuffle": ("", "Shuffle the queue", "Randomizes the order of the queued songs. "
                    "The current song keeps playing.", ["shuffle"]),
        "remove": ("<position>", "Remove one song from the queue",
                   "Removes the song at that position. Use `queue` to see the positions.", ["remove 3"]),
        "clear": ("", "Empty the queue", "Removes every queued song but lets the current song finish.",
                  ["clear"]),
    },
    "📁 Playlists": {
        "playlist": ("", "List this server's saved playlists",
                     "Shows every playlist saved on this server, with its size and creator. Playlists belong "
                     "to the server, so anyone can play them. Only the creator, or someone with Manage Server, "
                     "can change or delete one.\n\nWith the prefix, put names that contain spaces in quotes: "
                     f"`{config.PREFIX}playlist add \"road trip\" song`.", ["playlist"]),
        "playlist create": ("<name>", "Create an empty playlist", "Creates a new playlist on this server.",
                            ["playlist create gym"]),
        "playlist add": ("<name> <song | link>", "Add songs to a playlist",
                         "Adds one song, or every song from a playlist or album link. This lets you import a "
                         "Spotify, YouTube, Deezer or Apple Music playlist in one command. "
                         "Playlists hold up to 1000 songs.",
                         ["playlist add gym eye of the tiger", "playlist add gym https://open.spotify.com/playlist/..."]),
        "playlist show": ("<name> [page]", "List the songs in a playlist",
                          "Shows the playlist's songs, 15 per page, with their positions.", ["playlist show gym"]),
        "playlist play": ("<name> [shuffle]", "Queue a whole playlist",
                          "Adds every song in the playlist to the queue. Add `true` to shuffle them first.",
                          ["playlist play gym", "playlist play gym true"]),
        "playlist save": ("<name>", "Save the current queue as a playlist",
                          "Creates a new playlist from the current song and everything in the queue.",
                          ["playlist save friday night"]),
        "playlist remove": ("<name> <position>", "Remove a song from a playlist",
                            "Removes the song at that position. Use `playlist show` to see the positions.",
                            ["playlist remove gym 4"]),
        "playlist delete": ("<name>", "Delete a playlist", "Permanently deletes the playlist.",
                            ["playlist delete gym"]),
    },
}
COMMANDS = {name: info for section in SECTIONS.values() for name, info in section.items()}


class Help(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    def _aliases(self, name):
        cmd = self.bot.get_command(name)
        return list(cmd.aliases) if cmd else []

    def overview(self):
        p = config.PREFIX
        embed = discord.Embed(
            title="🎶 Music bot commands",
            description=f"Use `{p}command` or `/command`. For details and examples, use `{p}help <command>` "
                        f"(for example `{p}help play`).",
            color=discord.Color.blurple())
        for section, cmds in SECTIONS.items():
            lines = [f"`{p}{name}{' ' + args if args else ''}` — {summary}"
                     for name, (args, summary, _, _) in cmds.items()]
            embed.add_field(name=section, value="\n".join(lines), inline=False)
        embed.set_footer(text="Sources: YouTube · Spotify · SoundCloud · Deezer · Apple Music · Bandcamp · "
                              "Mixcloud · Vimeo · Twitch · links · files · radio")
        return embed

    def details(self, name):
        p = config.PREFIX
        args, summary, how, examples = COMMANDS[name]
        embed = discord.Embed(title=f"{p}{name}", description=f"**{summary}**\n\n{how}",
                              color=discord.Color.blurple())
        embed.add_field(name="Usage", value=f"`{p}{name}{' ' + args if args else ''}`", inline=False)
        if aliases := self._aliases(name):
            prefix = f"{name.rsplit(' ', 1)[0]} " if " " in name else ""
            embed.add_field(name="Shortcuts", value=", ".join(f"`{p}{prefix}{a}`" for a in aliases), inline=False)
        embed.add_field(name="Examples", value="\n".join(f"`{p}{e}`" for e in examples), inline=False)
        embed.set_footer(text="<required>  [optional]  ·  also works as a slash command")
        return embed

    @commands.hybrid_command(name="help", aliases=["h", "commands"])
    @app_commands.describe(command="A command to explain, e.g. play or playlist add")
    async def help_command(self, ctx, *, command: str = None):
        """Show all commands, or how one command works."""
        if not command:
            return await ctx.send(embed=self.overview())
        cmd = self.bot.get_command(command.strip().lower().removeprefix(config.PREFIX))
        name = cmd.qualified_name if cmd else None
        if name not in COMMANDS:
            return await ctx.send(f"❌ There's no command called `{command}`. Use `{config.PREFIX}help` to see them all.",
                                  ephemeral=True)
        await ctx.send(embed=self.details(name))

    @help_command.autocomplete("command")
    async def _complete(self, interaction, current):
        return [app_commands.Choice(name=n, value=n) for n in COMMANDS if current.lower() in n][:25]


async def setup(bot):
    await bot.add_cog(Help(bot))
