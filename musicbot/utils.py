import discord
from discord.ext import commands


class MusicError(commands.CommandError):
    """An error whose message is shown to the user as-is."""


def fmt_duration(seconds):
    if seconds is None:
        return "live"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    return f"{h}:{m:02}:{s:02}" if h else f"{m}:{s:02}"


def track_link(track, limit=90):
    title = discord.utils.escape_markdown(track.title[:limit])
    return f"[{title}]({track.url})" if track.url else f"**{title}**"


class PickView(discord.ui.View):
    """A dropdown letting the command author choose one of several options."""

    def __init__(self, author_id, options, on_pick):
        super().__init__(timeout=60)
        self.author_id = author_id
        self.on_pick = on_pick
        self.message = None
        self.select = discord.ui.Select(placeholder="Choose one…", options=[
            discord.SelectOption(label=label[:100] or "?", description=(desc or None) and desc[:100], value=str(i))
            for i, (label, desc) in enumerate(options)
        ])
        self.select.callback = self._picked
        self.add_item(self.select)

    async def interaction_check(self, interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("This menu isn't for you.", ephemeral=True)
            return False
        return True

    async def _picked(self, interaction):
        self.stop()
        index = int(self.select.values[0])
        await interaction.response.edit_message(content=f"Selected **{self.select.options[index].label}**", view=None)
        await self.on_pick(index)

    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content="Selection timed out.", view=None)
            except discord.HTTPException:
                pass
