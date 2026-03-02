"""
Tests for individual evaluation metrics.
"""

from rag_evaluation.metrics.faithfulness import FaithfulnessMetric
from rag_evaluation.metrics.context_precision import ContextPrecisionMetric
from rag_evaluation.metrics.relevance import RelevanceMetric


class TestFaithfulnessMetric:
    """Tests for the faithfulness metric."""

    def setup_method(self):
        self.metric = FaithfulnessMetric()

    def test_perfect_faithfulness(self):
        context = "The sky is blue. Water is wet."
        answer = "The sky is blue."
        result = self.metric.compute(answer, context)
        assert result["score"] >= 0.5

    def test_empty_answer(self):
        result = self.metric.compute("", "Some context")
        assert result["score"] == 1.0
        assert result["details"]["total_sentences"] == 0

    def test_result_has_details(self):
        result = self.metric.compute("The sky is blue.", "The sky is blue.")
        assert "details" in result
        assert "total_sentences" in result["details"]
        assert "supported_sentences" in result["details"]

    def test_score_in_range(self):
        result = self.metric.compute(
            "Machine learning is great for predictions.",
            "Machine learning uses data to make predictions.",
        )
        assert 0.0 <= result["score"] <= 1.0


class TestContextPrecisionMetric:
    """Tests for the context precision metric."""

    def setup_method(self):
        self.metric = ContextPrecisionMetric()

    def test_compute_returns_score(self):
        result = self.metric.compute(
            answer="ML is a subset of AI.",
            context="ML is part of artificial intelligence.",
            ground_truth="Machine learning is a subset of AI.",
        )
        assert "score" in result
        assert isinstance(result["score"], float)

    def test_score_in_range(self):
        result = self.metric.compute(
            answer="ML is AI.",
            context="ML is part of AI.",
            ground_truth="ML is AI.",
        )
        assert 0.0 <= result["score"] <= 1.0


class TestRelevanceMetric:
    """Tests for the relevance metric."""

    def setup_method(self):
        self.metric = RelevanceMetric()

    def test_compute_returns_score(self):
        result = self.metric.compute(
            query="What is ML?",
            answer="ML is a subset of AI.",
            context="ML is part of artificial intelligence.",
        )
        assert "score" in result
        assert isinstance(result["score"], float)

    def test_score_in_range(self):
        result = self.metric.compute(
            query="What is ML?",
            answer="ML is AI.",
            context="ML is part of AI.",
        )
        assert 0.0 <= result["score"] <= 1.0
