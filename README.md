# RAG Evaluation Framework

A comprehensive framework for evaluating Retrieval-Augmented Generation (RAG) models using multiple evaluation approaches: rule-based metrics and advanced LLM-based metrics via the ragas library.

## Features

- **Multiple Evaluation Backends**:
  - **Basic Evaluator**: Rule-based metrics (no external dependencies)
    - **Faithfulness**: Checks if the answer is grounded in the provided context rather than hallucinated
    - **Context Precision**: Measures how much of the answer comes from the ground truth context
    - **Relevance**: Checks if the generated response is relevant to the query and context
  
  - **Ragas Evaluator**: Advanced LLM-based metrics (requires ragas library and OpenAI API key)
    - **Faithfulness**: Measures factual consistency of the answer with the context
    - **Answer Relevancy**: Measures how relevant the answer is to the query
    - **Context Precision**: Measures how relevant the retrieved context is
    - **Context Recall**: Measures if all relevant information is retrieved

- **Qualitative Answer Logging**:
  - Side-by-side comparison of RAG-augmented answers vs direct LLM answers
  - Logs question category, model name, retrieved context, and both answers
  - Outputs to CSV (for Excel/Sheets review) and JSON (for programmatic analysis)
  - Optional evaluation scores attached to each log entry

- **Data Ingestion Support**:
  - Jabref (BibTeX) format
  - DataTable formats (CSV, JSON, Excel)

- **Easy-to-Use API**:
  - Single evaluation
  - Batch evaluation
  - Custom metric selection
  - Qualitative logging with structured output

## Installation

```bash
# Clone the repository
git clone https://github.com/RESHAPELab/RAG-evaluation.git
cd RAG-evaluation

# Install dependencies (for ragas support)
pip install -r requirements.txt

# Optional dependencies for enhanced features:
# pip install openpyxl  # For Excel support
# pip install bibtexparser  # For advanced BibTeX parsing
```

## Quick Start

### Basic Evaluator (Rule-based, No API Key Required)

```python
from rag_evaluation import RAGEvaluator

# Initialize evaluator
evaluator = RAGEvaluator()

# Evaluate a single output
results = evaluator.evaluate(
    query="What is machine learning?",
    context="Machine learning is a subset of AI that enables systems to learn...",
    answer="Machine learning allows computers to learn from data...",
    ground_truth="Machine learning is a subset of AI..."
)

print(results)
```

### Ragas Evaluator (LLM-based, Requires OpenAI API Key)

The ragas evaluator provides more sophisticated LLM-based evaluation metrics. Set your OpenAI API key first:

```bash
export OPENAI_API_KEY='your-api-key-here'
```

```python
from rag_evaluation import RagasEvaluator

# Initialize ragas evaluator
evaluator = RagasEvaluator()

# Evaluate a single output
results = evaluator.evaluate(
    query="What is machine learning?",
    context="Machine learning is a subset of AI that enables systems to learn...",
    answer="Machine learning allows computers to learn from data...",
    ground_truth="Machine learning is a subset of AI..."
)

print(results)
```

### Batch Evaluation

```python
from rag_evaluation import RAGEvaluator

evaluator = RAGEvaluator()

# Evaluate multiple outputs
results = evaluator.evaluate_batch(
    queries=["What is ML?", "What is DL?"],
    contexts=["ML is...", "DL is..."],
    answers=["ML allows...", "DL uses..."],
    ground_truths=["ML is...", "DL is..."]
)

# Get average scores
avg_scores = evaluator.get_average_scores(results)
print(avg_scores)
```

### Loading Data from Files

```python
from rag_evaluation import RAGEvaluator
from rag_evaluation.data_ingestion import DataTableLoader, JabrefLoader

# Load from CSV
loader = DataTableLoader()
data = loader.load_for_evaluation('data.csv')

# Evaluate
evaluator = RAGEvaluator()
results = evaluator.evaluate_batch(**data)

# Load from Jabref/BibTeX
jabref_loader = JabrefLoader()
data = jabref_loader.load_for_evaluation('references.bib')
results = evaluator.evaluate_batch(**data)
```

### Qualitative Answer Logging

Log RAG answers alongside direct LLM answers for side-by-side qualitative analysis. This helps you compare what the model answers **with** retrieved context versus **without** it.

#### From Python

```python
from rag_evaluation import QualitativeLogger, LogEntry

logger = QualitativeLogger()

logger.log(LogEntry(
    category="factual",
    model_name="gemini-1.5-flash",
    question="What is data.table?",
    rag_context="data.table is an R package that provides an enhanced version of data.frame...",
    rag_answer="data.table is an R package that extends data.frame with fast aggregation...",
    llm_answer="data.table is a popular R package used for data manipulation...",
))

# Save to both CSV and JSON
written = logger.save(output_dir="logs")
print(written)
# {'csv': 'logs/qualitative_log_2026-02-11_143022.csv',
#  'json': 'logs/qualitative_log_2026-02-11_143022.json'}
```

#### Attaching Evaluation Scores

You can compute evaluation metrics and attach them to each log entry:

