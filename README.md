# AspireAI — Academic Stress Predictor (Streamlit App)

A Streamlit app that predicts a student's academic stress category from a
66-item psychometric questionnaire plus demographics, generates a unique code
per student so they can retake the questionnaire later and see how their
stress has changed, and gives targeted interventions.

## Workflow

**Welcome screen** — two options:
- **New Assessment** — full 79-step wizard (13 demographic questions, one of
  which branches into "Undergraduate program?" or "Postgraduate program?"
  depending on what the student is pursuing, followed by all 66 psychometric
  questions, one at a time). On submit: generates a unique code
  (`ASP-XXXXXX`), saves the response to Google Sheets, and offers a
  downloadable personal Excel copy.
- **Returning User** — enter a previously issued code, retake just the
  66-question questionnaire (demographics are pulled from the first
  submission automatically), and get a comparison against the last
  submission: per-factor deltas, total score change, category movement, and
  a plain-language verdict on whether things have improved.

Every question is answered one at a time — nothing is pre-selected, and the
app won't advance until you actually answer.

## Files

- `app.py` — the Streamlit app
- `aspireai_final_model.pkl` — trained model bundle
- `requirements.txt` — pinned dependencies
- `media/` — optional folder for your own audio/video intervention files

## Run locally

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Deploy to Streamlit Community Cloud

1. Push this folder to a GitHub repo, including `aspireai_final_model.pkl`.
2. On [share.streamlit.io](https://share.streamlit.io), create a new app
   pointing at this repo, branch, and `app.py` as the main file.
3. **Set the Python version** (Settings → Python version → 3.11, or add a
   `runtime.txt` with `3.11` in it) — a newer, unpinned Python has previously
   caused install failures with this dependency set.
4. Complete the Google Sheets setup — see
   [`SETUP_GOOGLE_SHEETS.md`](SETUP_GOOGLE_SHEETS.md). **This is no longer
   optional**: the "Returning User" comparison feature needs Google Sheets as
   its database to look up a code across sessions. Without it, New
   Assessments still work and generate a code, but that code can't be
   retrieved later — the welcome screen shows a warning when this happens.

## Data stored per submission

One row per submission (baseline or follow-up), all under one fixed column
schema so the sheet stays queryable:

`Unique_Code, Submission_No, Timestamp_UTC, Submission_Type, <11 demographic
fields>, Pursuing, Undergraduate, Postgraduate, <5 factor scores>,
Total_Score, Predicted_Category, Confidence`

Demographic values are stored as the raw strings the model's encoders
recognize (not display labels), so a returning user's follow-up submission
can reuse them directly without re-collecting demographics.

## Notes on the model

- Undergraduate is simplified to **BA / BCom / BSc / BCA / BTech / Other**;
  Postgraduate to **MA / MCom / MSc / MCA / MTech / Other**. Each maps to one
  representative raw value the model's encoder recognizes. Note: MCA and
  MTech currently map to the same raw value (`Computer Science`) since the
  original survey data has no dedicated engineering postgraduate category.
- "Not Applicable" (i.e. not pursuing the other of UG/PG) is set
  automatically based on which one the student says they're pursuing.
- This tool is a research/screening aid, not a clinical diagnostic instrument.
