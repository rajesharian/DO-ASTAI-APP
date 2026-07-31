import joblib
import numpy as np
import pandas as pd
import plotly.graph_objects as go
import streamlit as st

st.set_page_config(
    page_title="DOASTAI",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ----------------------------------------------------------------------------
# Model bundle
# ----------------------------------------------------------------------------

LIKERT_OPTIONS = ["Strongly Disagree", "Disagree", "Undecided", "Agree", "Strongly Agree"]
LIKERT_MAP = {"Strongly Disagree": 1, "Disagree": 2, "Undecided": 3, "Agree": 4, "Strongly Agree": 5}

FACTOR_NAMES = {
    "PI": "Personal Inadequacy",
    "IPT": "Interaction with peers & Teachers",
    "FE": "Fear of Examination",
    "IFC": "Inadequate Facilities & College",
    "PESES": "Parents' expectations & Socio-Economic Status",
}

CATEGORY_COLORS = {
    "Very Low Stress": "#2e7d32",
    "Low Stress": "#66bb6a",
    "Moderate Stress": "#fbc02d",
    "High Stress": "#f4511e",
    "Very High Stress": "#c62828",
}

DEMOGRAPHIC_LABELS = {
    "Gender": "Gender",
    "Locality": "Locality",
    "Marital_Status": "Marital Status",
    "Affiliation": "Institution Affiliation",
    "Institution_Type": "Institution Type",
    "Mode_of_Study": "Mode of Study",
    "Category": "Category",
    "Economic_Status": "Economic Status",
    "Undergraduate": "Undergraduate Program (choose 'Not Applicable' if none)",
    "Postgraduate": "Postgraduate Program (choose 'Not Applicable' / 'No' if none)",
    "Semester": "Current Semester",
    "Mothers_Education": "Mother's Education",
    "Fathers_Education": "Father's Education",
}


@st.cache_resource
def load_bundle():
    return joblib.load("aspireai_final_model.pkl")


@st.cache_data
def clean_encoder_options(_bundle):
    """Map each demographic field to {display_label: original_encoder_string}."""
    options = {}
    for field, encoder in _bundle["label_encoders"].items():
        display_to_actual = {}
        for raw in encoder.classes_:
            display = raw.strip()
            if display not in display_to_actual:
                display_to_actual[display] = raw
        options[field] = display_to_actual
    return options


bundle = load_bundle()
model = bundle["model"]
label_encoders = bundle["label_encoders"]
feature_cols = bundle["feature_cols"]
stress_mapping = bundle["stress_mapping"]
psychometric_cols = bundle["psychometric_cols"]
inv_stress_mapping = {v: k for k, v in stress_mapping.items()}
demo_options = clean_encoder_options(bundle)

CLASS_ORDER = [inv_stress_mapping[i] for i in range(len(inv_stress_mapping))]

# ----------------------------------------------------------------------------
# Header
# ----------------------------------------------------------------------------

st.title("🧠 DOASTAI")
st.caption(
    "A validated psychometric assessment tool for students aged 18–25. "
    "Answer honestly — there are no right or wrong answers."
)
with st.expander("About this tool", expanded=False):
    st.markdown(
        """
This tool estimates an academic stress category from **5 validated psychometric
dimensions** — Personal Inadequacy, Interaction with peers & Teachers, Fear of
Examination, Inadequate Facilities at college, and Parents' expectations &
Socio-Economic Status — combined with basic demographic information, using a
model trained on survey data from students aged 18–25.

**This is a research/screening tool, not a clinical diagnosis.** If you are
struggling with stress, anxiety, or your mental health, please reach out to a
counselor, doctor, or a trusted person in your life.
        """
    )

st.divider()

# ----------------------------------------------------------------------------
# Form
# ----------------------------------------------------------------------------

with st.form("aspireai_form"):
    st.subheader("1. About you")
    demo_cols = st.columns(2)
    demo_answers = {}
    for i, field in enumerate(feature_cols):
        if field not in demo_options:
            continue
        col = demo_cols[i % 2]
        opts = list(demo_options[field].keys())
        with col:
            choice = st.selectbox(DEMOGRAPHIC_LABELS.get(field, field), opts, key=f"demo_{field}")
        demo_answers[field] = demo_options[field][choice]

    st.divider()
    st.subheader("2. Psychometric questionnaire")
    st.caption("For each statement, choose how much it applies to you.")

    tabs = st.tabs([f"{k} · {FACTOR_NAMES[k]}" for k in psychometric_cols.keys()])
    likert_answers = {}
    for tab, (factor, questions) in zip(tabs, psychometric_cols.items()):
        with tab:
            for q in questions:
                clean_q = q.split("[", 1)[1].rstrip("]") if "[" in q else q
                likert_answers[q] = st.radio(
                    clean_q,
                    LIKERT_OPTIONS,
                    index=2,
                    horizontal=True,
                    key=f"q_{q}",
                )

    st.divider()
    submitted = st.form_submit_button("Predict my stress level", use_container_width=True, type="primary")

# ----------------------------------------------------------------------------
# Prediction
# ----------------------------------------------------------------------------

if submitted:
    row = {}

    # Demographics — encode with the original trained LabelEncoders
    for field, raw_value in demo_answers.items():
        row[field] = label_encoders[field].transform([raw_value])[0]

    # Psychometric factor scores
    factor_scores = {}
    for factor, questions in psychometric_cols.items():
        score = sum(LIKERT_MAP[likert_answers[q]] for q in questions)
        factor_scores[factor] = score
        row[f"{factor}_Score"] = score

    X_input = pd.DataFrame([[row[c] for c in feature_cols]], columns=feature_cols)

    prediction = model.predict(X_input)[0]
    probabilities = model.predict_proba(X_input)[0]
    predicted_label = inv_stress_mapping[prediction]

    total_score = sum(factor_scores.values())

    st.divider()
    st.subheader("Results")

    color = CATEGORY_COLORS.get(predicted_label, "#455a64")
    st.markdown(
        f"""
        <div style="padding:1.2rem 1.5rem;border-radius:0.6rem;background:{color}22;
                    border:1px solid {color};margin-bottom:1rem;">
            <div style="font-size:0.9rem;color:#555;">Predicted category</div>
            <div style="font-size:1.8rem;font-weight:700;color:{color};">{predicted_label}</div>
            <div style="font-size:0.9rem;color:#555;margin-top:0.3rem;">
                Total psychometric score: <b>{total_score}</b> &nbsp;·&nbsp;
                Model confidence: <b>{probabilities[prediction]*100:.1f}%</b>
            </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    col_a, col_b = st.columns(2)

    with col_a:
        st.markdown("**Probability across all categories**")
        fig_prob = go.Figure(
            go.Bar(
                x=[probabilities[stress_mapping[c]] * 100 for c in CLASS_ORDER],
                y=CLASS_ORDER,
                orientation="h",
                marker_color=[CATEGORY_COLORS[c] for c in CLASS_ORDER],
                text=[f"{probabilities[stress_mapping[c]]*100:.1f}%" for c in CLASS_ORDER],
                textposition="outside",
            )
        )
        fig_prob.update_layout(
            xaxis_title="Probability (%)",
            xaxis_range=[0, 100],
            height=320,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_prob, use_container_width=True)

    with col_b:
        st.markdown("**Score breakdown by dimension**")
        fig_factors = go.Figure(
            go.Bar(
                x=list(factor_scores.values()),
                y=[f"{k} · {FACTOR_NAMES[k]}" for k in factor_scores.keys()],
                orientation="h",
                marker_color="#5c6bc0",
                text=list(factor_scores.values()),
                textposition="outside",
            )
        )
        fig_factors.update_layout(
            xaxis_title="Sub-score",
            height=320,
            margin=dict(l=10, r=10, t=10, b=10),
        )
        st.plotly_chart(fig_factors, use_container_width=True)

    st.caption(
        "Sub-scores are the sum of your Likert responses (1–5) within each dimension. "
        "Higher scores indicate greater self-reported stress in that dimension."
    )

    if predicted_label in ("High Stress", "Very High Stress"):
        st.warning(
            "Your responses suggest a high level of academic stress. Consider talking to a "
            "counselor, academic advisor, or someone you trust. If you're in emotional distress, "
            "please reach out to a mental health professional or a crisis line in your area."
        )

    st.divider()
    with st.expander("See your raw inputs"):
        st.write("**Demographics (encoded):**", row)
        st.write("**Factor scores:**", factor_scores)
