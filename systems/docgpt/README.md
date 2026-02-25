# DocGPT (WIP)

## Useful commands

```uv sync```: install deps  
```uv run python main.py```: run the Discord bot  

## Requirements
- docker (for PostgreSQL + MongoDB)
- python 3.11+
- uv
- Gemini API key (AI_GEMINI_APIKEY or GOOGLE_API_KEY)
- Discord bot token (APP_DISCORD_TOKEN)

Vector storage uses `langchain-postgres` with psycopg3. Set `STORAGE_VECTOR_URL` in `.env` to match your PostgreSQL. For the project's `docker compose`, use:
```
STORAGE_VECTOR_URL=postgresql+psycopg://root:example@localhost:5432/postgres
```
If you get "password authentication failed", another PostgreSQL may be on port 5432—use `STORAGE_VECTOR_URL` with the correct credentials, or stop the other service and run `docker compose up`.

### Discord interaction logging

The Discord bot logs each interaction (question, RAG answer, RAG context, optional raw LLM answer, Discord IDs, and timestamps) to PostgreSQL in the `discord_interaction_logs` table.

- Configure the logs database URL via:

```env
STORAGE_LOGS_URL=postgresql://root:example@localhost:5432/postgres
```

- Configure the RAG name and whether to log the raw, non-RAG LLM answer via:

```env
ASSISTANT_RAG_NAME=docgpt
ASSISTANT_LOG_RAW_LLM_ANSWER=false
```

- To export all fields to CSV, use the `DiscordInteractionLogger`:

```python
from pathlib import Path
from src.logging.discord_logger import DiscordInteractionLogger

logger = DiscordInteractionLogger(dsn="postgresql://root:example@localhost:5432/postgres", rag_name="docgpt")
logger.export_csv(Path("discord_interactions.csv"))
```

## How to use
Ask about the R data.table package documentation and contribution guide.

1. Set envars in .env file, use the .env.example file as an example;
2. Run ```docker compose up```
3. Ingest data (once): ```uv run python main.py --ingest```
4. Start the Discord bot: ```uv run python main.py```
