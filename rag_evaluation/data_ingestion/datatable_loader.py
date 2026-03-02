"""
DataTable Loader

Loads evaluation data from various tabular formats (CSV, Excel, JSON).
"""

import json
import csv
from typing import Dict, List, Any, Optional
from pathlib import Path


class DataTableLoader:
    """
    Loader for tabular data formats.
    
    This loader can parse CSV, Excel, and JSON files containing
    evaluation data with columns for queries, contexts, answers,
    and ground truth.
    """
    
    def load(self, file_path: str, format: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Load data from a tabular file.
        
        Args:
            file_path: Path to the data file
            format: Optional format specifier ('csv', 'json', 'excel').
                   If None, inferred from file extension.
            
        Returns:
            List of dictionaries containing the data
        """
        path = Path(file_path)
        
        if not path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")
        
        # Infer format from extension if not provided
        if format is None:
            format = self._infer_format(path)
        
        if format == 'csv':
            return self._load_csv(file_path)
        elif format == 'json':
            return self._load_json(file_path)
        elif format in ['excel', 'xlsx', 'xls']:
            return self._load_excel(file_path)
        else:
            raise ValueError(f"Unsupported format: {format}")
    
    def _infer_format(self, path: Path) -> str:
        """
        Infer file format from extension.
        
        Args:
            path: File path
            
        Returns:
            Format string
        """
        ext = path.suffix.lower()
        
        if ext == '.csv':
            return 'csv'
        elif ext == '.json':
            return 'json'
        elif ext in ['.xlsx', '.xls']:
            return 'excel'
        else:
            raise ValueError(f"Cannot infer format from extension: {ext}")
    
    def _load_csv(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load data from CSV file.
        
        Args:
            file_path: Path to CSV file
            
        Returns:
            List of dictionaries
        """
        entries = []
        
        with open(file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                entries.append(dict(row))
        
        return entries
    
    def _load_json(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load data from JSON file.
        
        Args:
            file_path: Path to JSON file
            
        Returns:
            List of dictionaries
        """
        with open(file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Handle both single entry and list of entries
        if isinstance(data, dict):
            return [data]
        return data
    
    def _load_excel(self, file_path: str) -> List[Dict[str, Any]]:
        """
        Load data from Excel file.
        
        Requires openpyxl or xlrd library.
        
        Args:
            file_path: Path to Excel file
            
        Returns:
            List of dictionaries
        """
        try:
            import openpyxl
            
            workbook = openpyxl.load_workbook(file_path)
            sheet = workbook.active
            
            # Get headers from first row
            headers = [cell.value for cell in sheet[1]]
            
            # Read data rows
            entries = []
            for row in sheet.iter_rows(min_row=2, values_only=True):
                entry = {headers[i]: row[i] for i in range(len(headers)) if i < len(row)}
                entries.append(entry)
            
            return entries
            
        except ImportError:
            raise ImportError(
                "openpyxl library required for Excel support. "
                "Install with: pip install openpyxl"
            )
    
    def load_for_evaluation(
        self,
        file_path: str,
        query_column: str = "query",
        context_column: str = "context",
        answer_column: str = "answer",
        ground_truth_column: str = "ground_truth",
        *,
        category_column: str = "category",
        model_name_column: str = "model_name",
        llm_answer_column: str = "llm_answer",
        format: Optional[str] = None,
    ) -> Dict[str, List[str]]:
        """
        Load data in a format ready for batch evaluation.

        Args:
            file_path: Path to the data file
            query_column: Name of the query column
            context_column: Name of the context column
            answer_column: Name of the answer column
            ground_truth_column: Name of the ground truth column
            category_column: Optional name of the question category column
            model_name_column: Optional name of the model name column
            llm_answer_column: Optional name of the non-RAG LLM answer column
            format: Optional format specifier

        Returns:
            Dictionary with lists of queries, contexts, answers, ground_truths,
            categories, model_names, and llm_answers (the last three may be
            empty strings if the corresponding columns are not present).
        """
        entries = self.load(file_path, format)

        return {
            "queries": [e.get(query_column, "") for e in entries],
            "contexts": [e.get(context_column, "") for e in entries],
            "answers": [e.get(answer_column, "") for e in entries],
            "ground_truths": [e.get(ground_truth_column, "") for e in entries],
            "categories": [e.get(category_column, "") for e in entries],
            "model_names": [e.get(model_name_column, "") for e in entries],
            "llm_answers": [e.get(llm_answer_column, "") for e in entries],
        }

    def load_for_qualitative_logging(
        self,
        file_path: str,
        category_column: str = 'category',
        model_name_column: str = 'model_name',
        query_column: str = 'question',
        rag_context_column: str = 'rag_context',
        rag_answer_column: str = 'rag_answer',
        llm_answer_column: str = 'llm_answer',
        format: Optional[str] = None
    ) -> Dict[str, List[str]]:
        """
        Load data in a format ready for qualitative logging.

        Expects a tabular file with columns for the question category,
        model name, the question itself, the RAG-retrieved context,
        the RAG-augmented answer, and the direct LLM answer.

        Args:
            file_path: Path to the data file
            category_column: Name of the category column
            model_name_column: Name of the model name column
            query_column: Name of the question/query column
            rag_context_column: Name of the RAG context column
            rag_answer_column: Name of the RAG answer column
            llm_answer_column: Name of the direct LLM answer column
            format: Optional format specifier

        Returns:
            Dictionary with lists of categories, model_names, questions,
            rag_contexts, rag_answers, and llm_answers
        """
        entries = self.load(file_path, format)

        return {
            'categories': [e.get(category_column, '') for e in entries],
            'model_names': [e.get(model_name_column, '') for e in entries],
            'questions': [e.get(query_column, '') for e in entries],
            'rag_contexts': [e.get(rag_context_column, '') for e in entries],
            'rag_answers': [e.get(rag_answer_column, '') for e in entries],
            'llm_answers': [e.get(llm_answer_column, '') for e in entries],
        }
