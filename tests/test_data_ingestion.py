"""
Tests for data ingestion loaders.
"""

import os
import tempfile

import pytest

from rag_evaluation.data_ingestion import DataTableLoader


@pytest.fixture
def loader():
    return DataTableLoader()


@pytest.fixture
def csv_file(tmp_path):
    """Create a temp CSV file that works cross-platform."""
    filepath = tmp_path / "test_data.csv"
    filepath.write_text("query,context,answer\nWhat is AI?,AI is intelligence.,AI is smart.\n", encoding="utf-8")
    return str(filepath)


@pytest.fixture
def json_file(tmp_path):
    """Create a temp JSON array file."""
    filepath = tmp_path / "test_data.json"
    filepath.write_text(
        '[{"query": "What is AI?", "context": "AI is intelligence.", "answer": "AI is smart."}]',
        encoding="utf-8",
    )
    return str(filepath)


@pytest.fixture
def json_single_file(tmp_path):
    """Create a temp JSON single-object file."""
    filepath = tmp_path / "test_single.json"
    filepath.write_text(
        '{"query": "What is AI?", "context": "AI is intelligence.", "answer": "AI is smart."}',
        encoding="utf-8",
    )
    return str(filepath)


@pytest.fixture
def eval_csv_file(tmp_path):
    """Create a temp CSV with ground_truth column."""
    filepath = tmp_path / "test_eval.csv"
    filepath.write_text(
        "query,context,answer,ground_truth\nWhat is AI?,AI info.,AI is smart.,AI is intelligence.\n",
        encoding="utf-8",
    )
    return str(filepath)


class TestDataTableLoader:
    """Tests for DataTableLoader CSV/JSON loading."""

    def test_load_csv(self, loader, csv_file):
        data = loader.load(csv_file)
        assert data is not None
        assert len(data) == 1
        assert data[0]["query"] == "What is AI?"

    def test_load_json(self, loader, json_file):
        data = loader.load(json_file)
        assert data is not None
        assert len(data) == 1
        assert data[0]["query"] == "What is AI?"

    def test_load_json_single_object(self, loader, json_single_file):
        data = loader.load(json_single_file)
        assert len(data) == 1

    def test_load_for_evaluation(self, loader, eval_csv_file):
        data = loader.load_for_evaluation(eval_csv_file)
        assert "queries" in data
        assert "contexts" in data
        assert "answers" in data
        assert "ground_truths" in data
        assert len(data["queries"]) == 1

    def test_file_not_found(self, loader):
        with pytest.raises(FileNotFoundError):
            loader.load("/nonexistent/file.csv")

    def test_unsupported_format(self, loader, tmp_path):
        filepath = tmp_path / "test.xyz"
        filepath.write_text("data", encoding="utf-8")
        with pytest.raises(ValueError):
            loader.load(str(filepath))
