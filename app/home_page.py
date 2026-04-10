import os
import pickle

from utils.pipeline import *

import pandas as pd
import streamlit as st

if "dfAll" not in st.session_state:
    st.session_state.dfAll = None
if "show_performance" not in st.session_state:
    st.session_state.show_performance = False
if "search_mode" not in st.session_state:
    st.session_state.search_mode = None
if "skip_counter" not in st.session_state:
    st.session_state.skip_counter = 0

st.set_page_config(
    page_title="SciLottery",
    page_icon='🎲'
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background-color: #FFFFFF; 
}
[data-testid="stSidebar"] {
    background-color: #e0e0e0;
}

/* Font size and layout tweaks */
html, body, [class*="css"] {
    font-size: 18px;
}
.block-container {
    max-width: 85% !important;   /* ↓ reduce ancho → más espacio lateral */
    padding-left: 4rem;
    padding-right: 4rem;
}
h1 {font-size: 32px !important; margin-bottom: 0.2rem;}
h2 {font-size: 24px !important; margin-bottom: 0.2rem;}
h3 {font-size: 19px !important; margin-bottom: 0.2rem;}
.stButton>button {
    border-radius: 6px;
    font-weight: 600;
    padding: 0.25rem 0.8rem;
    font-size: 12px;
}
.stDataFrame {
    border-radius: 8px;
}
[data-testid="metric-container"] {
    padding: 8px 14px;
}
.caption {
    font-size: 18px !important;
    color: #666;
}

