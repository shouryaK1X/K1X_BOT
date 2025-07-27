
import discord
from discord.ext import commands, tasks
from discord import app_commands
import yt_dlp
import asyncio
import os
from typing import Optional

intents = discord.Intents.all()
bot = commands.Bot(command_prefix="!", intents=intents, help_command=None)
tree = bot.tree

queue = []
current = None
loop = False
autoplay = True
twenty_four_seven = False
voice_client = None
guild_prefixes = {}

# -------- Utility Functions -------- #

def get_prefix(bot, message):
    return guild_prefixes.get(message.guild.id, "!")

@bot.event
async def on_ready():
    print(f"✅ Logged in as {bot.user}")
    try:
        synced = await tree.sync()
        print(f"🔁 Synced {len(synced)} command(s)")
    except Exception as e:
        print(f"❌ Sync failed: {e}")

# -------- Music System -------- #


class MusicControls(discord.ui.View):
    def __init__(self, ctx):
        super().__init__(timeout=None)
        self.ctx = ctx

    @discord.ui.button(label="⏸️ Pause", style=discord.ButtonStyle.primary)
    async def pause(self, interaction: discord.Interaction, button: discord.ui.Button):
        if voice_client and voice_client.is_playing():
            voice_client.pause()
            await interaction.response.send_message("⏸️ Paused", ephemeral=True)

    @discord.ui.button(label="▶️ Resume", style=discord.ButtonStyle.success)
    async def resume(self, interaction: discord.Interaction, button: discord.ui.Button):
        if voice_client and voice_client.is_paused():
            voice_client.resume()
            await interaction.response.send_message("▶️ Resumed", ephemeral=True)

    @discord.ui.button(label="⏭️ Skip", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        if voice_client and voice_client.is_playing():
            voice_client.stop()
            await interaction.response.send_message("⏭️ Skipped", ephemeral=True)

    @discord.ui.button(label="🛑 Stop", style=discord.ButtonStyle.danger)
    async def stop(self, interaction: discord.Interaction, button: discord.ui.Button):
        global queue, current, voice_client
        queue.clear()
        current = None
        if voice_client:
            await voice_client.disconnect()
            voice_client = None
        await interaction.response.send_message("🛑 Stopped and disconnected", ephemeral=True)


def yt_search(query):
    ydl_opts = {'format': 'bestaudio'}
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(f"ytsearch:{query}", download=False)['entries'][0]
    return {
        'url': info['url'],
        'title': info['title'],
        'webpage_url': info['webpage_url'],
        'thumbnail': info.get('thumbnail', '')
    }

async def play_next(ctx):
    global current, voice_client

    if loop:
        queue.insert(0, current)

    if queue:
        current = queue.pop(0)
        source = discord.FFmpegPCMAudio(current['url'], before_options="-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5")
        voice_client.play(source, after=lambda e: asyncio.run_coroutine_threadsafe(play_next(ctx), bot.loop))

        embed = discord.Embed(title="🎶 Now Playing", description=f"[{current['title']}]({current['webpage_url']})", color=0x1DB954)
        if current['thumbnail']:
            embed.set_thumbnail(url=current['thumbnail'])
        view = MusicControls(ctx)
        await ctx.channel.send(embed=embed, view=view)
    elif not twenty_four_seven:
        await asyncio.sleep(180)
        if not voice_client.is_playing():
            await voice_client.disconnect()
            voice_client = None

# -------- Slash Commands -------- #

@tree.command(name="join", description="Join voice channel")
async def join(interaction: discord.Interaction):
    global voice_client
    if interaction.user.voice:
        channel = interaction.user.voice.channel
        voice_client = await channel.connect()
        await interaction.response.send_message(f"📡 Joined {channel.name}", ephemeral=True)
    else:
        await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)

