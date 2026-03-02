# In-Depth Documentation

Complete reference for running the RAG Evaluation Framework, the DocGPT RAG system, the test suites, and configuring logging across the entire project.

---

## Table of Contents

- [1. Prerequisites and Environment Setup](#1-prerequisites-and-environment-setup)
  - [1.1 System Requirements](#11-system-requirements)
  - [1.2 Installing the Evaluation Framework](#12-installing-the-evaluation-framework)
  - [1.3 Installing DocGPT (The RAG System)](#13-installing-docgpt-the-rag-system)
  - [1.4 Environment Variables Reference](#14-environment-variables-reference)
- [2. Running the Evaluator](#2-running-the-evaluator)
  - [2.1 Overview of Evaluators](#21-overview-of-evaluators)
  - [2.2 Basic Evaluator (Rule-Based)](#22-basic-evaluator-rule-based)
  - [2.3 Ragas Evaluator (LLM-Based)](#23-ragas-evaluator-llm-based)
  - [2.4 Qualitative Logger](#24-qualitative-logger)
  - [2.5 Command-Line Evaluation Tools](#25-command-line-evaluation-tools)
  - [2.6 Data Ingestion and Supported Formats](#26-data-ingestion-and-supported-formats)
  - [2.7 Interpreting Evaluation Results](#27-interpreting-evaluation-results)
- [3. Running the RAG System (DocGPT)](#3-running-the-rag-system-docgpt)
  - [3.1 Architecture Overview](#31-architecture-overview)
  - [3.2 Infrastructure Setup (Docker)](#32-infrastructure-setup-docker)
  - [3.3 Ingesting Data into the Vector Store](#33-ingesting-data-into-the-vector-store)
  - [3.4 Running the Discord Bot](#34-running-the-discord-bot)
  - [3.5 Running the FastAPI Server](#35-running-the-fastapi-server)
  - [3.6 Automatic Interaction Logging](#36-automatic-interaction-logging)
  - [3.7 Configuration Deep Dive](#37-configuration-deep-dive)
  - [3.8 Troubleshooting DocGPT](#38-troubleshooting-docgpt)
- [4. Running the Tests](#4-running-the-tests)
  - [4.1 Evaluation Framework Tests](#41-evaluation-framework-tests)
  - [4.2 DocGPT Tests](#42-docgpt-tests)
  - [4.3 Continuous Integration (CI)](#43-continuous-integration-ci)
  - [4.4 Linting and Type Checking](#44-linting-and-type-checking)
- [5. Logging](#5-logging)
  - [5.1 DocGPT Logging Configuration](#51-docgpt-logging-configuration)
  - [5.2 Changing Log Levels](#52-changing-log-levels)
  - [5.3 Automatic Interaction Logs (CSV + JSONL)](#53-automatic-interaction-logs-csv--jsonl)
  - [5.4 Evaluation Framework Logging](#54-evaluation-framework-logging)
  - [5.5 Qualitative Logging Output](#55-qualitative-logging-output)
  - [5.6 Debugging with LangChain Verbose Mode](#56-debugging-with-langchain-verbose-mode)

---

## 1. Prerequisites and Environment Setup

### 1.1 System Requirements

| Component | Requirement |
|-----------|-------------|
| Python | 3.10+ (3.11+ for DocGPT) |
| Docker & Docker Compose | Required for DocGPT infrastructure (PostgreSQL + MongoDB) |
| `uv` | Required for DocGPT dependency management ([install guide](https://docs.astral.sh/uv/getting-started/installation/)) |
| `pip` | Required for the evaluation framework |
| Pandoc | Required by DocGPT for document conversion (`pypandoc` will attempt auto-install) |
| Git | For cloning the repository |

### 1.2 Installing the Evaluation Framework

```bash
# Clone the repository
git clone https://github.com/RESHAPELab/RAG-evaluation.git
cd RAG-evaluation

# Install core dependencies (includes ragas for LLM-based evaluation)
pip install -r requirements.txt

# Install the package itself in editable mode (recommended for development)
pip install -e .

# Install optional extras
pip install -e ".[dev]"      # pytest, ruff, mypy for development
pip install -e ".[excel]"    # openpyxl for Excel file support
pip install -e ".[bibtex]"   # bibtexparser for advanced BibTeX parsing

# Or install everything at once
pip install -e ".[dev,excel,bibtex]"
```

**Verify the installation:**

```bash
python -c "from rag_evaluation import RAGEvaluator; print('Evaluation framework OK')"
```

### 1.3 Installing DocGPT (The RAG System)

```bash
# Navigate to the DocGPT directory
cd systems/docgpt

# Install uv if you don't have it
# Windows (PowerShell):
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
# macOS/Linux:
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install all dependencies (reads pyproject.toml and uv.lock)
uv sync

# Install dev dependencies too
uv sync --dev

# Copy the environment template and fill in your keys
cp .env.example .env
# Edit .env with your actual values (see Section 1.4)
```

### 1.4 Environment Variables Reference

#### Evaluation Framework

| Variable | Required For | Description |
|----------|-------------|-------------|
| `OPENAI_API_KEY` | `RagasEvaluator` only | OpenAI API key for LLM-based metrics. Get one at https://platform.openai.com/api-keys |

> **Note:** The basic `RAGEvaluator` (rule-based) requires **no** API keys or external services.

#### DocGPT

Set these in `systems/docgpt/.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AI_GEMINI_APIKEY` | Yes | — | Google Gemini API key |
| `APP_DISCORD_TOKEN` | Yes (for bot) | — | Discord bot token |
| `STORAGE_VECTOR_URL` | No | `postgresql+psycopg://root:example@localhost:5432/postgres` | PostgreSQL connection string for vector storage |
| `STORAGE_MEMORY_URL` | No | `mongodb://root:example@localhost:27017` | MongoDB connection string for chat memory |
| `LOG_LEVEL` | No | `DEBUG` | Logging level (`DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`) |
| `AI_GEMINI_MODEL` | No | `gemini-1.5-flash` | Gemini model name to use |
| `ASSISTANT_K` | No | `100` | Number of retrieval results |
| `ASSISTANT_TOKENS_LIMIT` | No | `2000` | Maximum tokens in retrieval context |
| `ASSISTANT_SCORE_THRESHOLD` | No | `null` | Minimum similarity score filter |
| `DISTANCE_THRESHOLD` | No | `null` | Maximum distance threshold for retrieval |
| `API_PORT` | No | `8000` | Port for the FastAPI server |
| `INTERACTION_LOG_DIR` | No | `logs` | Directory for automatic interaction log files (CSV + JSONL) |

---

## 2. Running the Evaluator

### 2.1 Overview of Evaluators

The framework provides three main evaluation tools:

| Tool | Type | API Key Required | Use Case |
|------|------|-----------------|----------|
| `RAGEvaluator` | Rule-based metrics | No | Fast, deterministic, cost-free evaluation |
| `RagasEvaluator` | LLM-based metrics (via ragas) | Yes (`OPENAI_API_KEY`) | Sophisticated semantic evaluation |
| `QualitativeLogger` | Structured logging | No | Side-by-side RAG vs LLM comparison logging |

### 2.2 Basic Evaluator (Rule-Based)

The `RAGEvaluator` uses keyword-overlap heuristics to compute three metrics:

- **Faithfulness** — Is the answer grounded in the provided context?
- **Context Precision** — Does the answer come from the ground truth? (requires `ground_truth`)
- **Relevance** — Does the answer address the query and use the context?

#### Single Evaluation

```python
from rag_evaluation import RAGEvaluator

evaluator = RAGEvaluator()

results = evaluator.evaluate(
    query="What is machine learning?",
    context="Machine learning is a subset of AI that enables systems to learn and improve from experience without being explicitly programmed.",
    answer="Machine learning is a subset of artificial intelligence. It allows systems to learn from experience without explicit programming.",
    ground_truth="Machine learning is a subset of AI that enables systems to learn and improve from experience without being explicitly programmed."
)

# Print each metric
for metric_name, metric_result in results.items():
    print(f"{metric_name}: {metric_result['score']:.3f}")
    print(f"  Details: {metric_result['details']['reasoning']}")
```

**Example output:**

```
faithfulness: 1.000
  Details: 2 out of 2 sentences are grounded in context
context_precision: 0.750
  Details: 6 out of 8 answer terms found in ground truth
relevance: 0.629
  Details: Answer addresses 2/3 query terms and uses 7/17 context terms
```

#### Batch Evaluation

```python
evaluator = RAGEvaluator()

results = evaluator.evaluate_batch(
    queries=["What is ML?", "What is deep learning?"],
    contexts=["ML is a subset of AI that learns from data.", "Deep learning uses neural networks with many layers."],
    answers=["ML is a subset of AI.", "Deep learning uses multi-layered neural networks."],
    ground_truths=["ML is a subset of AI that learns from data.", "Deep learning uses multi-layered neural networks."]
)

# Get aggregated average scores
avg_scores = evaluator.get_average_scores(results)
print("Average scores:", avg_scores)
```

#### Using Specific Metrics Only

```python
# Only compute faithfulness and relevance (skip context_precision)
evaluator = RAGEvaluator(metrics=['faithfulness', 'relevance'])
results = evaluator.evaluate(query=query, context=context, answer=answer)
# results will only contain 'faithfulness' and 'relevance' keys
```

**Available metric names:** `faithfulness`, `context_precision`, `relevance`

#### Loading Data from Files

```python
from rag_evaluation import RAGEvaluator
from rag_evaluation.data_ingestion import DataTableLoader

loader = DataTableLoader()

# Load from CSV — the file must have columns: query, context, answer, ground_truth
data = loader.load_for_evaluation('examples/sample_data.csv')

evaluator = RAGEvaluator()
results = evaluator.evaluate_batch(**data)
avg_scores = evaluator.get_average_scores(results)

print("Results per sample:", results)
print("Average scores:", avg_scores)
```

### 2.3 Ragas Evaluator (LLM-Based)

The `RagasEvaluator` wraps the [ragas](https://docs.ragas.io/) library and uses an LLM (OpenAI by default) for semantic evaluation. It provides four metrics:

- **Faithfulness** — Factual consistency via LLM claim verification
- **Answer Relevancy** — Semantic relevance of the answer to the query
- **Context Precision** — How relevant the retrieved context is
- **Context Recall** — Whether all needed information was retrieved (requires `ground_truth`)

#### Setup

```bash
# Set your OpenAI API key
# Windows (PowerShell):
$env:OPENAI_API_KEY = "sk-your-key-here"

# macOS/Linux:
export OPENAI_API_KEY="sk-your-key-here"
```

#### Single Evaluation

```python
from rag_evaluation import RagasEvaluator

evaluator = RagasEvaluator()

results = evaluator.evaluate(
    query="What is machine learning?",
    context="Machine learning is a subset of AI that enables systems to learn...",
    answer="Machine learning allows computers to learn from data...",
    ground_truth="Machine learning is a subset of AI..."
)

for metric_name, metric_result in results.items():
    print(f"{metric_name}: {metric_result['score']}")
```

#### Batch Evaluation

```python
evaluator = RagasEvaluator()

results = evaluator.evaluate_batch(
    queries=["What is ML?", "What is DL?"],
    contexts=["ML is...", "DL is..."],
    answers=["ML allows...", "DL uses..."],
    ground_truths=["ML is...", "DL is..."]
)

avg_scores = evaluator.get_average_scores(results)
print("Average ragas scores:", avg_scores)
```

#### Custom Metric Selection

```python
# Only use faithfulness and answer_relevancy
evaluator = RagasEvaluator(metrics=['faithfulness', 'answer_relevancy'])
```

**Available metric names:** `faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`

#### Comparing Both Evaluators

```python
from rag_evaluation import RAGEvaluator, RagasEvaluator

query = "What is machine learning?"
context = "Machine learning is a subset of AI that enables systems to learn..."
answer = "ML is a type of AI that learns from data."

# Rule-based
basic = RAGEvaluator()
basic_results = basic.evaluate(query, context, answer)
print("Basic:", {k: v['score'] for k, v in basic_results.items()})

# LLM-based
ragas = RagasEvaluator()
ragas_results = ragas.evaluate(query, context, answer)
print("Ragas:", {k: v['score'] for k, v in ragas_results.items()})
```

### 2.4 Qualitative Logger

The `QualitativeLogger` records RAG-augmented answers alongside direct LLM answers for human review. It outputs to CSV (for Excel/Google Sheets) and JSON (for scripts).

#### Programmatic Usage

```python
from rag_evaluation import QualitativeLogger, LogEntry, RAGEvaluator

logger = QualitativeLogger()

# Log a single entry
logger.log(LogEntry(
    category="factual",
    model_name="gemini-1.5-flash",
    question="What is data.table?",
    rag_context="data.table is an R package that provides an enhanced version of data.frame...",
    rag_answer="data.table is an R package that extends data.frame with fast aggregation...",
    llm_answer="data.table is a popular R package used for data manipulation...",
))

# Optionally attach evaluation scores
evaluator = RAGEvaluator()
scores = evaluator.evaluate(
    query="What is data.table?",
    context="data.table is an R package...",
    answer="data.table is an R package that extends...",
)

logger.log(LogEntry(
    category="code",
    model_name="gemini-1.5-flash",
    question="How to read CSV with data.table?",
    rag_context="Use fread() to read files...",
    rag_answer="Use fread() for fast CSV reading...",
    llm_answer="Use read.csv() to read CSV files...",
    evaluation_scores=scores,
))

# Save to disk (creates both CSV and JSON)
written_files = logger.save(output_dir="output/logs")
print(written_files)
# {'csv': 'output/logs/qualitative_log_2026-02-11_143022.csv',
#  'json': 'output/logs/qualitative_log_2026-02-11_143022.json'}
```

#### Output Formats

**CSV output** — flat table, one row per entry. Evaluation scores are flattened into individual columns:

| timestamp | category | model_name | question | rag_context | rag_answer | llm_answer | faithfulness | context_precision | relevance |
|-----------|----------|------------|----------|-------------|------------|------------|--------------|-------------------|-----------|
| 2026-02-11T14:30:22 | factual | gemini-1.5-flash | What is data.table? | data.table is... | data.table extends... | data.table is a library... | | | |
| 2026-02-11T14:30:23 | code | gemini-1.5-flash | How to read CSV? | Use fread()... | Use fread()... | Use read.csv()... | 0.85 | 0.72 | 0.64 |

**JSON output** — structured array of objects with nested `evaluation_scores`.

#### Save Format Options

```python
# Save only CSV
logger.save(output_dir="logs", formats=["csv"])

# Save only JSON
logger.save(output_dir="logs", formats=["json"])

# Custom filename prefix
logger.save(output_dir="logs", filename_prefix="my_experiment")
# Creates: logs/my_experiment_2026-02-11_143022.csv
```

### 2.5 Command-Line Evaluation Tools

#### `evaluate.py` — Quantitative Evaluation

Run evaluation on a data file directly from the command line:

```bash
# Basic usage (auto-detects file format)
python examples/evaluate.py examples/sample_data.csv

# Verbose output (prints per-sample details)
python examples/evaluate.py examples/sample_data.csv --verbose

# Save results to a JSON file
python examples/evaluate.py examples/sample_data.csv --output results.json

# Specify file format explicitly
python examples/evaluate.py examples/sample_data.bib --type bibtex

# Select specific metrics
python examples/evaluate.py examples/sample_data.csv --metrics faithfulness relevance

# Combine options
python examples/evaluate.py data.json --verbose --output results.json --metrics faithfulness context_precision relevance
```

**Full CLI reference:**

```
usage: evaluate.py [-h] [--type {csv,json,bibtex,auto}] [--output OUTPUT]
                   [--metrics {faithfulness,context_precision,relevance} ...]
                   [--verbose]
                   data_file

positional arguments:
  data_file             Path to the evaluation data file

optional arguments:
  --type                Input format (default: auto)
  --output              Save results to this JSON file
  --metrics             Metrics to compute (default: all)
  --verbose, -v         Print detailed per-sample output
```

#### `qualitative_eval.py` — Qualitative Logging

Log RAG vs LLM answers from a data file:

```bash
# Basic usage — logs to logs/ directory as CSV + JSON
python examples/qualitative_eval.py examples/sample_qualitative_data.csv

# Custom output directory with verbose console output
python examples/qualitative_eval.py data.csv --output-dir results/logs --verbose

# Include evaluation metric scores in the log
python examples/qualitative_eval.py data.csv --with-scores --verbose

# Override model name and select specific scoring metrics
python examples/qualitative_eval.py data.csv --model-name gemini-2.0-flash --with-scores --metrics faithfulness relevance
```

**Full CLI reference:**

```
usage: qualitative_eval.py [-h] [--type {csv,json,excel,auto}]
                           [--output-dir OUTPUT_DIR] [--model-name MODEL_NAME]
                           [--with-scores]
                           [--metrics {faithfulness,context_precision,relevance} ...]
                           [--verbose]
                           data_file

positional arguments:
  data_file             Path to input data file (CSV, JSON, or Excel)

optional arguments:
  --type                Input format (default: auto)
  --output-dir          Directory for log files (default: logs/)
  --model-name          Override the model name for all entries
  --with-scores         Compute evaluation metrics and attach to entries
  --metrics             Which metrics to compute (default: all)
  --verbose, -v         Print detailed per-entry output
```

**Required CSV columns for qualitative logging:**

```csv
category,model_name,question,rag_context,rag_answer,llm_answer
factual,gemini-1.5-flash,"What is data.table?","data.table is...","data.table is a package...","data.table is a library..."
```

### 2.6 Data Ingestion and Supported Formats

#### DataTableLoader (CSV, JSON, Excel)

```python
from rag_evaluation.data_ingestion import DataTableLoader

loader = DataTableLoader()

# Load raw records
records = loader.load('data.csv')          # Returns List[Dict]
records = loader.load('data.json')         # Auto-detects format
records = loader.load('data.xlsx')         # Requires openpyxl

# Load ready for evaluation (returns dict with queries, contexts, answers, ground_truths)
data = loader.load_for_evaluation('data.csv')

# Load ready for qualitative logging
data = loader.load_for_qualitative_logging('qualitative_data.csv')

# Custom column mapping
data = loader.load_for_evaluation(
    'data.csv',
    query_column='question',       # default: 'query'
    context_column='retrieved',    # default: 'context'
    answer_column='response',      # default: 'answer'
    ground_truth_column='expected' # default: 'ground_truth'
)
```

**CSV format for evaluation:**

```csv
query,context,answer,ground_truth
"What is ML?","ML is a subset of AI...","ML allows computers to learn...","ML is a subset of AI..."
```

**JSON format for evaluation:**

```json
[
  {
    "query": "What is ML?",
    "context": "ML is a subset of AI...",
    "answer": "ML allows computers to learn...",
    "ground_truth": "ML is a subset of AI..."
  }
]
```

#### JabrefLoader (BibTeX)

```python
from rag_evaluation.data_ingestion import JabrefLoader

loader = JabrefLoader()

# Load raw entries
entries = loader.load('references.bib')

# Load ready for evaluation
data = loader.load_for_evaluation('references.bib')
```

**BibTeX field mapping:**

| BibTeX Field | Maps To |
|-------------|---------|
| `title` | `query` |
| `abstract` (or `note`) | `context` |
| `abstract` | `ground_truth` |

### 2.7 Interpreting Evaluation Results

All metrics return a dictionary with `score` (float 0.0–1.0) and `details` (dict with reasoning):

```python
{
    'faithfulness': {
        'score': 0.857,
        'details': {
            'total_sentences': 7,
            'supported_sentences': 6,
            'unsupported_sentences': ['One hallucinated sentence here.'],
            'reasoning': '6 out of 7 sentences are grounded in context'
        }
    },
    'context_precision': {
        'score': 0.75,
        'details': {
            'answer_terms_count': 8,
            'ground_truth_overlap': 6,
            'context_overlap': 7,
            'precision_percentage': '75.0%',
            'reasoning': '6 out of 8 answer terms found in ground truth'
        }
    },
    'relevance': {
        'score': 0.63,
        'details': {
            'query_relevance': 0.67,
            'context_relevance': 0.53,
            'query_terms_in_answer': 2,
            'total_query_terms': 3,
            'context_terms_in_answer': 7,
            'total_context_terms': 13,
            'reasoning': 'Answer addresses 2/3 query terms and uses 7/13 context terms'
        }
    }
}
```

**Score interpretation guide:**

| Score Range | Rating | Recommended Action |
|-------------|--------|--------------------|
| 0.8–1.0 | Excellent | Model is performing well |
| 0.6–0.8 | Good | Minor improvements possible |
| 0.4–0.6 | Fair | Review model configuration and data |
| 0.0–0.4 | Poor | Significant issues — needs attention |

**Metric-specific troubleshooting:**

| Low Score In | Likely Problem | Solutions |
|-------------|---------------|-----------|
| Faithfulness | Model is hallucinating | Improve context quality, lower temperature, add grounding instructions |
| Context Precision | Model not using correct sources | Improve retrieval ranking, verify ground truth quality |
| Relevance | Answer misses the question | Better prompt engineering, ensure context is relevant to query |

---

## 3. Running the RAG System (DocGPT)

DocGPT is a Retrieval-Augmented Generation system that answers questions about the R `data.table` package. It retrieves relevant documentation from a vector store and uses Google Gemini to generate answers. It runs as either a Discord bot or a FastAPI HTTP server.

### 3.1 Architecture Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                          DocGPT                                  │
│                                                                  │
│  ┌──────────┐    ┌──────────────┐    ┌────────────────────┐     │
│  │ Discord   │    │  Assistant    │    │  Google Gemini     │     │
│  │ Bot / API │───▶│  (LangChain)  │───▶│  LLM               │     │
│  └──────────┘    └──────┬───────┘    └────────────────────┘     │
│                         │                                        │
│                         ▼                                        │
│              ┌──────────────────┐                                │
│              │ Vector Store      │                                │
│              │ (PostgreSQL +     │                                │
│              │  pgvector)        │                                │
│              └──────────────────┘                                │
│                                                                  │
│              ┌──────────────────┐                                │
│              │ Memory Store      │                                │
│              │ (MongoDB)         │                                │
│              └──────────────────┘                                │
└─────────────────────────────────────────────────────────────────┘
```

**Key components:**

| Component | Technology | Purpose |
|-----------|-----------|---------|
| LLM | Google Gemini (via `langchain-google-genai`) | Generates answers |
| Vector Store | PostgreSQL + pgvector (via `langchain-postgres`) | Stores and retrieves document embeddings |
| Memory Store | MongoDB (via `pymongo`) | Persists chat history per session |
| Interface | Discord bot (`py-cord`) or FastAPI | User-facing interface |
| Content ingestion | Git clone + text splitting | Ingests data.table repo and wiki |
| Config | `config.yml` with env var interpolation | All settings in one place |
| DI Container | `dependency-injector` | Wires all components together |

### 3.2 Infrastructure Setup (Docker)

DocGPT requires PostgreSQL (with pgvector) and MongoDB. Both are provided via Docker Compose.

```bash
cd systems/docgpt

# Start infrastructure services in the background
docker compose up -d

# Verify services are running
docker compose ps
```

**Expected output:**

```
NAME              IMAGE            STATUS          PORTS
vector_storage    ankane/pgvector  Up              0.0.0.0:5432->5432/tcp
memory_storage    mongo            Up              0.0.0.0:27017->27017/tcp
```

**Ports used:**

| Service | Port | Protocol |
|---------|------|----------|
| PostgreSQL (pgvector) | 5432 | TCP |
| MongoDB | 27017 | TCP |

> **Conflict warning:** If another PostgreSQL instance is already running on port 5432, you will get a "password authentication failed" error. Either stop the other service or update `STORAGE_VECTOR_URL` in your `.env` with the correct credentials.

**Stopping infrastructure:**

```bash
docker compose down          # Stop containers
docker compose down -v       # Stop and remove volumes (deletes all data)
```

### 3.3 Ingesting Data into the Vector Store

Before the bot can answer questions, you must ingest the data.table documentation into the vector store. This is a one-time operation (or whenever you want to refresh the data).

```bash
cd systems/docgpt

# Make sure Docker services are running
docker compose up -d

# Run the ingestion
uv run python main.py --ingest
```

**What happens during ingestion:**

1. Clones the `Rdatatable/data.table` repository (code + wiki) into `assets/`
2. Converts documents (Markdown, code files) into text using pypandoc
3. Splits documents into chunks using LangChain text splitters
4. Generates embeddings and stores them in PostgreSQL via pgvector

**Ingestion logs** will appear on stderr (see [Section 5](#5-logging)):

```
[2026-02-11 14:30:22] [INFO] [__main__]: Fetching wiki documents...
[2026-02-11 14:30:25] [INFO] [__main__]: Fetching code documents...
[2026-02-11 14:30:45] [WARNING] [__main__]: Total of 3 documents failed to ingest
[2026-02-11 14:30:45] [INFO] [__main__]: Failed files summary: [...]
```

> **Note:** Some files may fail to ingest (e.g., binary files, malformed documents). The system logs each failure with the file name, file type, file path, exception type, and reason. These failures are non-fatal — the rest of the documents are still ingested successfully.

### 3.4 Running the Discord Bot

```bash
cd systems/docgpt

# Make sure Docker services are running
docker compose up -d

# Start the Discord bot
uv run python main.py
```

The bot will log in to Discord and listen for messages. You can interact with it by asking questions about the R data.table package in your Discord server.

**Console output on startup:**

```
[2026-02-11 14:31:00] [DEBUG] [src.app.discord]: Logged in as DocGPT#1234 (ID: 123456789)
```

### 3.5 Running the FastAPI Server

Instead of the Discord bot, you can run DocGPT as an HTTP API:

```bash
cd systems/docgpt

# Make sure Docker services are running
docker compose up -d

# Start the FastAPI server
uv run python main.py --api
```

The server starts on port 8000 by default (configurable via `API_PORT` env var).

**API documentation** is available at:
- Swagger UI: `http://localhost:8000/docs`
- ReDoc: `http://localhost:8000/redoc`

The API response now includes the retrieved context alongside the answer:

```json
{
  "question": "What is data.table?",
  "answer": "data.table is an R package that extends data.frame...",
  "retrieved_context": "data.table is an R package that provides...",
  "source_count": 5,
  "session_id": "test-session"
}
```

### 3.6 Automatic Interaction Logging

Every question asked to DocGPT — whether through the Discord bot, the FastAPI server, or the terminal CLI — is **automatically logged** to structured files on disk. Each interaction records:

- **Timestamp** — when the question was asked
- **Session ID** — the Discord thread ID, API session, or `"cli"`
- **Question** — the user's original question
- **Retrieved Context** — the full text of all document chunks retrieved from the vector store
- **Answer** — the LLM-generated response
- **Source Count** — how many document chunks were retrieved
- **Source Metadata** — file names, paths, and projects of retrieved documents (JSONL only)

#### Where the Logs Go

By default, logs are written to `systems/docgpt/logs/`. A pair of files is created each time the bot starts:

```
logs/
├── interactions_2026-02-11_143022.csv      ← open in Excel / Google Sheets
└── interactions_2026-02-11_143022.jsonl    ← parse with Python or any JSON tool
```

Each interaction is **appended immediately** after it occurs, so nothing is lost if the process crashes.

**To change the log directory,** set the `INTERACTION_LOG_DIR` environment variable:

```bash
# Windows (PowerShell)
$env:INTERACTION_LOG_DIR = "C:\my_logs"
uv run python main.py

# macOS/Linux
INTERACTION_LOG_DIR=/var/log/docgpt uv run python main.py
```

At startup you will see a confirmation message:

```
[2026-02-11 14:30:22] [INFO] [__main__]: Interaction logs: CSV=logs/interactions_2026-02-11_143022.csv, JSONL=logs/interactions_2026-02-11_143022.jsonl
```

#### CSV Format

Open the CSV in Excel or Google Sheets. Each row is one interaction:

| timestamp | session_id | question | retrieved_context | answer | source_count |
|-----------|------------|----------|-------------------|--------|-------------|
| 2026-02-11T14:30:22 | 1234567890 | What is data.table? | data.table is an R package that... | data.table extends data.frame... | 5 |

#### JSONL Format

Each line in the JSONL file is a self-contained JSON object with all fields plus the full source metadata:

```json
{
  "timestamp": "2026-02-11T14:30:22",
  "session_id": "1234567890",
  "question": "What is data.table?",
  "retrieved_context": "data.table is an R package that...",
  "answer": "data.table extends data.frame...",
  "source_count": 5,
  "source_metadata": [
    {"file_name": "README.md", "project": "data.table", "source": "wiki"},
    {"file_name": "data.table.Rmd", "project": "data.table", "source": "code"}
  ]
}
```

**To parse the JSONL file in Python:**

```python
import json

with open("logs/interactions_2026-02-11_143022.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        print(f"Q: {entry['question']}")
        print(f"A: {entry['answer'][:80]}...")
        print(f"  Sources: {entry['source_count']} chunks retrieved")
        print()
```

#### Testing the Auto-Logging

The fastest way to verify logging is via the FastAPI server:

```bash
cd systems/docgpt
docker compose up -d
uv run python main.py --ingest   # one-time
uv run python main.py --api
```

In another terminal, send a test request:

```bash
curl -X POST http://localhost:8000/api/v1/assistant/prompt -H "Content-Type: application/json" -d "{\"message\": \"What is data.table?\", \"session_id\": \"test\"}"
```

Then check `systems/docgpt/logs/` — you will find the CSV and JSONL files with your interaction logged.

#### Feeding Logs into the Evaluation Framework

The logged interactions can be used as input for the evaluation framework to score the RAG system:

```python
import json
from rag_evaluation import RAGEvaluator

evaluator = RAGEvaluator()

with open("systems/docgpt/logs/interactions_2026-02-11_143022.jsonl") as f:
    for line in f:
        entry = json.loads(line)
        scores = evaluator.evaluate(
            query=entry["question"],
            context=entry["retrieved_context"],
            answer=entry["answer"],
        )
        print(f"Q: {entry['question']}")
        for metric, result in scores.items():
            print(f"  {metric}: {result['score']:.3f}")
```

### 3.7 Configuration Deep Dive

All DocGPT configuration lives in `systems/docgpt/config.yml`. Values use `${ENV_VAR:default}` syntax for environment variable interpolation.

**Full configuration structure:**

```yaml
core:
  logging:                           # Python logging dict-config
    version: 1
    formatters:
      formatter:
        format: "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
    handlers:
      console:
        class: "logging.StreamHandler"
        level: ${LOG_LEVEL:DEBUG}     # Controlled by LOG_LEVEL env var
        formatter: "formatter"
        stream: "ext://sys.stderr"    # Output to stderr
    root:
      level: ${LOG_LEVEL:DEBUG}
      handlers: ["console"]

ai:
  gemini:
    model_name: ${AI_GEMINI_MODEL:gemini-1.5-flash}
    api_key: ${AI_GEMINI_APIKEY}      # Required — no default

assistant:
  k: ${ASSISTANT_K:100}              # Top-K retrieval results
  tokens_limit: ${ASSISTANT_TOKENS_LIMIT:2000}
  score_threshold: ${ASSISTANT_SCORE_THRESHOLD:null}
  distance_threshold: ${DISTANCE_THRESHOLD:null}

storage:
  vector:
    backend: ${STORAGE_VECTOR_BACKEND:chroma}
    url: ${STORAGE_VECTOR_URL:postgresql+psycopg://root:example@localhost:5432/postgres}
  memory:
    url: ${STORAGE_MEMORY_URL:mongodb://root:example@localhost:27017}

app:
  discord:
    token: ${APP_DISCORD_TOKEN}       # Required — no default

api:
  port: ${API_PORT:8000}
```

### 3.8 Troubleshooting DocGPT

| Problem | Cause | Solution |
|---------|-------|----------|
| `password authentication failed` | Another PostgreSQL on port 5432 | Stop the other service or change `STORAGE_VECTOR_URL` |
| `AI_GEMINI_APIKEY` error | Missing API key | Set `AI_GEMINI_APIKEY` in `.env` |
| `APP_DISCORD_TOKEN` error | Missing Discord token | Set `APP_DISCORD_TOKEN` in `.env` |
| `pypandoc` errors | Pandoc not installed | Run `pypandoc.ensure_pandoc_installed()` or install Pandoc manually |
| Ingestion failures | Binary/malformed files | Non-fatal — check logs for details, other documents still work |
| Empty answers from bot | Data not ingested | Run `uv run python main.py --ingest` first |
| `uv: command not found` | uv not installed | Install uv: see [Section 1.3](#13-installing-docgpt-the-rag-system) |

---

## 4. Running the Tests

### 4.1 Evaluation Framework Tests

The evaluation framework has a comprehensive test suite under `tests/`:

| Test File | What It Tests |
|-----------|--------------|
| `tests/test_evaluator.py` | `RAGEvaluator` — initialization, single eval, batch eval, average scores |
| `tests/test_metrics.py` | Individual metrics — `FaithfulnessMetric`, `ContextPrecisionMetric`, `RelevanceMetric` |
| `tests/test_data_ingestion.py` | `DataTableLoader` — CSV loading, JSON loading, evaluation format, error handling |
| `tests/conftest.py` | Shared pytest fixtures (`evaluator`, `sample_data`, `batch_data`) |

#### Running All Tests

```bash
# From the repository root
cd RAG-evaluation

# Install dev dependencies
pip install -e ".[dev]"

# Run all tests with verbose output
pytest tests/ -v

# Run with short traceback format
pytest tests/ -v --tb=short
```

#### Running Tests with Coverage

```bash
# Run tests with coverage report
pytest tests/ -v --cov=rag_evaluation --cov-report=term-missing

# Generate HTML coverage report
pytest tests/ -v --cov=rag_evaluation --cov-report=html
# Open htmlcov/index.html in your browser

# Generate XML coverage report (for CI)
pytest tests/ -v --cov=rag_evaluation --cov-report=xml
```

#### Running Specific Tests

```bash
# Run only evaluator tests
pytest tests/test_evaluator.py -v

# Run only metric tests
pytest tests/test_metrics.py -v

# Run only data ingestion tests
pytest tests/test_data_ingestion.py -v

# Run a specific test class
pytest tests/test_evaluator.py::TestRAGEvaluatorEvaluate -v

# Run a specific test method
pytest tests/test_evaluator.py::TestRAGEvaluatorEvaluate::test_evaluate_returns_all_metrics -v

# Run tests matching a keyword
pytest tests/ -v -k "faithfulness"
```

#### Test Fixtures

The test suite provides reusable fixtures in `tests/conftest.py`:

- `evaluator` — A default `RAGEvaluator()` with all three metrics
- `evaluator_faithfulness_only` — A `RAGEvaluator(metrics=["faithfulness"])`
- `sample_data` — A dict with `query`, `context`, `answer`, `ground_truth` (for single evaluation)
- `batch_data` — A dict with `queries`, `contexts`, `answers`, `ground_truths` (for batch evaluation)

### 4.2 DocGPT Tests

DocGPT tests live in `systems/docgpt/tests/`. The test infrastructure is set up (with `conftest.py` and `fixtures/`), but test implementations are still being added.

```bash
cd systems/docgpt

# Install dev dependencies
uv sync --dev

# Run DocGPT tests
uv run pytest tests/ -v --tb=short
```

> **Note:** Since DocGPT tests are still being developed, the CI pipeline uses `|| echo "No tests found yet"` to avoid failing the build.

### 4.3 Continuous Integration (CI)

The GitHub Actions CI pipeline (`.github/workflows/ci.yml`) runs automatically on pushes and pull requests to `main`, `master`, and `develop` branches.

**CI Jobs:**

| Job | What It Does | Matrix |
|-----|-------------|--------|
| `lint` | Runs Ruff linter + formatter check | Python 3.11 |
| `type-check` | Runs mypy type checking on `rag_evaluation/` | Python 3.11 |
| `test` | Runs pytest with coverage on the evaluation framework | Python 3.10, 3.11, 3.12 |
| `test-docgpt` | Runs pytest on DocGPT tests | Python 3.11 |

**To replicate CI locally:**

```bash
# Lint check
ruff check . --output-format=github

# Format check
ruff format --check .

# Type check
mypy rag_evaluation/ --ignore-missing-imports

# Tests with coverage (replicates the CI test job)
pytest tests/ -v --tb=short --cov=rag_evaluation --cov-report=term-missing --cov-report=xml
```

### 4.4 Linting and Type Checking

#### Ruff (Linting and Formatting)

```bash
# Check for lint errors
ruff check .

# Auto-fix lint errors where possible
ruff check . --fix

# Check formatting
ruff format --check .

# Auto-format code
ruff format .
```

The Ruff configuration is in `pyproject.toml`:
- Line length: 100
- Target: Python 3.10
- Selected rules: `E` (pycodestyle errors), `F` (pyflakes), `I` (isort), `N` (pep8-naming), `UP` (pyupgrade)
- Ignored: `E501` (line too long — handled by formatter)

#### Mypy (Type Checking)

```bash
# Type check the evaluation framework
mypy rag_evaluation/ --ignore-missing-imports
```

---

## 5. Logging

### 5.1 DocGPT Logging Configuration

DocGPT uses Python's standard `logging` module configured via `config.yml`. The logging dictionary config is applied at startup via `dependency-injector` resource initialization.

**Default log format:**

```
[2026-02-11 14:30:22,123] [INFO] [__main__]: Your log message here
```

Format breakdown: `[timestamp] [level] [logger_name]: message`

**Default output:** All logs go to **stderr** (not stdout), which means they won't interfere with program output.

**Startup initialization in `main.py`:**

```python
application = containers.Settings()
application.config.from_yaml("config.yml", envs_required=True, required=True)
application.core.init_resources()  # <-- This applies logging.config.dictConfig()
```

### 5.2 Changing Log Levels

Set the `LOG_LEVEL` environment variable before starting DocGPT:

```bash
# Windows (PowerShell)
$env:LOG_LEVEL = "INFO"
uv run python main.py

# macOS/Linux
LOG_LEVEL=INFO uv run python main.py
```

**Available levels (from most to least verbose):**

| Level | Value | Shows |
|-------|-------|-------|
| `DEBUG` | 10 | Everything — includes LangChain internals, retrieval details |
| `INFO` | 20 | Operational messages — ingestion progress, startup info |
| `WARNING` | 30 | Only warnings and errors — e.g., failed document ingestion counts |
| `ERROR` | 40 | Only errors — e.g., individual document ingestion failures |
| `CRITICAL` | 50 | Only fatal errors |

**Recommended settings:**

| Scenario | Log Level |
|----------|-----------|
| Development / debugging | `DEBUG` |
| Normal operation | `INFO` |
| Production / quiet mode | `WARNING` |

### 5.3 Automatic Interaction Logs (CSV + JSONL)

DocGPT automatically logs every RAG interaction to disk. This is separate from Python's `logging` module — it produces structured data files you can open in Excel or parse with scripts.

See [Section 3.6 — Automatic Interaction Logging](#36-automatic-interaction-logging) for full details on:
- Where the files are written (`systems/docgpt/logs/` by default)
- CSV and JSONL format descriptions
- How to change the output directory (`INTERACTION_LOG_DIR`)
- How to test the logging
- How to feed logs into the evaluation framework for scoring

### 5.4 Evaluation Framework Logging

The evaluation framework (`rag_evaluation/`) does not configure logging by itself. To enable logging in your evaluation scripts, add standard Python logging configuration:

```python
import logging

# Basic configuration — logs to console
logging.basicConfig(
    level=logging.DEBUG,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s"
)

# Now use the evaluator as normal
from rag_evaluation import RAGEvaluator
evaluator = RAGEvaluator()
results = evaluator.evaluate(query=query, context=context, answer=answer)
```

**For file-based logging:**

```python
import logging

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
    handlers=[
        logging.StreamHandler(),                          # Console
        logging.FileHandler("evaluation.log"),             # File
    ]
)
```

**For the ragas evaluator,** additional debug output can be enabled:

```python
import logging

# Enable ragas library debug logs
logging.getLogger("ragas").setLevel(logging.DEBUG)

# Enable httpx/openai request logs (shows API calls)
logging.getLogger("httpx").setLevel(logging.DEBUG)
logging.getLogger("openai").setLevel(logging.DEBUG)
```

### 5.5 Qualitative Logging Output

The `QualitativeLogger` produces structured log files (distinct from Python's `logging` module). These are evaluation artifacts, not debug logs.

**Where files are written:**

```python
logger.save(output_dir="logs")
# Creates:
#   logs/qualitative_log_2026-02-11_143022.csv
#   logs/qualitative_log_2026-02-11_143022.json
```

**CSV file** — Open in Excel or Google Sheets for human review. Columns include all `LogEntry` fields plus any evaluation score columns (flattened).

**JSON file** — Load programmatically for downstream analysis:

```python
import json

with open("logs/qualitative_log_2026-02-11_143022.json") as f:
    entries = json.load(f)

for entry in entries:
    print(f"Q: {entry['question']}")
    print(f"  RAG: {entry['rag_answer'][:80]}...")
    print(f"  LLM: {entry['llm_answer'][:80]}...")
    if entry.get('evaluation_scores'):
        print(f"  Scores: {entry['evaluation_scores']}")
```

**From the CLI:**

```bash
# Generate qualitative logs with verbose console output
python examples/qualitative_eval.py data.csv --output-dir my_logs --verbose

# The --verbose flag prints each entry to the console as it's processed
# The output files are always written to --output-dir regardless of --verbose
```

### 5.6 Debugging with LangChain Verbose Mode

DocGPT enables LangChain debug and verbose modes by default in `main.py`:

```python
from langchain_core.globals import set_debug, set_verbose
set_debug(True)
set_verbose(True)
```

This produces **very detailed** output showing:
- Every LLM prompt sent to Gemini
- Raw LLM responses
- Retrieval queries and results
- Chain execution steps

**To reduce noise in production,** disable these before starting:

```python
set_debug(False)
set_verbose(False)
```

Or set `LOG_LEVEL=WARNING` to suppress most output while keeping LangChain debug available in the code.

---

## Quick Reference Cheat Sheet

```bash
# ── Evaluation Framework ─────────────────────────────────────────

# Install
pip install -r requirements.txt && pip install -e ".[dev]"

# Run all tests
pytest tests/ -v --cov=rag_evaluation --cov-report=term-missing

# Run evaluator from CLI
python examples/evaluate.py data.csv --verbose
python examples/evaluate.py data.json --output results.json --metrics faithfulness relevance

# Run qualitative logger from CLI
python examples/qualitative_eval.py data.csv --with-scores --verbose --output-dir logs/

# Lint and format
ruff check . --fix && ruff format .

# Type check
mypy rag_evaluation/ --ignore-missing-imports


# ── DocGPT RAG System ────────────────────────────────────────────

cd systems/docgpt

# Setup
cp .env.example .env            # Then edit .env with your keys
uv sync                         # Install dependencies
docker compose up -d            # Start PostgreSQL + MongoDB

# Ingest data (one-time)
uv run python main.py --ingest

# Run Discord bot (interaction logs go to logs/ automatically)
uv run python main.py

# Run API server (interaction logs go to logs/ automatically)
uv run python main.py --api

# Custom log directory
$env:INTERACTION_LOG_DIR = "my_logs"  # PowerShell
uv run python main.py --api

# View interaction logs
# Open logs/interactions_*.csv in Excel
# Or parse logs/interactions_*.jsonl with Python

# Run DocGPT tests
uv run pytest tests/ -v --tb=short

# Tear down
docker compose down
```