</style>
""", unsafe_allow_html=True)

st.logo("assets/bcu_logo.png", size="large")

st.markdown(
    "<h1 style='text-align:left; margin-bottom:0;'>SciLottery</h1>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:left; color:gray; margin-top:0;'>Prediction of researcher performance from OpenAlex bibliometric data under uncertainty.</p>",
    unsafe_allow_html=True
)
if "work_citation_cache" not in st.session_state:
    st.session_state.work_citation_cache = {}

minPapers = 0
minCitations = 0

# Input options and params
email = st.text_input("User e-mail:", help="OpenAlex user email")

year_range = st.slider("Year range:", min_value=2010, max_value=2026, value=(2021, 2025), help="Select the publication year range to analyze")

y0, y1 = year_range
options = ['Institute', 'Author']
searchBy = st.pills('Search by: ', options, selection_mode="single", default=None)
if searchBy != st.session_state.search_mode:
    st.session_state.search_mode = searchBy
    st.session_state.dfAll = None
    st.session_state.show_performance = False

if not email and searchBy:
    st.warning("Email must be entered to continue")
    st.stop()

inputIds = None
dfAll = {}
last_warning = None
if searchBy == options[0]:
    # Selected institutions
    inputIds = st.text_input("Institute ids:", help='If more than one, separate with commas.')
elif searchBy == options[1]:
    # Selected authors
    inputIds = st.text_input("Author ids:", help='If more than one, separate with commas.')

# Submit to retrieve info
if inputIds:
    minPapers = st.number_input("Minimum number of papers per author:", value=10, min_value=0)
    minCitations = st.number_input("Minimum number of citations per author:", value=100, min_value=0)
    if st.button("Perform search", type='primary'):
        st.session_state.skip_counter = 0
        st.session_state.show_performance = True
        with st.spinner("OpenAlex search..."):
            try:
                phase1_weight = 0.8
                phase2_weight = 0.2

                if searchBy == options[0]:
                    inst_ids = sanitizeIds(inputIds, st, prefix='i')

                    progress_bar = st.progress(0)
                    last_warning = None

                    aids_processed = 0
                    max_aids_seen = 1
                    insts_processed = 0
                    total_insts = len(inst_ids)

                    for idx, inst in enumerate(inst_ids):
                        aids = None
                        for attempt in range(3):
                            aids, msg = authors_working_at_institution_in_year(inst_id=inst, year=y1, mailto=email, min_total_works=minPapers, min_total_citations=minCitations)
                            filtered_aids = []
                            if not aids:
                                if attempt < 2:
                                    if last_warning is not None:
                                        last_warning.empty()
                                    last_warning = st.warning(f"{msg} Retrying...")
                                    time.sleep(1 * (2 ** attempt))
                                    continue
                                else:
                                    if last_warning is not None:
                                        last_warning.empty()
                                    st.warning(f"Skipping institution {inst} due to repeated errors.")
                                    break
                            for aid in aids:
                                try:
                                    works, msg = count_author_works_in_period_safe(aid, email, y0, y1)
                                    if works is None:
                                        st.warning(f"{msg}.")
                                    if works >= minPapers:
                                        filtered_aids.append(aid)
                                except Exception:
                                    continue

                            if filtered_aids:
                                aids = filtered_aids
                                print(f'Filtered aids: {aids}')
                                break
                        if not aids:
                            st.session_state.skip_counter += 1

                            if st.session_state.skip_counter > 3:
                                st.error("Too many failed institutions. Stopping execution.")
                                st.stop()

                            continue

                        aids_processed += len(aids)
                        max_aids_seen = max(max_aids_seen, aids_processed)

                        phase1_progress = phase1_weight * (aids_processed / max_aids_seen)
                        progress_bar.progress(min(phase1_progress, phase1_weight))
                        for attempt in range(3):
                            try:
                                df, _, st.session_state.work_citation_cache = build_author_df_and_unique_work_distributions(
                                    aids,
                                    y0=y0,
                                    y1=y1,
                                    mailto=email,
                                    sleep_s=0.05,
                                    work_citation_cache=st.session_state.work_citation_cache
                                )
                                if df is not None and not df.empty:
                                    break
                                if attempt < 2:
                                    if last_warning is not None:
                                        last_warning.empty()
                                    last_warning = st.warning(
                                        "Rate limit reached. Retrying request..."
                                    )
                                    time.sleep(1 * (2 ** attempt))
                            except Exception as e:
                                st.warning(str(e))
                        if df is None or df.empty:
                            last_warning = st.warning("Some author data could not be retrieved due to repeated request errors.")
                        else:
                            dfAll[inst] = df

                        retrieved = len(df)
                        expected = len(aids)
                        if retrieved < expected:
                            st.warning(
                                f"⚠️ Filtering applied: {retrieved}/{expected} authors retrieved, "
                                f"{len(df)} retained after applying minimum publication and citation thresholds."
                            )

                        insts_processed += 1
                        phase2_progress = phase2_weight * (insts_processed / total_insts)
                        progress_bar.progress(phase1_weight + phase2_progress)
                    if not dfAll:
                        st.warning("Some institutions could not be processed due to repeated request errors.")
                    progress_bar.progress(1.0)
                elif searchBy == options[1]:
                    last_warning = None
                    aids = sanitizeIds(inputIds, st, prefix='A')

                    filtered_aids = []
                    progress_bar = st.progress(0)
                    total_aids = len(aids)

                    skip_counter = 0
                    max_skips = 3

                    for idx, aid in enumerate(aids):
                        works, msg = count_author_works_in_period_safe(aid, email, y0, y1)
                        if works is None:
                            if last_warning is not None:
                                last_warning.empty()
                            last_warning = st.warning(f"{msg}.")
                            skip_counter += 1

                            if skip_counter >= max_skips:
                                if last_warning is not None:
                                    last_warning.empty()
                                st.warning(f"Skipping {aid} due to repeated errors.")
                                progress_bar.progress(1.0)
                        elif works >= minPapers:
                            filtered_aids.append(aid)
                        progress_bar.progress((idx + 1) / total_aids * phase1_weight)

                    if not filtered_aids:
                        if last_warning is not None:
                            last_warning.empty()
                        last_warning = st.warning(f"No authors have at least {minPapers} papers in the selected period.")
                    aids = filtered_aids

                    df = None
                    for attempt in range(3):
                        df, _, st.session_state.work_citation_cache = build_author_df_and_unique_work_distributions(
                            aids,
                            y0=y0,
                            y1=y1,
                            mailto=email,
                            sleep_s=0.05,
                            work_citation_cache=st.session_state.work_citation_cache
                        )
                        progress_bar.progress(
                            phase1_weight + (attempt + 1) / 5 * phase2_weight
                        )
                        if df is not None and not df.empty:
                            break
                        if attempt < 2:
                            if last_warning is not None:
                                last_warning.empty()
                            last_warning = st.warning(
                                "Rate limit reached. Retrying request..."
                            )
                            time.sleep(1 * (2 ** attempt))
                        else:
                            if last_warning is not None:
                                last_warning.empty()
                            last_warning = st.warning("Some author data could not be retrieved due to repeated request errors.")
                    if df is None or df.empty:
                        if last_warning is not None:
                            last_warning.empty()
                        st.warning("Some author data could not be retrieved due to repeated request errors.")
                    else:
                        dfAll["inputAIDs"] = df

                    retrieved = len(df) if df is not None else 0
                    expected = len(aids)

                    if retrieved < expected:
                        st.warning(
                            f"⚠️ Filtering applied: {retrieved}/{expected} authors retrieved, "
                            f"{len(df)} retained after applying minimum publication and citation thresholds."
                        )

                st.session_state.dfAll = dfAll
                progress_bar.progress(1.0)
            except Exception as e:
                st.error(f"Unexpected error during OpenAlex search: {e}")
                st.stop()

dfAll = st.session_state.dfAll
if dfAll and st.session_state.show_performance:
    # Add citations columns
    cols = ["count", "citationAvg", "maxCitation"]
    dfClean = {}
    parts = []

    for inst_id, df in dfAll.items():
        df = df[
            (df["count1"] >= minPapers) &
            (df["citations1"] >= minCitations)
            ].reset_index(drop=True)

        d = df.copy()
        d["citationAvg1"] = d["citations1"] / d["count1"]
        cols = ["count1", "citationAvg1", "maxCitation1"]

        for c in cols:
            d[f"{c}Perc"] = d[c].rank(pct=True)

        d["avgPerc1"] = (d["count1Perc"] + d["citationAvg1Perc"] + d["maxCitation1Perc"]) / 3

        dfAll[inst_id] = d

        out = d.loc[:, [
            "authorID",
            "avgPerc1",
            "count1Perc",
            "citationAvg1Perc",
            "maxCitation1Perc"
        ]]

        parts.append(out)
        dfClean[inst_id] = d

    df = pd.concat(parts, axis=0, ignore_index=True)
    df = (
        df
        .sort_values(by="avgPerc1", ascending=False)
        .reset_index(drop=True)
    )

    st.header('Performance')
    df["authorID"] = df["authorID"].apply(
        lambda x: f"https://openalex.org/{x}"
    )
    df = df.round(2)
    st.dataframe(
        df,
        column_config={
            "authorID": st.column_config.LinkColumn(
                "authorID",
                display_text=r"https://openalex\.org/(.*)"
            )
        }
    )
    st.caption(f"**Shape:** {df.shape}", )

    score_col = "avgPerc1"
    target_col = "avgPerc2"

    alpha = None
    lambda_val = None
    gamma = None

    st.header('Budget allocation')
    B = st.number_input("Total budget:", help="Total amount of money to distribute.", value=1000000.0)
    col1, col2, col3 = st.columns(3)
    with col1:
        alpha = st.number_input("Alpha:", value=0.3, min_value=0.00, max_value=1.00, help="Exploration vs exploitation trade-off.\n\n"
             "• 0 → all budget goes to top performers (exploitation)\n"
             "• 1 → budget is spread more evenly (exploration)")
    with col2:
        lambda_val = st.number_input("Lambda:", value=0.8, min_value=0.00, max_value=1.00, help="Controls how exploration is distributed.\n\n"
             "• 1 → fully uniform (everyone gets similar share)\n"
             "• 0 → based on performance score")
    with col3:
        gamma = st.number_input("Gamma:", value=1.5, help="Controls how strongly top performers are favored.\n\n"
             "• 1 → proportional to score\n"
             "• >1 → increasingly favors top authors\n"
             "• <1 → more balanced distribution")

    with col1:
        count1 = st.number_input("Count weight:", value=0.6, min_value=0.00, max_value=1.00, help="Importance of number of publications in the score.")
    with col2:
        citations1 = st.number_input("Citations weight:", value=0.25, min_value=0.00, max_value=1.00, help="Importance of average citations per paper.")
    with col3:
        maxCit1 = st.number_input("Maximum citations weight:", value=0.15, min_value=0.00, max_value=1.00,  help="Importance of the most cited paper (impact peak).")

    col1, col2 = st.columns(2)
    with col1:
        b_floor = st.number_input("Minimum allocation per author (b_floor):", value=0.0, min_value=0.0, help="Minimum guaranteed funding per author.\n\n"
             "Ensures everyone receives at least this amount.")
    with col2:
        b_cap = st.number_input("Maximum allocation per author (b_cap):", value=B, min_value=0.0, help="Maximum funding per author.\n\n"
             "Prevents a single author from receiving too much.")

    if b_floor > b_cap:
        st.warning("Minimum allocation (b_floor) cannot exceed maximum (b_cap). Resetting to defaults.")
        b_floor = 0.0
        b_cap = B

    if st.button("Run budget allocation", type='primary'):
        df_raw = pd.concat(dfClean.values(), ignore_index=True)

        alloc = allocate_budget(
            df=df_raw,
            B=B,
            alpha=alpha,
            gamma=gamma,
            lambda_uniform=lambda_val,
            score_weights={
                "count1_rank": count1,
                "citations1_rank": citations1,
                "maxCitation1_rank": maxCit1
            },
            b_floor=b_floor,
            b_cap=b_cap
        )

        alloc_sorted = alloc.sort_values("b_total", ascending=False).reset_index(drop=True)
        alloc_sorted = alloc_sorted[["authorID", "score", "b_explore", "b_exploit", "b_total"]]

        alloc_sorted["authorID"] = alloc_sorted["authorID"].apply(
            lambda x: f"https://openalex.org/{x}"
        )
        alloc_sorted = alloc_sorted.round(2)
        st.dataframe(
            alloc_sorted,
            column_config={
                "authorID": st.column_config.LinkColumn(
                    "authorID",
                    display_text=r"https://openalex\.org/(.*)"
                )
            }
        )
        st.caption(f"**Shape:** {alloc_sorted.shape}")


st.markdown("""
    <style>
    footer {
        visibility: hidden;
    }
    .footer {
        position: fixed;
        left: 0;
        bottom: 0;
        width: 100%;
        background-color: rgba(240,240,240,0.7);
        text-align: center;
        color: gray;
        font-size: 0.9em;
        padding: 8px 0;
    }
    </style>

    <div class="footer">
        © 2026 - SciLottery 📈
    </div>
""", unsafe_allow_html=True)