```python
from rag_evaluation import RAGEvaluator, QualitativeLogger, LogEntry

evaluator = RAGEvaluator()
scores = evaluator.evaluate(
    query="What is data.table?",
    context="data.table is an R package...",
    answer="data.table is an R package that extends...",
)

logger = QualitativeLogger()
logger.log(LogEntry(
    category="factual",
    model_name="gemini-1.5-flash",
    question="What is data.table?",
    rag_context="data.table is an R package...",
    rag_answer="data.table is an R package that extends...",
    llm_answer="data.table is a popular R package...",
    evaluation_scores=scores,
))
logger.save("logs")
```

#### From the Command Line

The `examples/qualitative_eval.py` script provides a full CLI:

```bash
# Basic: load data and log to CSV + JSON
python examples/qualitative_eval.py your_data.csv

# With evaluation scores and verbose per-entry output
python examples/qualitative_eval.py your_data.csv --output-dir results/logs --with-scores --verbose

# Override the model name for all entries
python examples/qualitative_eval.py your_data.csv --model-name gemini-2.0-flash

# Choose specific metrics when scoring
python examples/qualitative_eval.py your_data.csv --with-scores --metrics faithfulness relevance
```

**CLI arguments:**

| Argument | Description |
|---|---|
| `data_file` | Path to input data file (CSV, JSON, or Excel) |
| `--type` | Input format: `csv`, `json`, `excel`, or `auto` (default: `auto`) |
| `--output-dir` | Directory for log files (default: `logs/`) |
| `--model-name` | Override the model name for all entries |
| `--with-scores` | Compute evaluation metrics and attach to each entry |
| `--metrics` | Which metrics to compute: `faithfulness`, `context_precision`, `relevance` |
| `--verbose`, `-v` | Print detailed per-entry output to the console |

## Evaluation Metrics

### Basic Evaluator Metrics (Rule-based)

#### Faithfulness

Evaluates whether the generated answer is grounded in the provided context and not hallucinated. 

- **Score Range**: 0.0 to 1.0
- **1.0**: All statements are supported by context
- **0.0**: No statements are supported by context
- **Approach**: Keyword-based analysis

#### Context Precision

Measures how much of the information in the answer comes from the ground truth context.

- **Score Range**: 0.0 to 1.0
- **1.0**: Answer is fully based on ground truth
- **0.0**: Answer has no overlap with ground truth
- **Approach**: Term overlap analysis

#### Relevance

Checks if the generated response is relevant to both the query and the provided context.

- **Score Range**: 0.0 to 1.0
- **1.0**: Highly relevant answer
- **0.0**: Completely irrelevant answer
- **Approach**: Weighted term matching

### Ragas Evaluator Metrics (LLM-based)

The ragas evaluator uses advanced LLM-based evaluation for more nuanced assessments:

#### Faithfulness
- Uses LLM to verify factual consistency between answer and context
- More accurate detection of hallucinations

#### Answer Relevancy
- Evaluates how well the answer addresses the user's query
- Considers semantic similarity, not just keyword matching

#### Context Precision
- Measures how relevant the retrieved context is to the query
- Helps evaluate retrieval quality

#### Context Recall
- Checks if all relevant information needed to answer the query is in the retrieved context
- Identifies gaps in retrieval

## Data Format

### Evaluation Data (CSV)

```csv
query,context,answer,ground_truth
"What is ML?","ML is...","ML allows...","ML is..."
```

### Evaluation Data (JSON)

```json
[
  {
    "query": "What is ML?",
    "context": "ML is...",
    "answer": "ML allows...",
    "ground_truth": "ML is..."
  }
]
```

### Qualitative Logging Data (CSV)

For the qualitative logger, provide a file with these columns:

```csv
category,model_name,question,rag_context,rag_answer,llm_answer
factual,gemini-1.5-flash,"What is data.table?","data.table is...","data.table is a package...","data.table is a library..."
code,gemini-1.5-flash,"How to read CSV?","Use fread()...","Use fread() to read...","Use read.csv() to read..."
```

| Column | Description |
|---|---|
| `category` | Question category for grouping (e.g. `factual`, `reasoning`, `code`) |
| `model_name` | LLM model used (e.g. `gemini-1.5-flash`) |
| `question` | The original user question |
| `rag_context` | The retrieved context that was passed to the LLM |
| `rag_answer` | The answer generated by the LLM **with** RAG context |
| `llm_answer` | The answer from the LLM **without** RAG (direct response) |

A sample file is provided at `examples/sample_qualitative_data.csv`.

### Qualitative Logging Data (JSON)

```json
[
  {
    "category": "factual",
    "model_name": "gemini-1.5-flash",
    "question": "What is data.table?",
    "rag_context": "data.table is...",
    "rag_answer": "data.table is a package...",
    "llm_answer": "data.table is a library..."
  }
]
```

### BibTeX Format (Jabref)

```bibtex
@article{key,
  title={Title},
  abstract={Context text...},
  note={Additional context...}
}
```

## Examples

Check the `examples/` directory for complete usage examples:

