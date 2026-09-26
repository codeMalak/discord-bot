# Discord Music Bot

Plays music in Discord voice channels from:

- YouTube and YouTube Music
- Spotify
- SoundCloud
- Deezer
- Apple Music
- Bandcamp
- Mixcloud
- Vimeo
- Twitch
- direct audio links and Discord attachments
- internet radio

It has a queue, loop modes, volume control and saved server playlists.

Every command works with the `$` prefix (for example `$play`) and as a slash command (for example `/play`).

## Getting help in Discord

| Command | What it shows |
|---|---|
| `$help` | Every command with a one-line description |
| `$help <command>` | How one command works, with usage, shortcuts and examples |

For example, `$help play` or `$help playlist add`. Shortcuts work too, so `$help p` is the same as `$help play`. With `/help`, Discord suggests command names as you type.

## Commands

Arguments in `<angle brackets>` are required. Arguments in `[square brackets]` are optional.

### 🎵 Playback

| Command | Shortcuts | What it does |
|---|---|---|
| `$play <song \| link \| attachment>` | `$p` | Plays a song, or adds it to the queue if something is already playing. See [How playback works](#how-playback-works). |
| `$playnext <song \| link>` | `$pn` | Same as `play`, but puts the song at the front of the queue. |
| `$search <song>` | | Shows a dropdown of the top 5 YouTube results. Pick one to queue it. Only the person who searched can use the menu, and it expires after 60 seconds. |
| `$radio <name \| genre>` | | Searches about 40,000 internet radio stations and shows the 5 most popular matches in a dropdown. Radio plays until you skip or stop it. |
| `$pause` | | Pauses playback. |
| `$resume` | `$unpause` | Continues from where it was paused. |
| `$skip` | `$s`, `$next` | Plays the next song in the queue. This also moves past a song on repeat. |
| `$stop` | | Stops playback and clears the queue. The bot stays in the channel. |
| `$nowplaying` | `$np`, `$current` | Shows the current song with a progress bar, the requester, the loop mode and what's next. |
| `$volume [0-150]` | `$vol`, `$v` | Shows the volume, or sets it as a percentage. The change applies immediately. The default is 50%. |
| `$join` | `$connect` | Joins your voice channel. You rarely need this, because `play` joins automatically. |
| `$leave` | `$dc`, `$disconnect` | Leaves the voice channel and clears the queue. |

### 📜 Queue

| Command | Shortcuts | What it does |
|---|---|---|
| `$queue [page]` | `$q` | Lists the current song and upcoming songs, 10 per page, with the total length. |
| `$loop [off \| track \| queue]` | | `track` repeats the current song. `queue` sends each finished song to the back of the queue, so the queue repeats forever. `off` stops repeating. With no option, it cycles off → track → queue. |
| `$shuffle` | | Randomizes the order of the queue. The current song keeps playing. |
| `$remove <position>` | `$rm` | Removes the song at that position in `$queue`. |
| `$clear` | | Empties the queue but lets the current song finish. |

### 📁 Playlists

Playlists are saved per server. Anyone on the server can list, show and play them. Only the person who created a playlist, or someone with the **Manage Server** permission, can change or delete it.

| Command | What it does |
|---|---|
| `$playlist` | Lists this server's playlists with their size and creator. Shortcut: `$pl`. |
| `$playlist create <name>` | Creates an empty playlist. |
| `$playlist add <name> <song \| link>` | Adds a song. With a playlist or album link, it adds every song from it, so you can import a Spotify, YouTube, Deezer or Apple Music playlist in one command. Playlists hold up to 1000 songs. |
| `$playlist show <name> [page]` | Lists a playlist's songs with their positions, 15 per page. |
| `$playlist play <name> [shuffle]` | Queues every song in the playlist. Add `true` to shuffle them first. |
| `$playlist save <name>` | Saves the current song and queue as a new playlist. |
| `$playlist remove <name> <position>` | Removes the song at that position. |
| `$playlist delete <name>` | Deletes the playlist permanently. |

With the prefix, put playlist names that contain spaces in quotes:

```
$playlist create "road trip"
$playlist add "road trip" https://open.spotify.com/playlist/...
$playlist play "road trip" true
```

Slash commands have a separate box for each argument, so they don't need quotes.

## How playback works

- **Song names** search YouTube and play the top result.
- **YouTube, SoundCloud, Bandcamp, Mixcloud, Vimeo and Twitch links**, direct audio links and attached files stream directly. Nothing is saved to disk.
- **Playlist and album links** add every song, up to 500.
- **Spotify, Deezer and Apple Music links** give the bot each song's title and artist. It finds the matching audio on YouTube when that song comes up. Because songs are only looked up as they play, even large playlists queue instantly.
- **Spotify's API needs Premium.** It only works if the Spotify developer app's owner has Premium. Without it, the bot reads Spotify's public embed pages instead, which cover tracks, albums and playlists up to about 100 songs.
- **The bot leaves on its own** after 5 minutes with nothing queued, or after 1 minute alone in the voice channel. You can change both times in `.env`.
- **Only the current listeners can control playback.** To use skip, pause, stop, volume or the other playback controls, you must be in the same voice channel as the bot.

## Setup

1. Create the virtual environment and install the dependencies:
   ```
   python -m venv .venv
   .venv\Scripts\pip install -r requirements.txt
   ```
2. Copy `.env.example` to `.env` and set `DISCORD_TOKEN`.
3. In the [Discord Developer Portal](https://discord.com/developers/applications), open your app. Under **Bot**, turn on **Message Content Intent**. The `$` commands need it.
4. Invite the bot to your server. Replace `YOUR_APP_ID` with your application ID:
   `https://discord.com/oauth2/authorize?client_id=YOUR_APP_ID&scope=bot+applications.commands&permissions=3230720`

   This link grants the permissions the bot needs:
   - View Channels
   - Send Messages
   - Embed Links
   - Read Message History
   - Connect
   - Speak
5. Start the bot:
   ```
   .venv\Scripts\python main.py
   ```

The bot needs FFmpeg, which isn't included in the repository. Install it with `winget install ffmpeg`, or put `ffmpeg.exe` in the project folder. The bot looks in the project folder first, then on your PATH. YouTube playback also needs a JavaScript runtime. The `deno` package in `requirements.txt` provides one.

### Settings (`.env`)

| Setting | Default | Meaning |
|---|---|---|
| `DISCORD_TOKEN` | — | Your bot token (required) |
| `COMMAND_PREFIX` | `$` | The prefix for text commands |
| `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` | empty | Optional. Only used if the Spotify app's owner has Premium. |
| `IDLE_TIMEOUT` | `300` | Seconds with an empty queue before the bot leaves |
| `ALONE_TIMEOUT` | `60` | Seconds alone in a voice channel before the bot leaves |
| `DEFAULT_VOLUME` | `50` | Starting volume, as a percentage |
| `MAX_TRACKS` | `500` | Most songs loaded from a single playlist or album link |

## Project layout

| Path | Contents |
|---|---|
| `main.py` | Bot startup and error handling |
| `musicbot/cogs/music.py` | Playback and queue commands |
| `musicbot/cogs/playlists.py` | Saved playlists, stored in `data/playlists.json` |
| `musicbot/cogs/help.py` | The `help` command and every command's help text |
| `musicbot/player.py` | Each server's queue and playback loop |
| `musicbot/sources.py` | yt-dlp search and streaming |
| `musicbot/resolvers.py` | Spotify, Deezer, Apple Music and radio lookups |
| `legacy/` | The original bot, kept for reference |
