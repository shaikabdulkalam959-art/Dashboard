import streamlit as st
import pandas as pd

from utils.data_loader import load_data, APIError
from utils.data_cleaning import normalize_columns, clean_data, detect_duplicates
from utils.analytics import filter_data, calculate_kpis, calculate_yoy, calculate_quality_metrics, calculate_research_momentum
from utils.insights import generate_insights

from components import filters as filters_ui
from components import kpis as kpis_ui
from components import charts
from components import school as school_ui
from components import researcher as researcher_ui
from components.reveal import render_reveal_feature

st.set_page_config(
    page_title="SAI Research Intelligence",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

with open("assets/styles.css") as f:
    st.markdown(f"<style>{f.read()}</style>", unsafe_allow_html=True)


# ---------------------------------------------------------------- DATA LOAD
def get_clean_data():
    raw_df = load_data()             # may raise APIError
    df = normalize_columns(raw_df)
    df = clean_data(df)
    df = detect_duplicates(df)
    return df


try:
    with st.spinner("Connecting to the SaiU publications API..."):
        base_df = get_clean_data()
except APIError as e:
    st.markdown('<div class="hero-title">SAI RESEARCH INTELLIGENCE</div>', unsafe_allow_html=True)
    st.error(f"**Could not load live publication data.** {e.message}")
    st.caption(f"Failure type: `{e.kind}`")
    if st.button("Retry connection"):
        st.cache_data.clear()
        st.rerun()
    st.stop()

if base_df is None or len(base_df) == 0:
    st.error("The API returned no publication records.")
    st.stop()


# ------------------------------------------------------------------ HEADER
st.markdown(
    """
    <div class="hero">
        <div class="hero-eyebrow">SAI UNIVERSITY · CHENNAI</div>
        <div class="hero-title">SAI <span class="accent">RESEARCH</span> INTELLIGENCE</div>
        <div class="hero-tagline">Mapping the University's Research Ecosystem</div>
    </div>
    """,
    unsafe_allow_html=True,
)

filters_ui.render_global_search()
active_filters = filters_ui.render_sidebar_filters(base_df)
search_q = st.session_state.get("search_query", "")

df = filter_data(base_df, active_filters, search_q)
st.markdown(f"<div class='filter-count'>Showing <b>{len(df):,}</b> of {len(base_df):,} total publications</div>",
            unsafe_allow_html=True)

if len(df) == 0:
    st.warning("No publications match the current research filters.")

    def _clear_all():
        # on_click callback: runs before this run's widgets are re-created,
        # so it's safe to reset their session_state keys here.
        for k, v in filters_ui.DEFAULTS.items():
            st.session_state[k] = v

    st.button("Clear all filters", on_click=_clear_all)
    st.stop()


# -------------------------------------------------------------- NAVIGATION
SECTIONS = [
    "01 — Overview", "02 — Research Growth", "03 — Schools", "04 — Researchers",
    "05 — Research Quality", "06 — SDG Impact", "07 — Publication Explorer", "08 — Data Quality",
]
section = st.radio("nav", SECTIONS, horizontal=True, label_visibility="collapsed")
st.markdown("---")

kpis = calculate_kpis(df)
momentum = calculate_research_momentum(df)


# ------------------------------------------------------------------ 01
if section == SECTIONS[0]:
    school_counts = df["school"].value_counts()
    top_schools = [
        (name, int(cnt), round(100 * cnt / school_counts.max(), 1))
        for name, cnt in school_counts.head(6).items()
    ]
    sdg_counts = {}
    for xs in df["sdg_list"]:
        for s in xs:
            sdg_counts[s] = sdg_counts.get(s, 0) + 1
    top_sdgs = [s for s, _ in sorted(sdg_counts.items(), key=lambda x: x[1], reverse=True)[:6]]

    render_reveal_feature(kpis, momentum, top_schools, top_sdgs)
    st.markdown("<div style='height:18px'></div>", unsafe_allow_html=True)

    st.markdown("#### Research Intelligence Summary")
    for s in generate_insights(df):
        st.markdown(f"<div class='insight-line'>▸ {s}</div>", unsafe_allow_html=True)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    kpis_ui.render_kpi_grid(kpis, momentum)
    kpis_ui.render_momentum_explainer(momentum)


# ------------------------------------------------------------------ 02
elif section == SECTIONS[1]:
    st.markdown("#### Research Growth & Year-over-Year Analysis")
    yoy = calculate_yoy(df)
    if not yoy["available"]:
        st.info("No valid publication years in the current filter selection.")
    else:
        c1, c2, c3 = st.columns(3)
        def _fmt(pct):
            return f"{pct:+.1f}%" if pct is not None else "N/A (no prior-year data)"
        c1.metric(f"Publications ({yoy['current_year']})", yoy["current_total"],
                   _fmt(yoy["publication_growth_pct"]))
        c2.metric("Indexed publication growth", "", _fmt(yoy["indexed_growth_pct"]))
        c3.metric("Q1 publication growth", "", _fmt(yoy["q1_growth_pct"]))
        if not yoy["previous_year_available"]:
            st.caption(f"No {yoy['previous_year']} records exist in the filtered data — "
                       f"growth percentages are not calculated to avoid misleading figures.")
        charts.render_trend_chart(yoy["trend_years"], yoy["trend_counts"])


# ------------------------------------------------------------------ 03
elif section == SECTIONS[2]:
    school_ui.render_school_ecosystem(df)


# ------------------------------------------------------------------ 04
elif section == SECTIONS[3]:
    researcher_ui.render_researcher_explorer(df)


# ------------------------------------------------------------------ 05
elif section == SECTIONS[4]:
    st.markdown("#### Research Quality Profile")
    quality = calculate_quality_metrics(df)
    charts.render_quality_charts(quality)
    known_q = sum(quality["quartile_counts"][q] for q in ["Q1", "Q2", "Q3", "Q4"])
    known_idx = quality["indexing_counts"]["Indexed"] + quality["indexing_counts"]["Non-indexed"]
    st.markdown(
        f"<div class='insight-line'>▸ Quartile denominator: {quality['total']} total filtered "
        f"publications ({known_q} with a known SJR quartile).</div>"
        f"<div class='insight-line'>▸ Indexing denominator: {known_idx} publications with a known "
        f"indexing status — {quality['indexing_counts']['Unknown']} have unknown status and are "
        f"never treated as non-indexed.</div>",
        unsafe_allow_html=True,
    )


# ------------------------------------------------------------------ 06
elif section == SECTIONS[5]:
    st.markdown("#### SDG Impact Matrix")
    st.caption("Rows: schools · Columns: SDGs actually present in the filtered data · "
               "Cells: publication–SDG associations")
    charts.render_sdg_heatmap(df)


# ------------------------------------------------------------------ 07
elif section == SECTIONS[6]:
    st.markdown("#### Publication Explorer")
    sort_by = st.selectbox("Sort by", ["Year", "Title", "School", "Quartile"])
    sort_map = {"Year": "year", "Title": "title", "School": "school", "Quartile": "quartile"}
    exp_df = df.sort_values(sort_map[sort_by], ascending=(sort_by != "Year"))

    show_cols = {
        "title": "Title", "authors_raw": "Authors", "year": "Year", "school": "School",
        "doc_type": "Document Type", "publisher": "Publisher/Source",
        "indexing_status": "Indexing", "quartile": "SJR Quartile",
        "sdg_raw": "SDGs", "doi": "DOI", "doi_link": "DOI Link", "article_link": "Publication URL",
    }
    display = exp_df[list(show_cols.keys())].rename(columns=show_cols)
    st.dataframe(
        display,
        column_config={
            "DOI Link": st.column_config.LinkColumn("DOI Link"),
            "Publication URL": st.column_config.LinkColumn("Publication URL"),
        },
        use_container_width=True, hide_index=True, height=520,
    )


# ------------------------------------------------------------------ 08
elif section == SECTIONS[7]:
    st.markdown("#### Data Quality & Coverage")
    total = len(base_df)
    missing = {
        "Missing year": int(base_df["year"].isna().sum()),
        "Missing school": int((base_df["school"] == "Unknown School").sum()),
        "Missing author": int((base_df["author_count"] == 0).sum()),
        "Missing quartile": int((~base_df["quartile_known"]).sum()),
        "Missing SDG": int((base_df["sdg_count"] == 0).sum()),
        "Missing DOI": int((base_df["doi_clean"] == "").sum()),
    }
    c = st.columns(3)
    c[0].metric("Total API records", total)
    c[1].metric("Duplicate records detected", int(base_df["is_duplicate"].sum()))
    c[2].metric("Unique dedupe keys", base_df["dedupe_key"].nunique())
    cols = st.columns(3)
    for i, (label, val) in enumerate(missing.items()):
        cols[i % 3].metric(label, f"{val} ({round(100*val/total,1)}%)")

    if base_df["is_duplicate"].any():
        with st.expander("View flagged duplicate records (not removed)"):
            dup_view = base_df[base_df["is_duplicate"]][["title", "year", "school", "doi", "dedupe_key"]]
            st.dataframe(dup_view, use_container_width=True, hide_index=True)

    with st.expander("Source-field mapping (API field → dashboard field)"):
        mapping_rows = [
            ("Authors", "raw_authors — full author byline as published"),
            ("SaiU Authors", "authors_raw / authors_list — university-affiliated authors, parsed"),
            ("School", "school"), ("Title", "title"), ("Year", "year (parsed to int)"),
            ("SJR Quartile", "quartile — Q1–Q4 or blank (Unclassified)"),
            ("Indexing Status", "indexing_status / indexing_list — pipe-delimited, e.g. 'Scopus | WoS'"),
            ("SaiU SDG Indexing", "sdg_raw / sdg_list — pipe-delimited SDG numbers (1–17)"),
            ("DOI / DOI Link", "doi / doi_link — clickable only when present"),
            ("Article Link", "article_link — publication URL, clickable only when present"),
            ("Document Type", "doc_type"), ("Publisher", "publisher"),
        ]
        st.dataframe(pd.DataFrame(mapping_rows, columns=["API field", "Dashboard field"]),
                     use_container_width=True, hide_index=True)


# -------------------------------------------------------------- SIDEBAR EXPORTS
with st.sidebar:
    st.markdown("---")
    st.markdown("### Export")
    st.download_button(
        "Download filtered publications (CSV)",
        df.drop(columns=["search_blob"]).to_csv(index=False).encode("utf-8"),
        file_name="sai_filtered_publications.csv", mime="text/csv",
        use_container_width=True,
    )
    summary_df = pd.DataFrame([{**kpis, "research_momentum": momentum["score"]}])
    st.download_button(
        "Download summary statistics (CSV)",
        summary_df.to_csv(index=False).encode("utf-8"),
        file_name="sai_summary_statistics.csv", mime="text/csv",
        use_container_width=True,
    )