- `examples/basic_usage.py`: Comprehensive examples of basic evaluator
- `examples/ragas_usage.py`: Examples using ragas evaluator with LLM-based metrics
- `examples/evaluate.py`: Command-line evaluation tool
- `examples/qualitative_eval.py`: Command-line qualitative logging tool (RAG vs LLM comparison)
- `examples/sample_data.json`: Sample JSON evaluation data
- `examples/sample_data.csv`: Sample CSV evaluation data
- `examples/sample_data.bib`: Sample BibTeX data
- `examples/sample_qualitative_data.csv`: Sample CSV for qualitative logging

Run the examples:

```bash
cd examples
python basic_usage.py

# Qualitative logging (no API key required for basic logging)
python qualitative_eval.py sample_qualitative_data.csv --verbose

# Qualitative logging with evaluation scores
python qualitative_eval.py sample_qualitative_data.csv --with-scores --verbose

# For ragas examples (requires OpenAI API key)
export OPENAI_API_KEY='your-key-here'
python ragas_usage.py
```

## Project Structure

```
rag_evaluation/
├── __init__.py              # Main package exports
├── evaluator.py             # RAGEvaluator class (basic, rule-based)
├── ragas_evaluator.py       # RagasEvaluator class (LLM-based)
├── qualitative_logger.py    # QualitativeLogger + LogEntry for answer logging
├── metrics/
│   ├── __init__.py
│   ├── faithfulness.py      # Faithfulness metric
│   ├── context_precision.py # Context precision metric
│   └── relevance.py         # Relevance metric
└── data_ingestion/
    ├── __init__.py
    ├── jabref_loader.py     # Jabref/BibTeX loader
    └── datatable_loader.py  # CSV/JSON/Excel loader
```

## Custom Metrics

You can select specific metrics to use:

```python
# Basic evaluator with specific metrics
evaluator = RAGEvaluator(metrics=['faithfulness', 'relevance'])
results = evaluator.evaluate(query, context, answer)

# Ragas evaluator with specific metrics
ragas_evaluator = RagasEvaluator(metrics=['faithfulness', 'answer_relevancy'])
results = ragas_evaluator.evaluate(query, context, answer)
```

## API Reference

### RAGEvaluator (Basic, Rule-based)

Main class for evaluating RAG models using rule-based metrics.

**Methods**:
- `evaluate(query, context, answer, ground_truth=None)`: Evaluate a single output
- `evaluate_batch(queries, contexts, answers, ground_truths=None)`: Evaluate multiple outputs
- `get_average_scores(batch_results)`: Calculate average scores from batch results

### RagasEvaluator (LLM-based)

Evaluator using the ragas library for LLM-based evaluation metrics.

**Requirements**: OpenAI API key (set OPENAI_API_KEY environment variable)

**Methods**:
- `evaluate(query, context, answer, ground_truth=None)`: Evaluate a single output
- `evaluate_batch(queries, contexts, answers, ground_truths=None)`: Evaluate multiple outputs
- `get_average_scores(batch_results)`: Calculate average scores from batch results

### QualitativeLogger

Accumulates log entries and writes them to CSV and/or JSON for qualitative analysis.

**Methods**:
- `log(entry)`: Append a single `LogEntry`
- `log_batch(entries)`: Append multiple `LogEntry` objects at once
- `save(output_dir="logs", formats=["csv", "json"])`: Write logs to disk; returns dict of `{format: filepath}`

**Properties**:
- `entries`: List of accumulated `LogEntry` objects
- `len(logger)`: Number of entries logged so far

### LogEntry

Pydantic model representing a single qualitative log record.

**Fields**:
- `timestamp` (str): Auto-generated ISO timestamp
- `category` (str): Question category (e.g. `"factual"`, `"reasoning"`, `"code"`)
- `model_name` (str): LLM model name (e.g. `"gemini-1.5-flash"`)
- `question` (str): The original user question
- `rag_context` (str): Retrieved context passed to the LLM
- `rag_answer` (str): LLM answer generated with RAG context
- `llm_answer` (str): LLM answer generated without RAG
- `evaluation_scores` (dict, optional): Metric scores from `RAGEvaluator`

### DataTableLoader

Loader for tabular data formats.

**Methods**:
- `load(file_path, format=None)`: Load data from file
- `load_for_evaluation(file_path, ...)`: Load data ready for evaluation
- `load_for_qualitative_logging(file_path, ...)`: Load data ready for qualitative logging (columns: `category`, `model_name`, `question`, `rag_context`, `rag_answer`, `llm_answer`)

**Supported Formats**: CSV, JSON, Excel (.xlsx, .xls)

### JabrefLoader

Loader for Jabref/BibTeX format.

**Methods**:
- `load(file_path)`: Load data from BibTeX file
- `load_for_evaluation(file_path)`: Load data ready for evaluation

**Supported Formats**: BibTeX (.bib), JSON

## Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

## License

This project is open source and available under the MIT License.

## Citation

If you use this framework in your research, please cite:

```bibtex
@software{rag_evaluation,
  title={RAG Evaluation Framework},
  author={RESHAPELab},
  year={2026},
  url={https://github.com/RESHAPELab/RAG-evaluation}
}
```

## Contact

For questions or issues, please open an issue on GitHub.