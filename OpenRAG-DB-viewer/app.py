"""OpenRAG Responses DB Viewer -- Streamlit application.

Supports both SQLite and PostgreSQL.  Auto-discovers tables in the database
and lets you pick which one to browse.
"""

from __future__ import annotations

import math
import os
from datetime import datetime, timedelta

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

import db_utils
import diff_utils

# Columns that contain markdown content and should be rendered as such
MARKDOWN_COLUMNS = {"question", "rag_answer", "llm_answer", "rag_context"}

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

tab_table, tab_basic, tab_diff, tab_analytics, tab_sql = st.tabs(
    ["Table View", "Basic View", "Diff View", "Analytics", "SQL Console"]
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
                        if val is None:
                            st.caption("(NULL)")
                        elif col_name in MARKDOWN_COLUMNS:
                            st.markdown(str(val))
                        else:
                            st.code(str(val), language=None)

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

# ===========================  BASIC VIEW  ==================================
with tab_basic:
    st.subheader("Expanded Row View")
    st.caption(
        "Each row is displayed as an expandable card with markdown content rendered properly. "
        "Ideal for reviewing long responses."
    )

    basic_total = db_utils.fetch_count(db, filters)
    basic_total_pages = max(1, math.ceil(basic_total / page_size))

    col_bpg1, col_bpg2, col_bpg3 = st.columns([1, 2, 1])
    with col_bpg2:
        basic_page = st.number_input(
            "Page",
            min_value=1,
            max_value=basic_total_pages,
            value=1,
            step=1,
            key="basic_page",
        )

    basic_filters = db_utils.Filters(
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
        page=basic_page,
        page_size=page_size,
        dropdown_filters=filters.dropdown_filters,
    )

    st.caption(f"**{basic_total}** rows match  ·  page {basic_page}/{basic_total_pages}")

    basic_df = db_utils.fetch_rows(db, basic_filters)

    if basic_df.empty:
        st.info("No rows match your filters.")
    else:
        pk_col = "id" if "id" in basic_df.columns else basic_df.columns[0]

        for idx, row in basic_df.iterrows():
            row_id = row.get(pk_col, idx)
            ts_val = row.get(db.timestamp_col, "")
            question_preview = str(row.get("question", ""))[:80] if "question" in row else ""
            if len(str(row.get("question", ""))) > 80:
                question_preview += "..."

            expander_title = f"**#{row_id}** | {ts_val}"
            if question_preview:
                expander_title += f" | {question_preview}"

            with st.expander(expander_title, expanded=False):
                if "question" in row:
                    st.markdown("##### Question")
                    st.markdown(str(row.get("question", "")))
                    st.markdown("---")

                col_left, col_right = st.columns(2)

                with col_left:
                    if "rag_answer" in row:
                        st.markdown("##### RAG Answer")
                        rag_text = str(row.get("rag_answer") or "")
                        if rag_text:
                            st.markdown(rag_text)
                            st.caption(
                                f"{diff_utils.answer_length(rag_text)} chars / "
                                f"{diff_utils.token_count(rag_text)} tokens"
                            )
                        else:
                            st.caption("(No RAG answer)")

                with col_right:
                    if "llm_answer" in row:
                        st.markdown("##### LLM Answer")
                        llm_text = str(row.get("llm_answer") or "")
                        if llm_text:
                            st.markdown(llm_text)
                            st.caption(
                                f"{diff_utils.answer_length(llm_text)} chars / "
                                f"{diff_utils.token_count(llm_text)} tokens"
                            )
                        else:
                            st.caption("(No LLM answer)")

                if "rag_answer" in row and "llm_answer" in row:
                    rag_t = str(row.get("rag_answer") or "")
                    llm_t = str(row.get("llm_answer") or "")
                    if rag_t and llm_t:
                        st.markdown("---")
                        st.metric(
                            "Jaccard Similarity",
                            f"{diff_utils.jaccard_similarity(rag_t, llm_t):.2%}"
                        )

                if "rag_context" in row and row.get("rag_context"):
                    with st.expander("View RAG Context", expanded=False):
                        st.markdown(str(row.get("rag_context", "")))

                other_cols = [
                    c for c in basic_df.columns
                    if c not in (pk_col, db.timestamp_col, "question", "rag_answer",
                                 "llm_answer", "rag_context")
                ]
                if other_cols:
                    with st.expander("Other Fields", expanded=False):
                        for col in other_cols:
                            val = row.get(col)
                            if val is not None and str(val).strip():
                                st.markdown(f"**{col}:** {val}")

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

# ===========================  ANALYTICS  ===================================
with tab_analytics:
    st.subheader("Data Analytics")
    st.caption("Visualizations and statistics for the current table data.")

    analytics_filters = db_utils.Filters(
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
        page_size=10000,
        dropdown_filters=filters.dropdown_filters,
    )

    analytics_df = db_utils.fetch_rows(db, analytics_filters)

    if analytics_df.empty:
        st.info("No data available for analytics. Adjust your filters.")
    else:
        st.caption(f"Analyzing **{len(analytics_df)}** rows (max 10,000 for performance)")

        has_rag_col = "rag_answer" in analytics_df.columns
        has_llm_col = "llm_answer" in analytics_df.columns
        has_ts_col = db.timestamp_col in analytics_df.columns

        if has_rag_col:
            analytics_df["rag_answer_len"] = analytics_df["rag_answer"].apply(
                lambda x: len(str(x)) if pd.notna(x) else 0
            )
        if has_llm_col:
            analytics_df["llm_answer_len"] = analytics_df["llm_answer"].apply(
                lambda x: len(str(x)) if pd.notna(x) else 0
            )

        if has_rag_col and has_llm_col:
            analytics_df["jaccard"] = analytics_df.apply(
                lambda r: diff_utils.jaccard_similarity(
                    str(r.get("rag_answer") or ""),
                    str(r.get("llm_answer") or "")
                ),
                axis=1
            )

        st.markdown("### Overview")
        overview_cols = st.columns(4)
        with overview_cols[0]:
            st.metric("Total Rows", len(analytics_df))
        with overview_cols[1]:
            if has_rag_col:
                non_empty_rag = analytics_df[analytics_df["rag_answer_len"] > 0]
                st.metric("With RAG Answer", len(non_empty_rag))
            else:
                st.metric("With RAG Answer", "N/A")
        with overview_cols[2]:
            if has_llm_col:
                non_empty_llm = analytics_df[analytics_df["llm_answer_len"] > 0]
                st.metric("With LLM Answer", len(non_empty_llm))
            else:
                st.metric("With LLM Answer", "N/A")
        with overview_cols[3]:
            if has_rag_col and has_llm_col:
                avg_jaccard = analytics_df["jaccard"].mean()
                st.metric("Avg Jaccard", f"{avg_jaccard:.2%}")
            else:
                st.metric("Avg Jaccard", "N/A")

        st.markdown("---")

        if has_rag_col or has_llm_col:
            st.markdown("### Answer Length Distribution")
            len_chart_cols = st.columns(2)

            with len_chart_cols[0]:
                if has_rag_col:
                    fig_rag_len = px.histogram(
                        analytics_df[analytics_df["rag_answer_len"] > 0],
                        x="rag_answer_len",
                        nbins=30,
                        title="RAG Answer Length (chars)",
                        labels={"rag_answer_len": "Characters"},
                        color_discrete_sequence=["#636EFA"]
                    )
                    fig_rag_len.update_layout(showlegend=False, height=300)
                    st.plotly_chart(fig_rag_len, use_container_width=True)
                else:
                    st.info("No rag_answer column")

            with len_chart_cols[1]:
                if has_llm_col:
                    fig_llm_len = px.histogram(
                        analytics_df[analytics_df["llm_answer_len"] > 0],
                        x="llm_answer_len",
                        nbins=30,
                        title="LLM Answer Length (chars)",
                        labels={"llm_answer_len": "Characters"},
                        color_discrete_sequence=["#EF553B"]
                    )
                    fig_llm_len.update_layout(showlegend=False, height=300)
                    st.plotly_chart(fig_llm_len, use_container_width=True)
                else:
                    st.info("No llm_answer column")

        if has_rag_col and has_llm_col:
            st.markdown("### RAG vs LLM Comparison")
            comparison_cols = st.columns(2)

            with comparison_cols[0]:
                fig_scatter = px.scatter(
                    analytics_df[
                        (analytics_df["rag_answer_len"] > 0) &
                        (analytics_df["llm_answer_len"] > 0)
                    ],
                    x="rag_answer_len",
                    y="llm_answer_len",
                    title="Answer Length: RAG vs LLM",
                    labels={
                        "rag_answer_len": "RAG Length (chars)",
                        "llm_answer_len": "LLM Length (chars)"
                    },
                    opacity=0.6
                )
                fig_scatter.add_trace(
                    go.Scatter(
                        x=[0, analytics_df["rag_answer_len"].max()],
                        y=[0, analytics_df["rag_answer_len"].max()],
                        mode="lines",
                        name="Equal Length",
                        line={"dash": "dash", "color": "gray"}
                    )
                )
                fig_scatter.update_layout(height=350)
                st.plotly_chart(fig_scatter, use_container_width=True)

            with comparison_cols[1]:
                fig_jaccard = px.histogram(
                    analytics_df,
                    x="jaccard",
                    nbins=20,
                    title="Jaccard Similarity Distribution",
                    labels={"jaccard": "Jaccard Similarity"},
                    color_discrete_sequence=["#00CC96"]
                )
                fig_jaccard.update_layout(
                    showlegend=False,
                    height=350,
                    xaxis={"tickformat": ".0%"}
                )
                st.plotly_chart(fig_jaccard, use_container_width=True)

        if has_ts_col:
            st.markdown("### Interactions Over Time")
            try:
                analytics_df["ts_parsed"] = pd.to_datetime(
                    analytics_df[db.timestamp_col], errors="coerce"
                )
                ts_valid = analytics_df[analytics_df["ts_parsed"].notna()].copy()

                if not ts_valid.empty:
                    ts_valid["date"] = ts_valid["ts_parsed"].dt.date
                    daily_counts = ts_valid.groupby("date").size().reset_index(name="count")

                    fig_time = px.line(
                        daily_counts,
                        x="date",
                        y="count",
                        title="Daily Interaction Count",
                        labels={"date": "Date", "count": "Interactions"},
                        markers=True
                    )
                    fig_time.update_layout(height=300)
                    st.plotly_chart(fig_time, use_container_width=True)
                else:
                    st.info("Could not parse timestamp column for time series.")
            except Exception:
                st.info("Could not parse timestamp column for time series.")

        categorical_cols = [
            c for c in ["rag_name", "category", "model_name", "source"]
            if c in analytics_df.columns
        ]

        if categorical_cols:
            st.markdown("### Category Breakdowns")
            cat_cols_display = st.columns(min(len(categorical_cols), 3))

            for i, cat_col in enumerate(categorical_cols[:3]):
                with cat_cols_display[i]:
                    value_counts = analytics_df[cat_col].value_counts().head(10)
                    if not value_counts.empty:
                        fig_bar = px.bar(
                            x=value_counts.index.astype(str),
                            y=value_counts.values,
                            title=f"Top {cat_col} Values",
                            labels={"x": cat_col, "y": "Count"}
                        )
                        fig_bar.update_layout(
                            showlegend=False,
                            height=300,
                            xaxis_tickangle=-45
                        )
                        st.plotly_chart(fig_bar, use_container_width=True)

        st.markdown("### Summary Statistics")
        if has_rag_col or has_llm_col:
            stats_data = []
            if has_rag_col:
                rag_lens = analytics_df[analytics_df["rag_answer_len"] > 0]["rag_answer_len"]
                if not rag_lens.empty:
                    stats_data.append({
                        "Metric": "RAG Answer Length",
                        "Mean": f"{rag_lens.mean():.0f}",
                        "Median": f"{rag_lens.median():.0f}",
                        "Min": f"{rag_lens.min():.0f}",
                        "Max": f"{rag_lens.max():.0f}",
                        "Std Dev": f"{rag_lens.std():.0f}"
                    })
            if has_llm_col:
                llm_lens = analytics_df[analytics_df["llm_answer_len"] > 0]["llm_answer_len"]
                if not llm_lens.empty:
                    stats_data.append({
                        "Metric": "LLM Answer Length",
                        "Mean": f"{llm_lens.mean():.0f}",
                        "Median": f"{llm_lens.median():.0f}",
                        "Min": f"{llm_lens.min():.0f}",
                        "Max": f"{llm_lens.max():.0f}",
                        "Std Dev": f"{llm_lens.std():.0f}"
                    })
            if has_rag_col and has_llm_col:
                jaccard_vals = analytics_df["jaccard"]
                stats_data.append({
                    "Metric": "Jaccard Similarity",
                    "Mean": f"{jaccard_vals.mean():.2%}",
                    "Median": f"{jaccard_vals.median():.2%}",
                    "Min": f"{jaccard_vals.min():.2%}",
                    "Max": f"{jaccard_vals.max():.2%}",
                    "Std Dev": f"{jaccard_vals.std():.2%}"
                })

            if stats_data:
                stats_df = pd.DataFrame(stats_data)
                st.dataframe(stats_df, use_container_width=True, hide_index=True)
        else:
            st.info("No answer columns available for statistics.")

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
