"""
Tests for the RAGEvaluator class.
"""

from rag_evaluation import RAGEvaluator


class TestRAGEvaluatorInit:
    """Tests for RAGEvaluator initialization."""

    def test_default_init_has_all_metrics(self, evaluator):
        assert "faithfulness" in evaluator.metrics
        assert "context_precision" in evaluator.metrics
        assert "relevance" in evaluator.metrics

    def test_custom_metrics(self):
        evaluator = RAGEvaluator(metrics=["faithfulness"])
        assert "faithfulness" in evaluator.metrics
        assert "context_precision" not in evaluator.metrics
        assert "relevance" not in evaluator.metrics

    def test_empty_metrics_list(self):
        evaluator = RAGEvaluator(metrics=[])
        assert len(evaluator.metrics) == 0

    def test_invalid_metric_ignored(self):
        evaluator = RAGEvaluator(metrics=["nonexistent"])
        assert len(evaluator.metrics) == 0


class TestRAGEvaluatorEvaluate:
    """Tests for single evaluation."""

    def test_evaluate_returns_all_metrics(self, evaluator, sample_data):
        results = evaluator.evaluate(**sample_data)
        assert "faithfulness" in results
        assert "context_precision" in results
        assert "relevance" in results

    def test_evaluate_faithfulness_has_score(self, evaluator, sample_data):
        results = evaluator.evaluate(**sample_data)
        assert "score" in results["faithfulness"]
        assert isinstance(results["faithfulness"]["score"], float)
        assert 0.0 <= results["faithfulness"]["score"] <= 1.0

    def test_evaluate_without_ground_truth(self, evaluator, sample_data):
        del sample_data["ground_truth"]
        results = evaluator.evaluate(**sample_data)
        assert results["context_precision"]["score"] is None
        assert "error" in results["context_precision"]

    def test_evaluate_with_ground_truth(self, evaluator, sample_data):
        results = evaluator.evaluate(**sample_data)
        assert results["context_precision"]["score"] is not None

    def test_evaluate_relevance_has_score(self, evaluator, sample_data):
        results = evaluator.evaluate(**sample_data)
        assert "score" in results["relevance"]
        assert isinstance(results["relevance"]["score"], float)

    def test_evaluate_empty_answer(self, evaluator, sample_data):
        sample_data["answer"] = ""
        results = evaluator.evaluate(**sample_data)
        # Should handle gracefully without errors
        assert "faithfulness" in results

    def test_evaluate_single_metric(self, evaluator_faithfulness_only, sample_data):
        results = evaluator_faithfulness_only.evaluate(**sample_data)
        assert "faithfulness" in results
        assert "context_precision" not in results
        assert "relevance" not in results


class TestRAGEvaluatorBatch:
    """Tests for batch evaluation."""

    def test_batch_returns_list(self, evaluator, batch_data):
        results = evaluator.evaluate_batch(**batch_data)
        assert isinstance(results, list)
        assert len(results) == 2

    def test_batch_each_result_has_metrics(self, evaluator, batch_data):
        results = evaluator.evaluate_batch(**batch_data)
        for result in results:
            assert "faithfulness" in result
            assert "context_precision" in result
            assert "relevance" in result

    def test_batch_without_ground_truths(self, evaluator, batch_data):
        del batch_data["ground_truths"]
        results = evaluator.evaluate_batch(
            queries=batch_data["queries"],
            contexts=batch_data["contexts"],
            answers=batch_data["answers"],
        )
        assert len(results) == 2
        for result in results:
            assert result["context_precision"]["score"] is None


class TestRAGEvaluatorAverageScores:
    """Tests for average score computation."""

    def test_average_scores_returns_dict(self, evaluator, batch_data):
        results = evaluator.evaluate_batch(**batch_data)
        averages = evaluator.get_average_scores(results)
        assert isinstance(averages, dict)

    def test_average_scores_has_all_metrics(self, evaluator, batch_data):
        results = evaluator.evaluate_batch(**batch_data)
        averages = evaluator.get_average_scores(results)
        assert "faithfulness" in averages
        assert "context_precision" in averages
        assert "relevance" in averages

    def test_average_scores_in_range(self, evaluator, batch_data):
        results = evaluator.evaluate_batch(**batch_data)
        averages = evaluator.get_average_scores(results)
        for metric_name, score in averages.items():
            if score is not None:
                assert 0.0 <= score <= 1.0, f"{metric_name} score out of range: {score}"

    def test_average_scores_empty_results(self, evaluator):
        averages = evaluator.get_average_scores([])
        for score in averages.values():
            assert score is None