@tree.command(name="play", description="Play a song")
@app_commands.describe(query="Song name or URL")
async def play(interaction: discord.Interaction, query: str):
    global voice_client, current

    if not interaction.user.voice:
        return await interaction.response.send_message("❌ You must be in a voice channel!", ephemeral=True)

    await interaction.response.defer()  # Acknowledge interaction immediately to prevent timeout

    if not voice_client or not voice_client.is_connected():
        voice_client = await interaction.user.voice.channel.connect()

    data = yt_search(query)
    queue.append(data)
    await interaction.followup.send(f"🔍 Searching and added: [{data['title']}]({data['webpage_url']})")

    if not voice_client.is_playing():
        await play_next(await bot.get_context(interaction))@tree.command(name="skip", description="Skip the current song")
async def skip(interaction: discord.Interaction):
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await interaction.response.send_message("⏭️ Skipped", ephemeral=True)

@tree.command(name="pause", description="Pause playback")
async def pause(interaction: discord.Interaction):
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await interaction.response.send_message("⏸️ Paused", ephemeral=True)

@tree.command(name="resume", description="Resume playback")
async def resume(interaction: discord.Interaction):
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await interaction.response.send_message("▶️ Resumed", ephemeral=True)

@tree.command(name="stop", description="Stop and disconnect")
async def stop(interaction: discord.Interaction):
    global queue, current, voice_client
    queue.clear()
    current = None
    if voice_client:
        await voice_client.disconnect()
        voice_client = None
    await interaction.response.send_message("🛑 Stopped and disconnected", ephemeral=True)

@tree.command(name="queue", description="Show current queue")
async def show_queue(interaction: discord.Interaction):
    if not queue:
        return await interaction.response.send_message("📭 Queue is empty.")
    description = "\n".join([f"**{i+1}.** [{track['title']}]({track['webpage_url']})" for i, track in enumerate(queue)])
    embed = discord.Embed(title="📜 Queue", description=description, color=0x1DB954)
    view = MusicControls(interaction)
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="nowplaying", description="Show the current song")
async def nowplaying(interaction: discord.Interaction):
    if not current:
        return await interaction.response.send_message("🚫 Nothing is playing.")
    embed = discord.Embed(title="🎶 Now Playing", description=f"[{current['title']}]({current['webpage_url']})", color=0x1DB954)
    if current.get('thumbnail'):
        embed.set_thumbnail(url=current['thumbnail'])
    view = MusicControls(interaction)
    await interaction.response.send_message(embed=embed, view=view)

@tree.command(name="loop", description="Toggle loop mode")
async def toggle_loop(interaction: discord.Interaction):
    global loop
    loop = not loop
    await interaction.response.send_message(f"🔁 Loop is now {'enabled' if loop else 'disabled'}", ephemeral=True)

@tree.command(name="24_7", description="Toggle 24/7 mode")
async def toggle_247(interaction: discord.Interaction):
    global twenty_four_seven
    twenty_four_seven = not twenty_four_seven
    await interaction.response.send_message(f"💤 24/7 mode is now {'enabled' if twenty_four_seven else 'disabled'}", ephemeral=True)

@tree.command(name="help", description="Show help commands")
async def help(interaction: discord.Interaction):
    commands_list = [
        "`/join` - Join your voice channel",
        "`/play [query]` - Play a song",
        "`/pause` - Pause the current song",
        "`/resume` - Resume the song",
        "`/skip` - Skip the song",
        "`/stop` - Stop and disconnect",
        "`/queue` - Show song queue",
        "`/nowplaying` - Show current song",
        "`/loop` - Toggle loop",
        "`/24_7` - Toggle 24/7 mode",
        "`/help` - Show this help menu"
    ]
    embed = discord.Embed(title="🎵 Bot Commands", description="\n".join(commands_list), color=0x1DB954)
    await interaction.response.send_message(embed=embed, ephemeral=True)

# Run bot

# -------- Prefix Commands -------- #

