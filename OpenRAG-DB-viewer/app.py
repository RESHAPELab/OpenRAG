"""OpenRAG Responses DB Viewer -- Streamlit application.

Supports both SQLite and PostgreSQL.  Auto-discovers tables in the database
and lets you pick which one to browse.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import pandas as pd
import streamlit as st

import db_utils
import diff_utils

# ---------------------------------------------------------------------------
# Page config
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="OpenRAG DB Viewer",
    page_icon=":mag:",
    layout="wide",
)

# ---------------------------------------------------------------------------
# Sidebar -- DB connection
# ---------------------------------------------------------------------------

st.sidebar.title("OpenRAG DB Viewer")

backend = st.sidebar.radio(
    "Database backend",
    ["PostgreSQL", "SQLite"],
    horizontal=True,
    help="PostgreSQL for live databases (e.g. discord_interaction_logs). "
         "SQLite for evaluation_logs .db files.",
)

# ---- Step 1: Discover tables ----
tables: list[str] = []
conn_error: str | None = None

if backend == "SQLite":
    db_path = st.sidebar.text_input(
        "SQLite DB path",
        value="evaluation_logs.db",
        help="Absolute or relative path to a SQLite file.",
    )
    try:
        tables = db_utils.list_sqlite_tables(db_path)
    except FileNotFoundError as exc:
        conn_error = str(exc)
    except Exception as exc:  # noqa: BLE001
        conn_error = f"Unexpected error: {exc}"
else:
    dsn = st.sidebar.text_input(
        "PostgreSQL DSN",
        value=os.environ.get("DB_VIEWER_DSN", "postgresql://root:example@localhost:5432/postgres"),
        help="Connection string for the PostgreSQL database. "
             "Set DB_VIEWER_DSN env var to override the default.",
    )
    try:
        tables = db_utils.list_pg_tables(dsn)
    except Exception as exc:  # noqa: BLE001
        conn_error = f"Connection failed: {exc}"

if conn_error:
    st.error(conn_error)
    st.stop()

if not tables:
    st.warning("No tables found in this database. The database appears to be empty.")
    st.info(
        "For the Discord interaction logs, the `discord_interaction_logs` table "
        "is created automatically the first time the Discord bot logs an interaction. "
        "Run the bot at least once, then refresh."
    )
    st.stop()

# ---- Step 2: Pick a table ----
# Put well-known tables first
priority = ["discord_interaction_logs", "evaluation_logs"]
ordered = [t for t in priority if t in tables] + [t for t in tables if t not in priority]
selected_table = st.sidebar.selectbox("Table", ordered)

# ---- Step 3: Connect to the selected table ----
db: db_utils.DBConn | None = None
try:
    if backend == "SQLite":
        db = db_utils.connect_sqlite(db_path, selected_table)
    else:
        db = db_utils.connect_postgresql(dsn, selected_table)
except Exception as exc:  # noqa: BLE001
    st.error(f"Failed to open table: {exc}")
    st.stop()

assert db is not None

st.sidebar.caption(f"Connected to **{db.table}** ({len(db.columns)} columns)")

# ---------------------------------------------------------------------------
# Sidebar -- Filters
# ---------------------------------------------------------------------------

st.sidebar.markdown("---")
st.sidebar.subheader("Filters")

dropdown_selections: dict[str, str | None] = {}
for col in db.filterable_dropdowns:
    values = db_utils.get_distinct_values(db, col)
    sel = st.sidebar.selectbox(col, ["All"] + values, index=0, key=f"dd_{col}")
    dropdown_selections[col] = sel if sel != "All" else None

ts_col_name = db.timestamp_col
st.sidebar.markdown(f"**{ts_col_name} range**")
ts_preset = st.sidebar.selectbox(
    "Quick preset", ["None", "Last 24 hours", "Last 7 days", "Last 30 days"]
)
ts_from_val = ""
ts_to_val = ""
if ts_preset == "Last 24 hours":
    ts_from_val = (datetime.utcnow() - timedelta(hours=24)).strftime("%Y-%m-%d %H:%M:%S")
elif ts_preset == "Last 7 days":
    ts_from_val = (datetime.utcnow() - timedelta(days=7)).strftime("%Y-%m-%d %H:%M:%S")
elif ts_preset == "Last 30 days":
    ts_from_val = (datetime.utcnow() - timedelta(days=30)).strftime("%Y-%m-%d %H:%M:%S")

ts_from = st.sidebar.text_input("From (ISO)", value=ts_from_val)
ts_to = st.sidebar.text_input("To (ISO)", value=ts_to_val)

# Free-text search across text-like columns
text_cols_available = [c for c in db.columns if c not in ("id",)]
search_text = st.sidebar.text_input(
    "Search text",
    help=f"Searches across text columns in {db.table}",
)

# Advanced filters -- only show if rag_answer/llm_answer exist
has_answer_cols = "rag_answer" in db.columns or "llm_answer" in db.columns
with st.sidebar.expander("Advanced filters"):
    answer_filter = "No filter"
    min_rag_len = 0
    min_llm_len = 0
    if has_answer_cols:
        answer_filter = st.selectbox(
            "Answer presence",
            ["No filter", "Has RAG answer", "Has LLM answer", "Missing either"],
        )
        if "rag_answer" in db.columns:
            min_rag_len = st.number_input("Min RAG answer length", min_value=0, value=0, step=10)
        if "llm_answer" in db.columns:
            min_llm_len = st.number_input("Min LLM answer length", min_value=0, value=0, step=10)

    id_min = 0
    id_max = 0
    if "id" in db.columns:
        id_min = st.number_input("ID min", min_value=0, value=0, step=1)
        id_max = st.number_input("ID max", min_value=0, value=0, step=1)

# Sort & pagination
st.sidebar.markdown("---")
st.sidebar.subheader("Display")
sort_col = st.sidebar.selectbox("Sort by", db.sortable, index=0)
sort_dir = st.sidebar.radio("Sort direction", ["DESC", "ASC"], horizontal=True)
page_size = st.sidebar.selectbox("Rows per page", [25, 50, 100, 200], index=1)

# Column visibility
with st.sidebar.expander("Column visibility"):
    col_visibility: dict[str, bool] = {}
    important = {"id", ts_col_name, "question", "rag_context", "rag_answer", "llm_answer",
                 "rag_name", "category", "model_name"}
    for col in db.columns:
        col_visibility[col] = st.checkbox(col, value=(col in important), key=f"vis_{col}")

visible_cols = [c for c, shown in col_visibility.items() if shown]

# Build Filters
has_rag = None
has_llm = None
missing_either = False
if answer_filter == "Has RAG answer":
    has_rag = True
elif answer_filter == "Has LLM answer":
    has_llm = True
elif answer_filter == "Missing either":
    missing_either = True

filters = db_utils.Filters(
    ts_from=ts_from or None,
    ts_to=ts_to or None,
    search_text=search_text or None,
    search_columns=text_cols_available,
    has_rag=has_rag,
    has_llm=has_llm,
    missing_either=missing_either,
    min_rag_len=min_rag_len if min_rag_len > 0 else None,
    min_llm_len=min_llm_len if min_llm_len > 0 else None,
    id_min=id_min if id_min > 0 else None,
    id_max=id_max if id_max > 0 else None,
    sort_col=sort_col,
    sort_dir=sort_dir,
    page=1,
    page_size=page_size,
    dropdown_filters={k: v for k, v in dropdown_selections.items() if v is not None},
)

# ---------------------------------------------------------------------------
# Main area
# ---------------------------------------------------------------------------

tab_table, tab_diff, tab_sql = st.tabs(
    ["Table View", "Diff View", "SQL Console"]
)

# ===========================  TABLE VIEW  ==================================
with tab_table:
    total = db_utils.fetch_count(db, filters)
    total_pages = max(1, math.ceil(total / page_size))

    col_pg1, col_pg2, col_pg3 = st.columns([1, 2, 1])
    with col_pg2:
        page = st.number_input(
            "Page",
            min_value=1,
            max_value=total_pages,
            value=1,
            step=1,
            key="table_page",
        )
    filters.page = page

    st.caption(
        f"**{total}** rows match  ·  page {page}/{total_pages}  ·  "
        f"table: `{db.table}`"
    )

    df = db_utils.fetch_rows(db, filters)

    if df.empty:
        st.info("No rows match your filters.")
    else:
        avail_visible = [c for c in visible_cols if c in df.columns]
        display_df = df[avail_visible] if avail_visible else df

        # Export
        exp1, exp2, _ = st.columns([1, 1, 4])
        export_filters = db_utils.Filters(
            ts_from=filters.ts_from,
            ts_to=filters.ts_to,
            search_text=filters.search_text,
            search_columns=filters.search_columns,
            has_rag=filters.has_rag,
            has_llm=filters.has_llm,
            missing_either=filters.missing_either,
            min_rag_len=filters.min_rag_len,
            min_llm_len=filters.min_llm_len,
            id_min=filters.id_min,
            id_max=filters.id_max,
            sort_col=filters.sort_col,
            sort_dir=filters.sort_dir,
            page=1,
            page_size=999_999_999,
            dropdown_filters=filters.dropdown_filters,
        )
        with exp1:
            all_df = db_utils.fetch_rows(db, export_filters)
            st.download_button(
                "Export CSV",
                data=db_utils.to_csv_bytes(all_df),
                file_name=f"{db.table}_export.csv",
                mime="text/csv",
            )
        with exp2:
            st.download_button(
                "Export JSONL",
                data=db_utils.to_jsonl_bytes(all_df),
                file_name=f"{db.table}_export.jsonl",
                mime="application/jsonl",
            )

        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # ---- Detail panel ----
        st.markdown("---")
        st.subheader("Row detail")
        pk_col = "id" if "id" in df.columns else df.columns[0]
        row_ids = df[pk_col].tolist()
        if row_ids:
            selected_id = st.selectbox(
                f"Select {pk_col} to inspect", row_ids, key="detail_id"
            )
            row = db_utils.fetch_row_by_id(db, selected_id)
            if row:
                for col_name in db.columns:
                    val = row.get(col_name, "")
                    expand = col_name in ("rag_answer", "llm_answer", "question")
                    with st.expander(f"**{col_name}**", expanded=expand):
                        st.code(str(val) if val is not None else "(NULL)", language=None)

                # Metrics (only if rag/llm columns exist)
                if "rag_answer" in db.columns and "llm_answer" in db.columns:
                    st.markdown("**Quick metrics**")
                    m1, m2, m3 = st.columns(3)
                    rag_text = str(row.get("rag_answer") or "")
                    llm_text = str(row.get("llm_answer") or "")
                    m1.metric(
                        "RAG answer length",
                        f"{diff_utils.answer_length(rag_text)} chars / "
                        f"{diff_utils.token_count(rag_text)} tokens",
                    )
                    m2.metric(
                        "LLM answer length",
                        f"{diff_utils.answer_length(llm_text)} chars / "
                        f"{diff_utils.token_count(llm_text)} tokens",
                    )
                    m3.metric(
                        "Jaccard overlap",
                        f"{diff_utils.jaccard_similarity(rag_text, llm_text):.2%}",
                    )

                if "candidate_a_answer" in row and row.get("candidate_a_answer"):
                    st.markdown("**Candidate A vs B**")
                    ca, cb = st.columns(2)
                    with ca:
                        st.text_area(
                            "Candidate A",
                            value=str(row.get("candidate_a_answer") or ""),
                            height=150, disabled=True, key=f"cand_a_{selected_id}",
                        )
                    with cb:
                        st.text_area(
                            "Candidate B",
                            value=str(row.get("candidate_b_answer") or ""),
                            height=150, disabled=True, key=f"cand_b_{selected_id}",
                        )

                if "feedback_thumbs_up" in row and row.get("feedback_thumbs_up") is not None:
                    fb = row["feedback_thumbs_up"]
                    st.info(
                        f"Feedback: {'Thumbs up' if fb else 'Thumbs down'} "
                        f"(at {row.get('feedback_timestamp', 'N/A')})"
                    )

# ===========================  DIFF VIEW  ===================================
with tab_diff:
    if "rag_answer" not in db.columns or "llm_answer" not in db.columns:
        st.info(
            f"Diff View requires `rag_answer` and `llm_answer` columns. "
            f"Table `{db.table}` does not have them."
        )
    else:
        st.subheader("RAG vs LLM Answer Diff")

        diff_row_id = st.number_input("Enter row ID", min_value=1, step=1, key="diff_row_id")
        diff_row = db_utils.fetch_row_by_id(db, int(diff_row_id))

        if diff_row is None:
            st.warning(f"Row {diff_row_id} not found.")
        else:
            rag_text = str(diff_row.get("rag_answer") or "")
            llm_text = str(diff_row.get("llm_answer") or "")

            if "question" in diff_row:
                st.caption(f"**Question:** {diff_row.get('question', '')}")

            mc1, mc2, mc3 = st.columns(3)
            mc1.metric("RAG length", f"{diff_utils.answer_length(rag_text)} chars")
            mc2.metric("LLM length", f"{diff_utils.answer_length(llm_text)} chars")
            mc3.metric("Jaccard overlap", f"{diff_utils.jaccard_similarity(rag_text, llm_text):.2%}")

            diff_mode = st.radio(
                "Diff style",
                ["Side-by-side (highlighted)", "Inline word diff", "Unified diff"],
                horizontal=True,
            )

            if diff_mode == "Side-by-side (highlighted)":
                html_table = diff_utils.side_by_side_html(rag_text, llm_text)
                st.markdown(
                    f'<div style="overflow-x:auto;font-size:13px">{html_table}</div>',
                    unsafe_allow_html=True,
                )
            elif diff_mode == "Inline word diff":
                html_a, html_b = diff_utils.inline_diff_html(rag_text, llm_text)
                c1, c2 = st.columns(2)
                with c1:
                    st.markdown("**RAG Answer**")
                    st.markdown(
                        f'<div style="white-space:pre-wrap;font-family:monospace;font-size:13px;'
                        f'padding:8px;border:1px solid #444;border-radius:6px">{html_a}</div>',
                        unsafe_allow_html=True,
                    )
                with c2:
                    st.markdown("**LLM Answer**")
                    st.markdown(
                        f'<div style="white-space:pre-wrap;font-family:monospace;font-size:13px;'
                        f'padding:8px;border:1px solid #444;border-radius:6px">{html_b}</div>',
                        unsafe_allow_html=True,
                    )
            elif diff_mode == "Unified diff":
                diff_text = diff_utils.unified_diff_text(rag_text, llm_text)
                if diff_text:
                    st.code(diff_text, language="diff")
                else:
                    st.info("No differences found (texts are identical).")

# ===========================  SQL CONSOLE  =================================
with tab_sql:
    st.subheader("Read-only SQL Console")

    all_tables_str = ", ".join(f"`{t}`" for t in tables)
    st.caption(
        f"Only `SELECT` (and `WITH ... SELECT`) queries are allowed. "
        f"Available tables: {all_tables_str}"
    )

    default_sql = f"SELECT * FROM {db.table} LIMIT 20;"
    sql_input = st.text_area(
        "SQL query",
        value=default_sql,
        height=120,
        key="sql_console_input",
    )

    explain_label = (
        "Show EXPLAIN QUERY PLAN" if db.backend == "sqlite" else "Show EXPLAIN ANALYZE"
    )
    show_plan = st.checkbox(explain_label, key="sql_show_plan")

    if st.button("Run query", key="sql_run"):
        query_to_run = sql_input.strip()
        if show_plan:
            prefix = "EXPLAIN QUERY PLAN" if db.backend == "sqlite" else "EXPLAIN ANALYZE"
            query_to_run = f"{prefix} {query_to_run}"

        err = db_utils.validate_readonly(sql_input.strip())
        if err:
            st.error(f"Blocked: {err}")
        else:
            try:
                result_df = db_utils.run_readonly_sql(db, query_to_run)
                if result_df.empty:
                    st.info("Query returned no rows.")
                else:
                    st.dataframe(result_df, use_container_width=True, hide_index=True)
                    st.caption(f"{len(result_df)} row(s) returned.")
            except Exception as exc:  # noqa: BLE001
                st.error(f"Query error: {exc}")
