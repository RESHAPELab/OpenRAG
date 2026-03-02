import logging

import discord
from dependency_injector.wiring import Provide, inject
from langchain_text_splitters import MarkdownTextSplitter

from src.core.containers import Settings
from src.core.interaction_logger import get_logger
from src.port.assistant import AssistantPort

__all__ = ("BOT",)

log = logging.getLogger(__name__)

# Configure intents to allow fetching thread members
intents = discord.Intents.default()
intents.members = True
intents.message_content = True

BOT = discord.Bot(auto_sync_commands=True, intents=intents)
NEW_THREAD_NAME = "New Thread"
MAX_MESSAGE_LEN = 2000


@BOT.event
async def on_ready():
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

    result = assistant.prompt(message_content, session_id=str(channel.id))

    # Log the interaction (question, retrieved context, answer)
    interaction_logger = get_logger()
    if interaction_logger:
        try:
            interaction_logger.log(
                session_id=str(channel.id),
                question=message_content,
                answer=result.answer,
                retrieved_context=result.retrieved_context,
                source_metadata=result.source_metadata,
            )
        except Exception:
            log.exception("Failed to log interaction")

    response_chunks = MarkdownTextSplitter(
        chunk_size=MAX_MESSAGE_LEN,
        chunk_overlap=0,
        strip_whitespace=False,
        keep_separator=True,
        add_start_index=True,
    ).split_text(result.answer)

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
            log.exception("Failed to add feedback reactions to assistant reply")

    if channel.name.lower() == NEW_THREAD_NAME.lower():
        title_result = assistant.prompt(
            f"""Create a short raw string title for this history: 
            
            - question:
            {message_content}
            
            - answer:
            {result.answer}
            
            title:"""
        )
        await channel.edit(name=title_result.answer)
