# module:    main.py
# author:    Carlos Rodriguez
# Date:      November 10, 2022 (rewritten September 2026)
# Purpose:   Discord music bot. Streams from YouTube, Spotify, SoundCloud, Deezer,
#            Apple Music, Bandcamp, Mixcloud, Vimeo, Twitch, direct links and internet radio.
#            Commands work with the prefix (default $) and as slash commands.

import logging
import sys

import discord
from discord import app_commands
from discord.ext import commands

from musicbot import config
from musicbot.utils import MusicError

log = logging.getLogger("musicbot")

class MusicBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True  # needed for prefix commands
        super().__init__(command_prefix=commands.when_mentioned_or(config.PREFIX), intents=intents,
                         help_command=None, case_insensitive=True,
                         activity=discord.Activity(type=discord.ActivityType.listening,
                                                   name=f"{config.PREFIX}help"))

    async def setup_hook(self):
        await self.load_extension("musicbot.cogs.music")
        await self.load_extension("musicbot.cogs.playlists")
        await self.load_extension("musicbot.cogs.help")
        synced = await self.tree.sync()
        log.info("Synced %d slash commands", len(synced))

    async def on_ready(self):
        log.info("Logged in as %s (%s) in %d servers", self.user, self.user.id, len(self.guilds))

    async def on_command_error(self, ctx, error):
        if isinstance(error, commands.CommandNotFound):
            return
        while not isinstance(error, MusicError) and getattr(error, "original", None) is not None:
            error = error.original  # unwrap CommandInvokeError / HybridCommandError
        if isinstance(error, commands.MissingRequiredArgument):
            message = f"Missing `{error.param.name}`. Usage: `{config.PREFIX}{ctx.command.qualified_name} {ctx.command.signature}`"
        elif isinstance(error, (MusicError, commands.UserInputError, commands.CheckFailure,
                                app_commands.CheckFailure)):
            message = str(error)
        else:
            log.error("Error in command %s", ctx.command, exc_info=error)
            message = "Something went wrong running that command."
        try:
            await ctx.send(f"❌ {message}", ephemeral=True)
        except discord.HTTPException:
            pass



def main():
    discord.utils.setup_logging(level=logging.INFO)
    if not config.DISCORD_TOKEN:
        sys.exit("DISCORD_TOKEN is not set. Copy .env.example to .env and fill it in.")
    if not config.DENO:
        log.warning("deno not found: YouTube playback may fail. Install it with `pip install deno`.")
    MusicBot().run(config.DISCORD_TOKEN, log_handler=None)


if __name__ == "__main__":
    main()
