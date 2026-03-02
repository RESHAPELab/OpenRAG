#!/usr/bin/env python3
"""
Qualitative RAG Evaluation Runner

Loads a data file containing questions, RAG answers, and direct LLM answers,
then logs them in both CSV and JSON for side-by-side qualitative analysis.

Optionally computes evaluation metric scores and attaches them to each log entry.

Usage:
    python qualitative_eval.py data.csv
    python qualitative_eval.py data.csv --output-dir results/logs --with-scores --verbose
    python qualitative_eval.py data.json --model-name gemini-1.5-flash
"""

import argparse
import sys
from pathlib import Path

# Add parent directory to path to import rag_evaluation
sys.path.insert(0, str(Path(__file__).parent.parent))

from rag_evaluation import RAGEvaluator, QualitativeLogger, LogEntry
from rag_evaluation.data_ingestion import DataTableLoader


def load_qualitative_data(file_path: str, data_type: str = "auto") -> dict:
    """
    Load data from file using DataTableLoader.

    Args:
        file_path: Path to the data file
        data_type: Format hint ('csv', 'json', 'excel', or 'auto')

    Returns:
        Dictionary with lists of categories, model_names, questions,
        rag_contexts, rag_answers, and llm_answers
    """
    path = Path(file_path)
    if not path.exists():
        raise FileNotFoundError(f"Data file not found: {file_path}")

    fmt = None if data_type == "auto" else data_type
    loader = DataTableLoader()
    return loader.load_for_qualitative_logging(file_path, format=fmt)


def build_log_entries(
    data: dict,
    model_name_override: str | None = None,
    evaluator: RAGEvaluator | None = None,
) -> list[LogEntry]:
    """
    Convert loaded data rows into LogEntry objects.

    If an evaluator is provided, each entry will include evaluation scores
    computed from (question, rag_context, rag_answer).

    Args:
        data: Output of load_qualitative_data()
        model_name_override: If set, overrides the model_name for every entry
        evaluator: Optional RAGEvaluator for attaching metric scores

    Returns:
        List of LogEntry objects ready for the logger
    """
    entries: list[LogEntry] = []
    n = len(data["questions"])

    for i in range(n):
        model = model_name_override or data["model_names"][i]
        question = data["questions"][i]
        rag_context = data["rag_contexts"][i]
        rag_answer = data["rag_answers"][i]

        scores = None
        if evaluator and rag_context and rag_answer:
            scores = evaluator.evaluate(
                query=question,
                context=rag_context,
                answer=rag_answer,
            )

        entries.append(
            LogEntry(
                category=data["categories"][i],
                model_name=model,
                question=question,
                rag_context=rag_context,
                rag_answer=rag_answer,
                llm_answer=data["llm_answers"][i],
                evaluation_scores=scores,
            )
        )

    return entries


def print_summary(entries: list[LogEntry], verbose: bool = False) -> None:
    """Print a human-readable summary of the logged entries."""
    print("\n" + "=" * 70)
    print("QUALITATIVE LOG SUMMARY")
    print("=" * 70)
    print(f"  Total entries: {len(entries)}")

    # Category breakdown
    categories = {}
    for e in entries:
        cat = e.category or "(uncategorized)"
        categories[cat] = categories.get(cat, 0) + 1
    if categories:
        print("  Categories:")
        for cat, count in sorted(categories.items()):
            print(f"    - {cat}: {count}")

    # Model breakdown
    models = {}
    for e in entries:
        m = e.model_name or "(unknown)"
        models[m] = models.get(m, 0) + 1
    if models:
        print("  Models:")
        for m, count in sorted(models.items()):
            print(f"    - {m}: {count}")

    if verbose:
        print("\n" + "-" * 70)
        for i, entry in enumerate(entries, 1):
            print(f"\n  [{i}] {entry.category or '-'} | {entry.model_name or '-'}")
            print(f"      Q:   {entry.question[:80]}{'...' if len(entry.question) > 80 else ''}")
            print(f"      RAG: {entry.rag_answer[:80]}{'...' if len(entry.rag_answer) > 80 else ''}")
            print(f"      LLM: {entry.llm_answer[:80]}{'...' if len(entry.llm_answer) > 80 else ''}")
            if entry.evaluation_scores:
                scores_str = ", ".join(
                    f"{k}: {v.get('score', v) if isinstance(v, dict) else v:.3f}"
                    for k, v in entry.evaluation_scores.items()
                    if (isinstance(v, dict) and v.get("score") is not None) or isinstance(v, (int, float))
                )
                if scores_str:
                    print(f"      Scores: {scores_str}")

    print("\n" + "=" * 70)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Log RAG vs direct LLM answers for qualitative analysis."
    )

    parser.add_argument(
        "data_file",
        help="Path to the input data file (CSV, JSON, or Excel)",
    )
    parser.add_argument(
        "--type",
        choices=["csv", "json", "excel", "auto"],
        default="auto",
        help="Input file format (default: auto-detect from extension)",
    )
    parser.add_argument(
        "--output-dir",
        default="logs",
        help="Directory to write log files into (default: logs/)",
    )
    parser.add_argument(
        "--model-name",
        default=None,
        help="Override model name for all entries (uses data column value if omitted)",
    )
    parser.add_argument(
        "--with-scores",
        action="store_true",
        help="Compute evaluation metric scores and attach to each log entry",
    )
    parser.add_argument(
        "--metrics",
        nargs="+",
        choices=["faithfulness", "context_precision", "relevance"],
        default=None,
        help="Metrics to compute when --with-scores is used (default: all)",
    )
    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Print detailed per-entry output",
    )

    args = parser.parse_args()

    try:
        # Load data
        print(f"Loading data from: {args.data_file}")
        data = load_qualitative_data(args.data_file, args.type)
        n = len(data["questions"])
        print(f"Loaded {n} entries")

        # Optionally set up evaluator
        evaluator = None
        if args.with_scores:
            evaluator = RAGEvaluator(metrics=args.metrics)
            print(f"Scoring with metrics: {list(evaluator.metrics.keys())}")

        # Build log entries
        entries = build_log_entries(data, args.model_name, evaluator)

        # Log and save
        logger = QualitativeLogger()
        logger.log_batch(entries)

        written = logger.save(output_dir=args.output_dir)
        for fmt, path in written.items():
            print(f"  {fmt.upper()} saved to: {path}")

        # Print summary
        print_summary(entries, verbose=args.verbose)

        return 0

    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
