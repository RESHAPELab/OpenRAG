import logging
from typing import Any

import discord
from dependency_injector.wiring import Provide, inject
from langchain_text_splitters import MarkdownTextSplitter

from src.core.containers import Settings
from src.logging.discord_logger import DiscordInteractionLogger
from src.port.assistant import AssistantPort

__all__ = ("BOT",)

# Configure intents to allow fetching thread members
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

BOT = discord.Bot(auto_sync_commands=True, intents=intents)
NEW_THREAD_NAME = "New Thread"
MAX_MESSAGE_LEN = 2000


@BOT.event
async def on_ready():
    log = logging.getLogger(__name__)
    user = BOT.user
    if user is None:
        raise Exception("User not logged")
    log.debug(f"Logged in as {user} (ID: {user.id})")


@BOT.event
@inject
async def on_thread_delete(
    thread: discord.Thread,
    *,
    assistant: AssistantPort = Provide[Settings.assistant.chat],
):
    if not (thread.owner and BOT.user):
        return

    if thread.owner.id == BOT.user.id:
        assistant.clear_history(str(thread.id))


@BOT.command(description="Sends help request")
async def help_me(ctx: discord.ApplicationContext):
    # Defer immediately to prevent timeout (gives us up to 15 minutes to respond)
    await ctx.defer(ephemeral=True)
    
    try:
        channel = ctx.channel
        if channel is None:
            raise ValueError("Channel not found")
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("Command origin not from a text channel")

        thread = await channel.create_thread(
            name=NEW_THREAD_NAME,
            type=discord.ChannelType.private_thread,
        )
        await thread.edit(invitable=False)
        await thread.add_user(ctx.author)

        await thread.send("May I help you?")
        await ctx.followup.send("Private thread created!", ephemeral=True)
    except (Exception,) as e:
        await ctx.followup.send(f"Error: {e}", ephemeral=True)


@BOT.command(description="Clear threads")
@inject
async def clear_my_threads(ctx: discord.ApplicationContext):
    try:
        if not isinstance(ctx.channel, discord.TextChannel):
            raise ValueError("Channel must be a text channel")

        await ctx.respond("Ok!")

        delete_count = 0
        for thread in ctx.channel.threads:
            try:
                members = await thread.fetch_members()
                member_ids = [m.id for m in members]
                if ctx.author.id in member_ids:
                    await thread.delete()
                    delete_count += 1
            except discord.Forbidden:
                continue
        
        async for thread in ctx.channel.archived_threads(limit=100, private=True):
            try:
                members = await thread.fetch_members()
                member_ids = [m.id for m in members]
                if ctx.author.id in member_ids:
                    await thread.delete()
                    delete_count += 1
            except discord.Forbidden:
                continue
    except (Exception,) as e:
        await ctx.respond(f"Error: {e}")


@BOT.event
@inject
async def on_message(
    message: discord.Message,
    *,
    assistant: AssistantPort = Provide[Settings.assistant.chat],
    interaction_logger: DiscordInteractionLogger = Provide[
        Settings.logging.discord_logger
    ],
):
    user = BOT.user
    channel = message.channel

    if (
        message.author == user
        or message.type != discord.MessageType.default
        or not isinstance(channel, discord.Thread)
    ):
        return

    # Note: for some reason message comes empty from "message" var
    user_message = await channel.fetch_message(message.id)
    message_content = user_message.clean_content

    result: dict[str, Any] = assistant.prompt_with_metadata(
        message_content, session_id=str(channel.id)
    )
    response = result["answer"]
    response_chunks = MarkdownTextSplitter(
        chunk_size=MAX_MESSAGE_LEN,
        chunk_overlap=0,
        strip_whitespace=False,
        keep_separator=True,
        add_start_index=True,
    ).split_text(response)

    for reply in response_chunks:
        await user_message.reply(reply)

    try:
        interaction_logger.log_interaction(
            question=message_content,
            rag_answer=response,
            rag_context=result.get("rag_context"),
            llm_answer=result.get("llm_answer"),
            discord_user_id=str(message.author.id),
            discord_channel_id=str(channel.id),
            discord_thread_id=str(channel.id),
            discord_message_id=str(message.id),
        )
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to log Discord interaction: %s", e)

    try:
        await user_message.add_reaction("👍")
        await user_message.add_reaction("👎")
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to add feedback reactions: %s", e)

    if channel.name.lower() == NEW_THREAD_NAME.lower():
        title = assistant.prompt(
            f"""Create a short raw string title for this history: 
            
            - question:
            {message_content}
            
            - answer:
            {response}
            
            title:"""
        )
        await channel.edit(name=title)


@BOT.event
@inject
async def on_reaction_add(
    reaction: discord.Reaction,
    user: discord.abc.User,
    *,
    interaction_logger: DiscordInteractionLogger = Provide[
        Settings.logging.discord_logger
    ],
):
    bot_user = BOT.user
    if bot_user is None:
        return

    if getattr(user, "bot", False) or user.id == bot_user.id:
        return

    emoji = str(reaction.emoji)
    if emoji not in ("👍", "👎"):
        return

    message = reaction.message
    if (
        message.type != discord.MessageType.default
        or not isinstance(message.channel, discord.Thread)
        or (message.author is not None and message.author.id == bot_user.id)
    ):
        return

    thumbs_up = emoji == "👍"
    try:
        updated = interaction_logger.log_feedback(
            discord_message_id=str(message.id),
            thumbs_up=thumbs_up,
        )
        if not updated:
            log = logging.getLogger(__name__)
            log.warning(
                "No Discord log row found for message_id=%s (feedback=%s)",
                str(message.id),
                "up" if thumbs_up else "down",
            )
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to log feedback reaction: %s", e)


@BOT.event
@inject
async def on_reaction_remove(
    reaction: discord.Reaction,
    user: discord.abc.User,
    *,
    interaction_logger: DiscordInteractionLogger = Provide[
        Settings.logging.discord_logger
    ],
):
    bot_user = BOT.user
    if bot_user is None:
        return

    if getattr(user, "bot", False) or user.id == bot_user.id:
        return

    emoji = str(reaction.emoji)
    if emoji not in ("👍", "👎"):
        return

    message = reaction.message
    if (
        message.type != discord.MessageType.default
        or not isinstance(message.channel, discord.Thread)
        or (message.author is not None and message.author.id == bot_user.id)
    ):
        return

    # Clear feedback only when there are no remaining non-bot 👍/👎 reactions.
    # The bot itself adds both reactions, so a count <= 1 indicates no user feedback left.
    has_user_feedback = False
    for r in getattr(message, "reactions", []) or []:
        if str(r.emoji) in ("👍", "👎") and getattr(r, "count", 0) > 1:
            has_user_feedback = True
            break

    if has_user_feedback:
        return

    try:
        updated = interaction_logger.log_feedback(
            discord_message_id=str(message.id),
            thumbs_up=None,
        )
        if not updated:
            log = logging.getLogger(__name__)
            log.warning(
                "No Discord log row found for message_id=%s (feedback cleared)",
                str(message.id),
            )
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to clear feedback reaction: %s", e)
