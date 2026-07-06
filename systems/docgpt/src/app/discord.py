import asyncio
import logging
import os
from pathlib import Path
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

BOT = discord.Bot(auto_sync_commands=True, intents=intents)
NEW_THREAD_NAME = "New Thread"
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

    thinking_msg = await channel.send("_Gathering information..._")

    # LangChain / LLM work is synchronous; run off the event loop so other
    # users' slash commands (e.g. /help_me defer) are not starved.
    result: dict[str, Any] = await asyncio.to_thread(
        assistant.prompt_with_metadata,
        message_content,
        session_id=str(channel.id),
    )
    await thinking_msg.delete()
    response = result["answer"]

    # Build citation block from source documents (top 3 unique sources).
    _GITHUB_BASE = "https://github.com/Rdatatable/data.table"
    _MAX_CITATIONS = 3
    source_docs = result.get("source_documents") or []
    seen: set[str] = set()
    citation_lines: list[str] = []
    for doc in source_docs:
        metadata = getattr(doc, "metadata", {}) or {}
        source = metadata.get("source") or ""
        file_path = metadata.get("file_path") or ""

        # Deduplicate by file_path if available, otherwise source.
        # Stop after MAX_CITATIONS unique sources.
        dedup_key = file_path or source
        if not dedup_key or dedup_key in seen:
            continue
        if len(citation_lines) >= _MAX_CITATIONS:
            break
        seen.add(dedup_key)

        if source.startswith("http://") or source.startswith("https://"):
            citation_lines.append(f"- <{source}>")
        elif source.endswith(".wiki"):
            # Wiki page: strip .md extension to get the page name.
            if file_path:
                page = Path(file_path).stem
                url = f"{_GITHUB_BASE}/wiki/{page}"
                citation_lines.append(f"- [**{page}**](<{url}>)")
            else:
                # Old ingestion record without file_path — link to wiki home.
                citation_lines.append(f"- [**data.table wiki**](<{_GITHUB_BASE}/wiki>)")
        elif file_path:
            # Source code file: link to the file on GitHub.
            url = f"{_GITHUB_BASE}/blob/master/{file_path}"
            citation_lines.append(f"- [**{file_path}**](<{url}>)")
        else:
            citation_lines.append(f"- `{os.path.basename(source)}`")

    if citation_lines:
        response = response.rstrip() + "\n\n**Sources:**\n" + "\n".join(citation_lines)

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

    # Add feedback reactions to the assistant's first reply.
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
            bot_reply_message_id=str(first_reply_message.id) if first_reply_message else None,
        )
    except Exception as e:
        log = logging.getLogger(__name__)
        log.error("Failed to log Discord interaction: %s", e)

    if channel.name.lower() == NEW_THREAD_NAME.lower():
        log = logging.getLogger(__name__)
        try:
            title = await asyncio.to_thread(
                assistant.generate_title, message_content, response
            )
            safe = _safe_thread_name(title)
            if safe.lower() != NEW_THREAD_NAME.lower():
                await channel.edit(name=safe)
                log.debug("Thread renamed to: %s", safe)
            else:
                log.warning("generate_title returned empty/unusable title: %r", title)
        except Exception as e:
            log.error("Failed to generate thread title: %s", e)


@BOT.event
@inject
async def on_raw_reaction_add(
    payload: discord.RawReactionActionEvent,
    *,
    interaction_logger: DiscordInteractionLogger = Provide[
        Settings.logging.discord_logger
    ],
) -> None:
    log = logging.getLogger(__name__)

    # Ignore the bot's own reactions.
    if BOT.user and payload.user_id == BOT.user.id:
        return

    emoji = str(payload.emoji)
    if emoji not in ("👍", "👎"):
        return

    thumbs_up = emoji == "👍"

    try:
        updated = await asyncio.to_thread(
            interaction_logger.log_feedback,
            bot_reply_message_id=str(payload.message_id),
            thumbs_up=thumbs_up,
        )
        if updated:
            log.debug("Feedback logged: %s for message %s", emoji, payload.message_id)
        else:
            log.debug("Reaction %s on message %s matched no log row", emoji, payload.message_id)
    except Exception as e:
        log.error("Failed to log feedback reaction: %s", e)
