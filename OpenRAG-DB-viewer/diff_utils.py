"""Diff and metrics utilities for comparing RAG vs LLM answers."""

from __future__ import annotations

import difflib
import html
import re


def tokenize(text: str) -> list[str]:
    """Whitespace-tokenize after lowercasing and stripping punctuation."""
    return re.findall(r"\w+", (text or "").lower())


def jaccard_similarity(text_a: str | None, text_b: str | None) -> float:
    """Token-level Jaccard similarity between two texts."""
    set_a = set(tokenize(text_a or ""))
    set_b = set(tokenize(text_b or ""))
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    return len(set_a & set_b) / len(set_a | set_b)


def answer_length(text: str | None) -> int:
    return len(text) if text else 0


def token_count(text: str | None) -> int:
    return len(tokenize(text or ""))


def side_by_side_html(text_a: str | None, text_b: str | None) -> str:
    """Return an HTML table showing a side-by-side diff of two texts.

    Additions are highlighted green, deletions red.
    """
    a_lines = (text_a or "").splitlines(keepends=True)
    b_lines = (text_b or "").splitlines(keepends=True)
    differ = difflib.HtmlDiff(wrapcolumn=80)
    table = differ.make_table(
        a_lines,
        b_lines,
        fromdesc="RAG Answer",
        todesc="LLM Answer",
        context=False,
    )
    return table


def unified_diff_text(text_a: str | None, text_b: str | None) -> str:
    """Return a unified diff string."""
    a_lines = (text_a or "").splitlines(keepends=True)
    b_lines = (text_b or "").splitlines(keepends=True)
    diff = difflib.unified_diff(a_lines, b_lines, fromfile="rag_answer", tofile="llm_answer")
    return "".join(diff)


def inline_diff_html(text_a: str | None, text_b: str | None) -> tuple[str, str]:
    """Return (html_a, html_b) with word-level diff highlights.

    Deleted words in text_a are wrapped in red spans.
    Added words in text_b are wrapped in green spans.
    """
    words_a = (text_a or "").split()
    words_b = (text_b or "").split()
    sm = difflib.SequenceMatcher(None, words_a, words_b)

    result_a: list[str] = []
    result_b: list[str] = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            result_a.extend(html.escape(w) for w in words_a[i1:i2])
            result_b.extend(html.escape(w) for w in words_b[j1:j2])
        elif tag == "replace":
            result_a.extend(
                f'<span style="background:#ffcccc;padding:1px 3px;border-radius:3px">{html.escape(w)}</span>'
                for w in words_a[i1:i2]
            )
            result_b.extend(
                f'<span style="background:#ccffcc;padding:1px 3px;border-radius:3px">{html.escape(w)}</span>'
                for w in words_b[j1:j2]
            )
        elif tag == "delete":
            result_a.extend(
                f'<span style="background:#ffcccc;padding:1px 3px;border-radius:3px">{html.escape(w)}</span>'
                for w in words_a[i1:i2]
            )
        elif tag == "insert":
            result_b.extend(
                f'<span style="background:#ccffcc;padding:1px 3px;border-radius:3px">{html.escape(w)}</span>'
                for w in words_b[j1:j2]
            )

    return " ".join(result_a), " ".join(result_b)