@bot.command(name="join")
async def join_cmd(ctx):
    global voice_client
    if ctx.author.voice:
        channel = ctx.author.voice.channel
        voice_client = await channel.connect()
        await ctx.send(f"📡 Joined {channel.name}")
    else:
        await ctx.send("❌ You must be in a voice channel!")

@bot.command(name="play")
async def play_cmd(ctx, *, query: str):
    global voice_client, current

    if not ctx.author.voice:
        return await ctx.send("❌ You must be in a voice channel!")

    if not voice_client or not voice_client.is_connected():
        voice_client = await ctx.author.voice.channel.connect()

    data = yt_search(query)
    queue.append(data)
    await ctx.send(f"🔍 Searching and added: [{data['title']}]({data['webpage_url']})")

    if not voice_client.is_playing():
        await play_next(ctx)

@bot.command(name="pause")
async def pause_cmd(ctx):
    if voice_client and voice_client.is_playing():
        voice_client.pause()
        await ctx.send("⏸️ Paused")

@bot.command(name="resume")
async def resume_cmd(ctx):
    if voice_client and voice_client.is_paused():
        voice_client.resume()
        await ctx.send("▶️ Resumed")

@bot.command(name="skip")
async def skip_cmd(ctx):
    if voice_client and voice_client.is_playing():
        voice_client.stop()
        await ctx.send("⏭️ Skipped")

@bot.command(name="stop")
async def stop_cmd(ctx):
    global queue, current, voice_client
    queue.clear()
    current = None
    if voice_client:
        await voice_client.disconnect()
        voice_client = None
    await ctx.send("🛑 Stopped and disconnected")

@bot.command(name="queue")
async def queue_cmd(ctx):
    if not queue:
        return await ctx.send("📭 Queue is empty.")
    description = "\n".join([f"**{i+1}.** [{track['title']}]({track['webpage_url']})" for i, track in enumerate(queue)])
    embed = discord.Embed(title="📜 Queue", description=description, color=0x1DB954)
    view = MusicControls(ctx)
    await ctx.send(embed=embed, view=view)

@bot.command(name="nowplaying")
async def nowplaying_cmd(ctx):
    if not current:
        return await ctx.send("🚫 Nothing is playing.")
    embed = discord.Embed(title="🎶 Now Playing", description=f"[{current['title']}]({current['webpage_url']})", color=0x1DB954)
    if current.get('thumbnail'):
        embed.set_thumbnail(url=current['thumbnail'])
    view = MusicControls(ctx)
    await ctx.send(embed=embed, view=view)

@bot.command(name="loop")
async def loop_cmd(ctx):
    global loop
    loop = not loop
    await ctx.send(f"🔁 Loop is now {'enabled' if loop else 'disabled'}")

@bot.command(name="247")
async def mode247_cmd(ctx):
    global twenty_four_seven
    twenty_four_seven = not twenty_four_seven
    await ctx.send(f"💤 24/7 mode is now {'enabled' if twenty_four_seven else 'disabled'}")

@bot.command(name="help")
async def help_cmd(ctx):
    commands_list = [
        "`!join` - Join your voice channel",
        "`!play [query]` - Play a song",
        "`!pause` - Pause the current song",
        "`!resume` - Resume the song",
        "`!skip` - Skip the song",
        "`!stop` - Stop and disconnect",
        "`!queue` - Show song queue",
        "`!nowplaying` - Show current song",
        "`!loop` - Toggle loop",
        "`!247` - Toggle 24/7 mode",
        "`!help` - Show this help menu"
    ]
    embed = discord.Embed(title="🎵 Bot Commands", description="\n".join(commands_list), color=0x1DB954)
    view = MusicControls(ctx)
    await ctx.send(embed=embed, view=view)


bot.run("MTM5NjQzNjQ2OTY1MjAwMDg4OA.Gy_O-q.hEwK-PjVU7lr1TTN0fgzXZQlce1KJKcFQCz9_E")
