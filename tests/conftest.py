"""
Shared fixtures for RAG evaluation tests.
"""

import pytest

from rag_evaluation import RAGEvaluator


@pytest.fixture
def evaluator():
    """Create a default RAGEvaluator instance with all metrics."""
    return RAGEvaluator()


@pytest.fixture
def evaluator_faithfulness_only():
    """Create a RAGEvaluator with only faithfulness metric."""
    return RAGEvaluator(metrics=["faithfulness"])


@pytest.fixture
def sample_data():
    """Sample evaluation data for testing."""
    return {
        "query": "What is machine learning?",
        "context": (
            "Machine learning is a subset of artificial intelligence that "
            "enables systems to learn and improve from experience without "
            "being explicitly programmed. It focuses on developing computer "
            "programs that can access data and use it to learn for themselves."
        ),
        "answer": (
            "Machine learning is a subset of artificial intelligence. "
            "It allows systems to learn from experience without explicit programming."
        ),
        "ground_truth": (
            "Machine learning is a subset of artificial intelligence that "
            "enables systems to learn and improve from experience without "
            "being explicitly programmed."
        ),
    }


@pytest.fixture
def batch_data():
    """Batch sample data for testing evaluate_batch."""
    return {
        "queries": [
            "What is machine learning?",
            "What is deep learning?",
        ],
        "contexts": [
            "Machine learning is a subset of AI that learns from data.",
            "Deep learning uses neural networks with many layers to learn from large amounts of data.",
        ],
        "answers": [
            "Machine learning is a subset of AI.",
            "Deep learning is a type of machine learning using neural networks.",
        ],
        "ground_truths": [
            "Machine learning is a subset of AI that learns from data.",
            "Deep learning uses multi-layered neural networks.",
        ],
    }
