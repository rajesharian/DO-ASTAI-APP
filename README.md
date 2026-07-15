# AspireAI — Academic Stress Predictor (Streamlit App)

A Streamlit app that predicts a student's academic stress category (Very Low →
Very High) from a 66-item psychometric questionnaire plus basic demographics,
using the tuned Logistic Regression model exported from the AspireAI notebook.

## Files

- `app.py` — the Streamlit app
- `aspireai_final_model.pkl` — trained model bundle (pipeline + label encoders +
  feature order + stress mapping + question text), exported from the notebook
- `requirements.txt` — pinned dependencies (scikit-learn is pinned to `1.6.1`,
  the version the model was actually trained/pickled with — using a different
  version can silently change predictions, not just print a warning)

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

Then open the local URL Streamlit prints (usually `http://localhost:8501`).

## Deploy to Streamlit Community Cloud

1. **Push this folder to a GitHub repo** (public or private). Make sure
   `aspireai_final_model.pkl` is actually committed — check its size isn't
   silently ignored by a stray `.gitignore` rule, and that it's under GitHub's
   100 MB file limit (this one is well under that).
2. Go to **[share.streamlit.io](https://share.streamlit.io)** and sign in with
   GitHub.
3. Click **"New app"**, pick this repo/branch, and set the main file path to
   `app.py`.
4. Click **Deploy**. First build takes a few minutes while it installs
   `requirements.txt`.
5. Once live, you'll get a public URL like
   `https://<your-app-name>.streamlit.app`.

### If the deployed predictions look different from local

That almost always means the deployed environment resolved a different
scikit-learn version than what trained the model. Check the Streamlit Cloud
build logs for the installed scikit-learn version and make sure it matches
`requirements.txt` (`1.6.1`). If Streamlit Cloud can't resolve that exact
version for its Python version, re-export the model bundle from the notebook
using the newer scikit-learn instead of trying to force the old version.

## Notes on the model

- Only 5 psychometric factor scores (PI, IPT, FE, IFC, PE&SES) and 13
  demographic fields are used as model inputs — exactly the `feature_cols`
  stored in the pickle bundle.
- Demographic dropdowns are deduplicated by trimming whitespace (e.g. the
  training data had both `"Campus"` and `"Campus "` as separate categories);
  the app maps the cleaned label back to whichever original string the
  encoder was actually trained on.
- This tool is a research/screening aid, not a clinical diagnostic instrument.
