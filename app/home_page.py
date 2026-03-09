import os
import pickle
import random

from utils.pipeline import *

import pandas as pd
import streamlit as st

if "dfAll" not in st.session_state:
    st.session_state.dfAll = None
st.set_page_config(
    page_title="OpenAlex Performance Predictor CNB",
    page_icon='📈'
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
    "<h1 style='text-align:left; margin-bottom:0;'>OpenAlex Performance Predictor</h1>",
    unsafe_allow_html=True
)
st.markdown(
    "<p style='text-align:left; color:gray; margin-top:0;'>TODO write description</p>",
    unsafe_allow_html=True
)

# Input options and params
email = st.text_input("User e-mail:", help="OpenAlex user email")

year = st.number_input("Year:", help="Year to search in OpenAlex", value=2020)
options = ['Institute', 'Author']
searchBy = st.pills('Search by: ', options, selection_mode="single", default=None)

if not email and searchBy:
    st.warning("Email must be entered to continue")
    st.stop()

inputIds = None
dfAll = {}
if searchBy == options[0]:
    # Selected institutions
    inputIds = st.text_input("Institute ids:", help='If more than one, separate with commas.')
    #todo delete this when its finished
    fnAll = "app/dfMultInst.p"
    if os.path.exists(fnAll):
        dfAll = pickle.load(open(fnAll, "rb"))
elif searchBy == options[1]:
    # Selected authors
    inputIds = st.text_input("Author ids:", help='If more than one, separate with commas.')
    # todo delete this when its finished
    fnAll = "app/dfMultAids.p"
    if os.path.exists(fnAll):
        dfAll = pickle.load(open(fnAll, "rb"))

# Submit to retrieve info
if inputIds:
    minPapers = st.number_input("Minimum number of papers per author:", value=10, min_value=0)
    # todo delete this check when its finished
    if st.button("Perform search", type='primary'):
        if not dfAll:
            with st.spinner("OpenAlex search..."):
                try:
                    if searchBy == options[0]:
                        inst_ids = sanitizeIds(inputIds, st, prefix='i')
                        #check id validity
                        inst_ids = checkValid(inst_ids, 'i', st)
                        for inst in inst_ids:
                            aids = None
                            for attempt in range(5):
                                aids, msg = authors_working_at_institution_in_year(inst, year, email)
                                if not aids:
                                    st.warning(f"{msg}. Retrying...")
                                    time.sleep(1 * (2 ** attempt))
                                    continue
                                break
                            if not aids:
                                st.warning(f"Skipping institution {inst} due to repeated errors.")
                                continue

                            df = build_author_df_and_unique_work_distributions(
                                aids, Y=year, mailto=email, sleep_s=0.05
                            )
                            df = df[df["count1"] >= minPapers].reset_index(drop=True)
                            dfAll[inst] = df
                    elif searchBy == options[1]:
                        aids = sanitizeIds(inputIds, st, prefix='A')
                        # check id validity
                        aids = checkValid(aids, 'A', st)
                        df = None
                        for attempt in range(5):
                            df = build_author_df_and_unique_work_distributions(
                                aids, Y=year, mailto=email, sleep_s=0.05
                            )
                            if df is None or df.empty:
                                st.warning("Rate limit hit while retrieving author data. Retrying...")
                                time.sleep(1 * (2 ** attempt))
                                continue
                            break

                        if df is None or df.empty:
                            st.warning("Author data incomplete due to repeated errors.")
                        else:
                            df = df[df["count1"] >= minPapers].reset_index(drop=True)
                            dfAll["inputAIDs"] = df
                    st.session_state.dfAll = dfAll
                except Exception as e:
                    st.error(f"Unexpected error during OpenAlex search: {e}")
                    st.stop()

dfAll = st.session_state.dfAll
if dfAll:
    # Add citations columns
    cols = ["count", "citationAvg", "maxCitation"]
    dfClean = {}
    parts = []

    for inst_id, df in dfAll.items():
        d = df.loc[df["count1"] > 1].copy()

        d["citationAvg1"] = d["citations1"] / d["count1"]
        d["citationAvg2"] = d["citations2"] / d["count2"]

        for suffix in ["1","2"]:
          for c in cols:
              col = f"{c}{suffix}"
              d[f"{col}Perc"] = d[col].rank(pct=True)
        d["avgPerc1"]=(d["citationAvg1Perc"]+d["count1Perc"]+d["maxCitation1Perc"])/3
        d["avgPerc2"]=(d["citationAvg2Perc"]+d["count2Perc"]+d["maxCitation2Perc"])/3

        #filter if only specific authors
        if searchBy == options[1]:
            selected_aids = [x.strip() for x in inputIds.split(",") if x.strip()]
            d = d[d["authorID"].isin(selected_aids)]


        dfAll[inst_id] = d

        # collect only percentile columns
        perc_cols = [f"{c}{suffix}Perc" for c in cols for suffix in ["1", "2"]]
        out = d.loc[:, ["authorID","avgPerc1","avgPerc2"]+perc_cols].copy()

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
    B = st.number_input("Total budget:", help="", value=1)
    col1, col2, col3 = st.columns(3)
    with col1:
        alpha = st.number_input("Alpha:", value=0.3, min_value=0.00, max_value=1.00)
    with col2:
        lambda_val = st.number_input("Lambda:", value=0.8, min_value=0.00, max_value=1.00)
    with col3:
        gamma = st.number_input("Gamma:", value=1.5)

    if st.button("Submit", type='primary'):
        alloc = allocate_budget(
                df=df,
                B=B,
                score_col='avgPerc1',
                alpha=alpha,
                lambda_uniform=lambda_val,
                gamma=gamma,
                id_col='authorID',
                add_columns=True
            )

        st.dataframe(
            alloc,
            column_config={
                "authorID": st.column_config.LinkColumn(
                    "authorID",
                    display_text=r"https://openalex\.org/(.*)"
                )
            }
        )
        st.caption(f"**Shape:** {alloc.shape}")


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
        © 2026 CNB – Performance predictor 📈
    </div>
""", unsafe_allow_html=True)
