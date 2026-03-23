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

## How to use
Ask about the R data.table package documentation and contribution guide.

1. Set envars in .env file, use the .env.example file as an example;
2. Run ```docker compose up```
3. Ingest data (once): ```uv run python main.py --ingest```
4. Start the Discord bot: ```uv run python main.py```

## Manual bot testing with separate test DB

Use this flow when you want to interact with the bot in Discord without touching normal dev data.

1. Create a test env file from the template:
   ```powershell
   Copy-Item .env.test.example .env.test
   ```
2. Fill in `AI_GEMINI_APIKEY` and `APP_DISCORD_TOKEN` in `.env.test`.
3. Start isolated test databases:
   ```powershell
   docker compose -f docker-compose.test.yml up -d
   ```
4. Load `.env.test` into the current PowerShell session:
   ```powershell
   Get-Content .env.test | ForEach-Object {
     if ($_ -match '^\s*#' -or $_ -match '^\s*$') { return }
     $name, $value = $_ -split '=', 2
     Set-Item -Path "Env:$name" -Value $value
   }
   ```
5. Ingest documents into the test vector database:
   ```powershell
   uv run python main.py --ingest
   ```
6. Run the Discord bot using the test DB settings:
   ```powershell
   uv run python main.py
   ```
7. Tear down and wipe test data when done:
   ```powershell
   docker compose -f docker-compose.test.yml down -v
   ```

This keeps vector data and chat memory isolated to test services (`localhost:55432`, `localhost:27018`) and removes persisted test data on teardown.

## Run a second bot on EC2 (side-by-side with prod)

Use this when your production bot is already running and you want a separate test bot process.

1. Create a second Discord bot application/token (test-only) and add it to a test server.
2. Prepare test environment values:
   ```bash
   cp .env.test.example .env.test
   ```
3. Edit `.env.test` and set:
   - `APP_DISCORD_TOKEN` to the test bot token
   - `AI_GEMINI_APIKEY`
4. Ingest test data once:
   ```bash
   set -a && source .env.test && set +a
   docker compose -f docker-compose.test.yml up -d
   uv run python main.py --ingest
   ```
5. Run the second bot:
   ```bash
   ./run-test-bot.sh
   ```

Notes:
- Do not reuse the production bot token for the test bot.
- Production bot keeps using `.env`; test bot uses `.env.test`.
- Stop and wipe test data when finished:
  ```bash
  docker compose -f docker-compose.test.yml down -v
  ```
