import logging
import re
from typing import Any

import discord
from dependency_injector.wiring import Provide, inject
from langchain_text_splitters import MarkdownTextSplitter

from src.core.containers import Settings
from src.logging.discord_logger import DiscordInteractionLogger
from src.port.assistant import AssistantPort

__all__ = ("BOT",)

# Configure intents to allow fetching thread members and reactions
intents = discord.Intents.default()
intents.members = True
intents.message_content = True
intents.reactions = True

BOT = discord.Bot(auto_sync_commands=True, intents=intents)
NEW_THREAD_NAME = "New Thread about data.table"
MAX_MESSAGE_LEN = 2000
MAX_THREAD_NAME_LEN = 100


def _safe_thread_name(name: str) -> str:
    # Discord thread names must be <= 100 characters.
    cleaned = " ".join((name or "").strip().split())
    if not cleaned:
        return NEW_THREAD_NAME
    if len(cleaned) <= MAX_THREAD_NAME_LEN:
        return cleaned
    return cleaned[:MAX_THREAD_NAME_LEN].rstrip()


def _extract_title(raw: str) -> str:
    """Best-effort extraction when model returns extra narration."""
    text = (raw or "").strip()
    if not text:
        return NEW_THREAD_NAME

    # Keep first non-empty line only.
    first_line = next((line.strip() for line in text.splitlines() if line.strip()), text)

    # Remove common wrappers such as: "A great title would be: ..."
    first_line = re.sub(
        r"(?i)^(?:hi there!?[\s,-]*)?(?:a\s+great\s+title(?:\s+for\s+this\s+history)?\s+would\s+be|title)\s*:\s*",
        "",
        first_line,
    )

    # Strip markdown bullets/quotes and surrounding quotes.
    first_line = re.sub(r"^[>\-\*\d\.\)\s]+", "", first_line).strip().strip("'\"`")
    return _safe_thread_name(first_line)


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


@BOT.event
@inject
async def on_raw_reaction_add(
    payload: discord.RawReactionActionEvent,
    *,
    interaction_logger: DiscordInteractionLogger = Provide[
        Settings.logging.discord_logger
    ],
):
    """Handle feedback reactions (thumbs up/down) on bot messages."""
    log = logging.getLogger(__name__)

    if BOT.user is None:
        return

    if payload.user_id == BOT.user.id:
        return

    emoji = str(payload.emoji)
    if emoji not in ("👍", "👎"):
        return

    thumbs_up = emoji == "👍"
    reply_message_id = str(payload.message_id)

    try:
        updated = interaction_logger.log_feedback(
            discord_reply_message_id=reply_message_id,
            thumbs_up=thumbs_up,
        )
        if updated:
            log.debug(
                "Recorded feedback (thumbs_up=%s) for reply message %s",
                thumbs_up,
                reply_message_id,
            )
    except Exception as e:
        log.error("Failed to log feedback for message %s: %s", reply_message_id, e)


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

    first_reply_message: discord.Message | None = None
    for reply in response_chunks:
        sent = await user_message.reply(reply)
        if first_reply_message is None:
            first_reply_message = sent

    # Add feedback reactions to the assistant's first reply (the answer),
    # not to the original user question message.
    if first_reply_message is not None:
        try:
            await first_reply_message.add_reaction("👍")
            await first_reply_message.add_reaction("👎")
        except Exception:
            log = logging.getLogger(__name__)
            log.exception("Failed to add feedback reactions to assistant reply")

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
            discord_reply_message_id=str(first_reply_message.id) if first_reply_message else None,
        )
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to log Discord interaction: %s", e)

    if channel.name.lower() == NEW_THREAD_NAME.lower():
        title = assistant.prompt(
            f"""Return ONLY a concise thread title.
            Rules:
            - 3 to 8 words
            - No greeting, no explanation, no punctuation at the end
            - Output title text only (single line)
            
            - question:
            {message_content}
            
            - answer:
            {response}
            
            title:"""
        )
        await channel.edit(name=_extract_title(title))
