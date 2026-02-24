from email.policy import default

from numpy.matlib import empty

from utils.pipeline import *

import pandas as pd
import streamlit as st

st.set_page_config(
    page_title="OpenAlex Performance Predictor CNB",
    page_icon='📈'
)

st.markdown("""
<style>
[data-testid="stAppViewContainer"] {
    background-color: #FAF8F7; 
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

logo_placeholder = st.empty()
logo_placeholder.markdown(
    """
    <div class="fixed-logo"></div>
    """,
    unsafe_allow_html=True
)

col1, col2 = st.columns([1,4])
st.logo("assets/bcu_logo.png", size="large")

with col1:
    st.image("assets/CNB_2025.png", width=180)
with col2:
    st.markdown(
        "<h1 style='text-align:left; margin-bottom:0;'>OpenAlex Performance Predictor</h1>",
        unsafe_allow_html=True
    )
    st.markdown(
        "<p style='text-align:left; color:gray; margin-top:0;'>TODO write description</p>",
        unsafe_allow_html=True
    )

# Get all institutions authors (test)
#todo quitar cuando este terminado
allInstitutions = [
    "i4210087039", # 1 Instituto Investig. Biomedicas
    "i4210130807", # 2 Instituto Astrofisico de Canarias
    "i4210107147", # 3 Instituto Catalan de Oncologia
    "i4210120109", # 4 Museo Nac. Ciencias Naturales
    "i4210151127", # 5 Inst. Geociencias
    "i4210126640", # 6 Inst. Filosofia
    "i4210165411", # 7 CIEMAT
    "i4210113665", # 8 IIB Granada
    "i4210086614", # 9 Inst. Invest. 12 de octubre
    "i4210105802", # 10 Inst. Historia
    "i4210105141", # 11 Bioingenieria de Zaragoza
    "i4210118429", # 12 Ciencia de materiales de Madrid
    "i4210146061", # 13 CBM
    "i2799803557", # 14 BSC
    "i4210102407", # 15 Inst. Invest. Vall d'Hebron
    "i4210147680", # 16 CIB
    "i4210151560", # 17 Ciencias del Mar
    "i4210159146", # 18 Inst. Astrofisica de Andalucia
    "i4210148332", # 19 Barcelona Global Health
    "i4210129656", # 20 Ecologia
]
year=2020 # todo use this in the search!?


email = st.text_input("User e-mail:", key="OpenAlex user email", value='blanca.pueche@cnb.csic.es')

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
    fnAll = "app/dfMultInst.p"
    if os.path.exists(fnAll):
        dfAll = pickle.load(open(fnAll, "rb"))
elif searchBy == options[1]:
    # Selected authors
    inputIds = st.text_input("Author ids:", help='If more than one, separate with commas.')
    fnAll = "app/dfMultAids.p"
    if os.path.exists(fnAll):
        dfAll = pickle.load(open(fnAll, "rb"))

# submit
if inputIds:
    if not dfAll:
        with st.spinner("OpenAlex search..."):
            try:
                if searchBy == options[0]:
                    #inst_id = ['i4210151560', 'i4210129656']
                    inst_ids = [x.strip() for x in inputIds.split(",") if x.strip()]
                    #check validity
                    inst_ids = checkValid(inst_ids, 'i', st)
                    for inst in inst_ids:
                        try:
                            aids = authors_working_at_institution_in_year(inst, year, email)
                        except Exception as e:
                            st.error(f"Error retrieving authors for institution {inst}: {e}")
                            st.stop()
                        df = build_author_df_and_unique_work_distributions(aids, Y=year, mailto=MAILTO, sleep_s=0.05)
                        df = df[(df["count1"] > 0)].reset_index(drop=True)
                        dfAll[inst_ids] = df
                    fnAll = "app/dfMultInst.p"
                    pickle.dump(dfAll, open(fnAll, "wb"))
                elif searchBy == options[1]:
                    #aids = ['A5050710342', 'A5051113581', 'A5010137759', 'A5039659064']
                    aids = [x.strip() for x in inputIds.split(",") if x.strip()]
                    aids = checkValid(aids, 'A', st)
                    inst_ids = get_inst_ids_from_authors(aids, email)
                    for inst_id in set(inst_ids):
                        try:
                            aids_in_inst = authors_working_at_institution_in_year(inst_id, year, email)
                        except Exception as e:
                            st.error(f"Error retrieving authors for institution {inst_id}: {e}")
                            #st.stop()

                        df_inst = build_author_df_and_unique_work_distributions(
                            aids_in_inst, Y=year, mailto=MAILTO, sleep_s=1
                        )
                        df_inst = df_inst[df_inst["count1"] > 0].reset_index(drop=True)

                        dfAll[inst_id] = df_inst
                    fnAll = "app/dfMultAids.p"
                    pickle.dump(dfAll, open(fnAll, "wb"))

            except Exception as e:
                st.error(f"Unexpected error during OpenAlex search: {e}")
                st.stop()

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
        st.dataframe(df)
        st.caption(f"**Shape:** {df.shape}", )

        B = 1                      # total budget todo do i out it as param!?
        score_col = "avgPerc1"
        target_col = "avgPerc2"

        alpha = None
        lambda_val = None
        gamma = None

        st.header('Budget allocation')
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
                    B=1,
                    score_col='avgPerc1',
                    alpha=alpha,
                    lambda_uniform=lambda_val,
                    gamma=gamma,
                    id_col='authorID',
                    add_columns=True
                )


            st.dataframe(alloc)
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
