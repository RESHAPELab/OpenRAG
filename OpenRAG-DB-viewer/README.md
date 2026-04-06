# OpenRAG Responses DB Viewer

A local Streamlit web UI for inspecting, filtering, and exporting evaluation
responses stored in either:

- **PostgreSQL** -- the `discord_interaction_logs` table (user messages, RAG
  answers, LLM answers, Discord metadata, candidate answers, feedback)
- **SQLite** -- the `evaluation_logs` table (evaluation pipeline results)
- **Any table** -- the viewer auto-discovers all tables in the database and lets
  you pick which one to browse.

Built for the [OpenRAG](https://github.com/RESHAPELab/OpenRAG) project.

## Features

- **Dual backend** -- switch between PostgreSQL and SQLite via a sidebar toggle.
- **Auto table discovery** -- connects and lists all available tables; no
  hard-coded table names required.
- **Configurable connection** -- enter a DSN for PostgreSQL or a file path for
  SQLite. Supports `DB_VIEWER_DSN` env var for automation.
- **Dynamic schema** -- columns, filters, and dropdowns adapt automatically.
- **Filtering** -- dropdown filters, timestamp range with presets (24h/7d/30d),
  free-text search, answer presence checks, min-length, ID range.
- **Pagination & sorting** -- browse large result sets efficiently.
- **Column visibility toggles** -- hide/show any column.
- **Row detail panel** -- full wrapped text, candidate answers, feedback info.
- **Diff view** -- side-by-side, inline word-diff, or unified diff between
  `rag_answer` and `llm_answer`, plus Jaccard overlap score.
- **Export** -- download filtered results as CSV or JSONL.
- **Read-only SQL console** -- run arbitrary `SELECT` queries with optional
  `EXPLAIN QUERY PLAN` (SQLite) or `EXPLAIN ANALYZE` (PostgreSQL).

## Prerequisites

- Python 3.10+
- pip
- For EC2 connection: SSH access with a `.pem` key file

## Installation

```bash
pip install -r requirements.txt
```

## Running the viewer

### Option 1: Direct connection (local database)

```bash
streamlit run app.py
```

Then configure the DSN or file path in the sidebar.

### Option 2: Connect to EC2 via SSH tunnel (recommended for production data)

The production Discord bot runs on an Amazon EC2 instance. The connect scripts
handle the SSH tunnel automatically.

**Windows (PowerShell):**

```powershell
.\connect.ps1 -SshKey "C:\path\to\your-key.pem" -Ec2Host "YOUR_EC2_IP" -Ec2User "YOUR_USER"
```

**Linux / macOS:**

```bash
chmod +x connect.sh
./connect.sh -k ~/.ssh/your-key.pem -h YOUR_EC2_IP -u YOUR_USER
```

The scripts will:
1. Open an SSH tunnel (`localhost:15432 -> EC2:5432`)
2. Set the `DB_VIEWER_DSN` environment variable
3. Launch Streamlit
4. Clean up the tunnel on exit

**Environment variables (optional, avoids typing every time):**

| Variable | Description | Example |
|---|---|---|
| `EC2_SSH_KEY_PATH` | Path to `.pem` file | `~/.ssh/my-key.pem` |
| `EC2_HOST` | EC2 public IP or hostname | `3.14.15.92` |
| `EC2_SSH_USER` | SSH username | `ubuntu` |
| `DB_VIEWER_DSN` | Full PostgreSQL DSN (overrides sidebar default) | `postgresql://root:example@localhost:15432/postgres` |

### Option 3: Manual SSH tunnel

If you prefer to manage the tunnel yourself:

```bash
# Terminal 1: open the tunnel
ssh -i ~/.ssh/your-key.pem -L 15432:localhost:5432 -N your_user@YOUR_EC2_IP

# Terminal 2: run the viewer
set DB_VIEWER_DSN=postgresql://root:example@localhost:15432/postgres
streamlit run app.py
```

## CI / GitHub Actions

On push to `main`, the workflow in `.github/workflows/ci.yml`:
1. Runs import checks and unit tests (SQL validation, diff utilities)
2. Creates an auto-tagged GitHub Release

### GitHub Secrets (for future CI enhancements)

If you want CI to run integration tests against EC2:

| Secret | Description |
|---|---|
| `EC2_HOST` | EC2 public IP or hostname |
| `EC2_SSH_USER` | SSH username |
| `EC2_SSH_KEY` | Contents of the `.pem` private key |

## Manual test steps

1. **Launch viewer** -- `streamlit run app.py`, select PostgreSQL, enter DSN.
2. **Verify table discovery** -- confirm the table dropdown shows available tables.
3. **Verify rows load** sorted newest-first.
4. **Filter by dropdown** -- select a value, confirm table updates.
5. **Free-text search** -- type a keyword from a known question.
6. **Export CSV** -- click "Export CSV", open the file, verify contents.
7. **Row detail** -- select a row ID, verify all columns display.
8. **Diff view** -- switch to Diff View tab, enter a row ID, verify
   side-by-side display and Jaccard score.
9. **SQL console** -- run `SELECT COUNT(*) FROM discord_interaction_logs;`
10. **SQL guard** -- try `DROP TABLE discord_interaction_logs;`, confirm blocked.
11. **Bad connection** -- enter a bogus DSN, confirm friendly error message.

## Project structure

```
OpenRAG-DB-viewer/
  app.py               Streamlit entrypoint (dual-backend UI)
  db_utils.py           Database connection, query builder, export helpers
  diff_utils.py         Diff rendering and text-similarity metrics
  connect.ps1           Windows launch script with SSH tunnel
  connect.sh            Linux/macOS launch script with SSH tunnel
  requirements.txt      Python dependencies
  .github/workflows/    CI: smoke tests + auto-release
  README.md             This file
```

## License

Same as the parent OpenRAG project.
