import datetime as dt
import io
import os
import random
import string

import joblib
import openpyxl
import pandas as pd
import plotly.graph_objects as go
import streamlit as st
import streamlit.components.v1 as components

try:
    import gspread
    from google.oauth2.service_account import Credentials

    GSPREAD_AVAILABLE = True
except ImportError:
    GSPREAD_AVAILABLE = False

st.set_page_config(
    page_title="DOAST-AI",
    page_icon="🧠",
    layout="centered",
    initial_sidebar_state="collapsed",
)

# ----------------------------------------------------------------------------
# Constants
# ----------------------------------------------------------------------------

LIKERT_OPTIONS = ["Strongly Disagree", "Disagree", "Undecided", "Agree", "Strongly Agree"]
LIKERT_MAP = {"Strongly Disagree": 1, "Disagree": 2, "Undecided": 3, "Agree": 4, "Strongly Agree": 5}

FACTOR_NAMES = {
    "PI": "Personal Inadequacy",
    "IPT": "Interaction with Peers & Teachers",
    "FE": "Fear of Examination",
    "IFC": "Inadequate Facilities at College",
    "PESES": "Parental Expectations & Socio-Economic Status",
}

CATEGORY_COLORS = {
    "Very Low Stress": "#2e7d32",
    "Low Stress": "#66bb6a",
    "Moderate Stress": "#fbc02d",
    "High Stress": "#f4511e",
    "Very High Stress": "#c62828",
}

# A factor is flagged as individually elevated once its normalized score (share
# of the maximum possible score for that factor) crosses this line — independent
# of what the overall predicted category is.
HIGH_FACTOR_INTENSITY_THRESHOLD = 0.70

PAIR_INTERVENTIONS = {
    frozenset(("PI", "IPT")): (
        "Self-doubt and interpersonal/teaching friction tend to reinforce each other — "
        "feeling inadequate can make it harder to ask for help, which then makes the "
        "friction worse. Addressing the interpersonal side (even a single honest "
        "conversation with a teacher or peer) often eases the self-doubt too."
    ),
    frozenset(("PI", "FE")): (
        "Self-doubt and exam fear commonly feed each other — a disappointing result "
        "confirms the 'not good enough' belief, which then raises anxiety for the next "
        "exam. Breaking the cycle usually starts with the exam-prep side (structured "
        "review, practice tests) rather than trying to 'feel more confident' first."
    ),
    frozenset(("PI", "IFC")): (
        "It can be hard to tell how much of the struggle is you versus a genuinely "
        "under-resourced environment. If facilities are a real constraint, that's worth "
        "separating out from self-doubt rather than absorbing it as a personal failing."
    ),
    frozenset(("PI", "PESES")): (
        "Self-doubt combined with family or financial pressure often centers on feeling "
        "like you need to 'prove' something. Naming that pressure out loud, even just to "
        "yourself, can help separate your own goals from ones inherited from expectation."
    ),
    frozenset(("IPT", "FE")): (
        "Friction with a specific teacher can heighten exam fear tied to that subject "
        "particularly. If that's the pattern, addressing the relationship (even just "
        "clarifying expectations) can reduce the exam anxiety more directly than general "
        "study techniques would."
    ),
    frozenset(("IPT", "IFC")): (
        "Difficult environments (crowded, poorly resourced spaces) often amplify "
        "interpersonal tension. Raising facility issues collectively with classmates can "
        "help on both fronts at once."
    ),
    frozenset(("IPT", "PESES")): (
        "It's common to feel unable to discuss personal or interpersonal struggles when "
        "there's pressure to 'not worry the family' or to justify a costly education. A "
        "trusted mentor or counselor outside the family can be a useful outlet here."
    ),
    frozenset(("FE", "IFC")): (
        "Exam fear tends to intensify when the environment itself doesn't support "
        "focused study (no quiet space, limited library access). If that's fixable "
        "even partially — a different study spot, library hours — it can meaningfully "
        "lower exam-specific anxiety."
    ),
    frozenset(("FE", "PESES")): (
        "Exam fear combined with financial or family pressure often means the stakes "
        "feel unusually high — a single exam carrying the weight of a family's "
        "investment. It can help to separate 'doing your best' from 'guaranteeing an "
        "outcome you can't fully control.'"
    ),
    frozenset(("IFC", "PESES")): (
        "Facility or environment limitations combined with financial pressure can "
        "compound — there's less room to pay for alternatives (private tutoring, better "
        "internet, etc.) when the environment itself falls short. Checking whether your "
        "institution has support funds or resource-sharing programs may help."
    ),
}

CATEGORY_INTERVENTIONS = {
    "Very Low Stress": [
        "Your responses suggest you're managing academic demands well right now — keep up whatever routines are working for you.",
        "It's still worth checking in with yourself regularly, since stress levels can shift with deadlines and exams.",
        "Consider using some of this steady period to build habits (sleep, exercise, study routine) that act as a buffer later.",
    ],
    "Low Stress": [
        "You're generally coping well, with some manageable pressure here and there.",
        "Keep an eye on the specific dimension(s) below that scored relatively higher — small adjustments there now can prevent buildup later.",
        "Simple habits like regular sleep, short breaks between study sessions, and staying connected with friends go a long way at this stage.",
    ],
    "Moderate Stress": [
        "Your responses suggest a noticeable but manageable level of academic stress.",
        "Try breaking large tasks into smaller ones with clear deadlines — it tends to reduce the feeling of being overwhelmed.",
        "Regular breaks, physical activity, and consistent sleep can measurably reduce day-to-day stress at this level.",
        "It may help to talk to a friend, mentor, or academic advisor about what's feeling heaviest right now.",
    ],
    "High Stress": [
        "Your responses suggest a high level of academic stress — this is worth taking seriously.",
        "Consider reaching out to your institution's student counseling service, if available — many offer free, confidential sessions.",
        "Talking to an academic advisor about workload, deadlines, or exam accommodations can genuinely help, not just emotionally but practically.",
        "Try to protect basic routines — sleep, meals, some physical movement — even when everything else feels urgent.",
    ],
    "Very High Stress": [
        "Your responses suggest a very high level of academic stress.",
        "Please consider speaking with a counselor, doctor, or mental health professional soon — this level of stress is hard to manage alone.",
        "If you're a student, most institutions have a counseling center; a visit or even a phone call can be a good first step.",
        "Reach out to someone you trust — a friend, family member, or mentor — about how you've been feeling.",
    ],
}

FACTOR_INTERVENTIONS = {
    "PI": {
        "title": "Personal Inadequacy",
        "tips": [
            "Try noticing and questioning self-critical thoughts ('I'm not good enough') rather than automatically accepting them.",
            "Set smaller, achievable goals and acknowledge progress — confidence tends to build from evidence, not willpower.",
            "Talking to a counselor or mentor about self-doubt can help separate realistic concerns from harsh self-judgment.",
        ],
    },
    "IPT": {
        "title": "Interaction with Peers & Teachers",
        "tips": [
            "If specific interactions with teachers or peers are a recurring source of stress, consider raising it with an academic advisor or student support office.",
            "Building even one or two supportive peer relationships can meaningfully reduce isolation.",
            "Practicing direct but calm communication (e.g. asking a teacher for clarification rather than staying silent) often reduces ongoing friction.",
        ],
    },
    "FE": {
        "title": "Fear of Examination",
        "tips": [
            "Spaced, active review (practice questions, teaching concepts to someone else) tends to reduce exam anxiety more than re-reading notes.",
            "Simple breathing exercises before an exam (slow inhale, longer exhale, repeated a few times) can lower acute anxiety in the moment.",
            "If exam fear feels disproportionate or panic-like, it's worth mentioning to a counselor — there are specific techniques that help.",
        ],
    },
    "IFC": {
        "title": "Inadequate Facilities at College",
        "tips": [
            "If specific facilities (library access, labs, hostel conditions, etc.) are a real bottleneck, raising it with student representatives or administration can lead to actual fixes, not just coping.",
            "Where possible, identify alternate quiet study spaces (public library, empty classrooms) if your usual environment is a stressor.",
            "Connecting with classmates facing similar facility issues can help — collective feedback is often taken more seriously.",
        ],
    },
    "PESES": {
        "title": "Parental Expectations & Socio-Economic Status",
        "tips": [
            "If financial pressure is a major factor, check whether your institution offers scholarships, fee waivers, or emergency student funds.",
            "Talking openly with family about academic and financial expectations, even briefly, can reduce the weight of carrying it silently.",
            "Peer support groups or mentorship programs for first-generation or under-resourced students exist at many institutions — worth asking your student services office.",
        ],
    },
}

# ----------------------------------------------------------------------------
# Media interventions (audio/video)
# ----------------------------------------------------------------------------
YOUTUBE_LINKS = {
    "Very High Stress": "",
    "High Stress": "",
    "FE": "",
}
LOCAL_AUDIO_FILES = {
    "Moderate Stress": "",
}
LOCAL_VIDEO_FILES = {
    "High Stress": "",
}
MEDIA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media")


def show_media_for(key: str):
    yt = YOUTUBE_LINKS.get(key, "")
    if yt:
        st.video(yt)
    audio_file = LOCAL_AUDIO_FILES.get(key, "")
    if audio_file:
        path = os.path.join(MEDIA_DIR, audio_file)
        if os.path.exists(path):
            st.audio(path)
        else:
            st.caption(f"(Configured audio file `{audio_file}` not found in the media/ folder.)")
    video_file = LOCAL_VIDEO_FILES.get(key, "")
    if video_file:
        path = os.path.join(MEDIA_DIR, video_file)
        if os.path.exists(path):
            st.video(path)
        else:
            st.caption(f"(Configured video file `{video_file}` not found in the media/ folder.)")


BREATHING_EXERCISE_HTML = """
<div style="display:flex;flex-direction:column;align-items:center;
            font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;
            padding:1rem 0;">
  <div id="breathCircle" style="width:120px;height:120px;border-radius:50%;
       background:radial-gradient(circle at 35% 35%, #90caf9, #42a5f5);
       transition:transform 4s ease-in-out;box-shadow:0 0 30px rgba(66,165,245,0.5);">
  </div>
  <div id="breathLabel" style="margin-top:1.2rem;font-size:1.3rem;font-weight:600;color:#333;">
    Press Start
  </div>
  <div style="margin-top:1rem;display:flex;gap:0.6rem;">
    <button id="startBtn" style="padding:0.5rem 1.2rem;border-radius:2rem;border:none;
        background:#42a5f5;color:white;font-weight:600;cursor:pointer;">Start</button>
    <button id="stopBtn" style="padding:0.5rem 1.2rem;border-radius:2rem;border:1px solid #ccc;
        background:white;color:#555;font-weight:600;cursor:pointer;">Stop</button>
    <label style="display:flex;align-items:center;gap:0.4rem;font-size:0.9rem;color:#555;margin-left:0.5rem;">
      <input type="checkbox" id="soundToggle"> Sound
    </label>
  </div>
  <div style="margin-top:0.6rem;font-size:0.8rem;color:#888;">4s inhale · 4s hold · 4s exhale · 4s hold</div>
</div>
<script>
(function() {
  const circle = document.getElementById('breathCircle');
  const label = document.getElementById('breathLabel');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const soundToggle = document.getElementById('soundToggle');
  let phaseIndex = 0;
  let timer = null;
  let audioCtx = null;
  let oscillator = null;
  let gainNode = null;

  const phases = [
    { name: 'Inhale', scale: 1.6, duration: 4000 },
    { name: 'Hold', scale: 1.6, duration: 4000 },
    { name: 'Exhale', scale: 1.0, duration: 4000 },
    { name: 'Hold', scale: 1.0, duration: 4000 },
  ];

  function ensureAudio() {
    if (!audioCtx) {
      audioCtx = new (window.AudioContext || window.webkitAudioContext)();
      oscillator = audioCtx.createOscillator();
      gainNode = audioCtx.createGain();
      oscillator.type = 'sine';
      oscillator.frequency.value = 220;
      gainNode.gain.value = 0;
      oscillator.connect(gainNode);
      gainNode.connect(audioCtx.destination);
      oscillator.start();
    }
  }

  function setTone(target, duration) {
    if (soundToggle.checked && audioCtx) {
      const now = audioCtx.currentTime;
      gainNode.gain.cancelScheduledValues(now);
      gainNode.gain.setValueAtTime(gainNode.gain.value, now);
      gainNode.gain.linearRampToValueAtTime(target, now + duration / 1000);
    }
  }

  function runPhase() {
    const phase = phases[phaseIndex % phases.length];
    label.textContent = phase.name;
    circle.style.transform = `scale(${phase.scale})`;
    setTone(phase.name === 'Inhale' ? 0.04 : (phase.name === 'Exhale' ? 0.0 : gainNode ? gainNode.gain.value : 0), phase.duration);
    phaseIndex++;
    timer = setTimeout(runPhase, phase.duration);
  }

  startBtn.addEventListener('click', function() {
    if (soundToggle.checked) ensureAudio();
    if (timer) clearTimeout(timer);
    phaseIndex = 0;
    runPhase();
  });

  stopBtn.addEventListener('click', function() {
    if (timer) clearTimeout(timer);
    label.textContent = 'Press Start';
    circle.style.transform = 'scale(1)';
    if (gainNode) gainNode.gain.value = 0;
  });
})();
</script>
"""


def show_breathing_exercise():
    components.html(BREATHING_EXERCISE_HTML, height=320)


DEMOGRAPHIC_LABELS = {
    "Gender": "Gender",
    "Locality": "Locality",
    "Marital_Status": "Marital Status",
    "Affiliation": "Institution Affiliation",
    "Institution_Type": "Institution Type",
    "Mode_of_Study": "Mode of Study",
    "Category": "Category",
    "Economic_Status": "Economic Status",
    "Semester": "Current Semester",
    "Mothers_Education": "Mother's Education",
    "Fathers_Education": "Father's Education",
}

# Fields asked as simple single-select demographic questions in the wizard
# (Undergraduate/Postgraduate are handled separately via the pursuing-branch).
SIMPLE_DEMO_FIELDS = [
    "Gender", "Locality", "Marital_Status", "Affiliation", "Institution_Type",
    "Mode_of_Study", "Category", "Economic_Status", "Semester",
    "Mothers_Education", "Fathers_Education",
]

# ----------------------------------------------------------------------------
# Model bundle
# ----------------------------------------------------------------------------

@st.cache_resource
def load_bundle():
    return joblib.load("aspireai_final_model.pkl")


UNDERGRAD_GROUPS = {
    "BA": "B.A",
    "BCom": "Commerce",
    "BSc": "Science",
    "BCA": "BCA",
    "BTech": "Btech ",
    "Other": "Special (vi)",
}

POSTGRAD_GROUPS = {
    "MA": "Arts",
    "MCom": "Commerce",
    "MSc": "Science",
    "MCA": "Computer Science",
    "MTech": "Computer Science",
    "Other": "Special (vi)",
}

NOT_APPLICABLE_RAW = "Not Applicable"


@st.cache_data
def clean_encoder_options(_bundle):
    """Map each demographic field to {display_label: original_encoder_string}."""
    options = {}
    for field, encoder in _bundle["label_encoders"].items():
        known_classes = set(encoder.classes_)
        if field == "Undergraduate":
            options[field] = {l: r for l, r in UNDERGRAD_GROUPS.items() if r in known_classes}
            continue
        if field == "Postgraduate":
            options[field] = {l: r for l, r in POSTGRAD_GROUPS.items() if r in known_classes}
            continue
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
FACTORS = list(psychometric_cols.keys())

# ----------------------------------------------------------------------------
# Google Sheets — persistent store (required for the returning-user comparison
# feature; without it, codes can't be looked up across sessions since
# Streamlit Cloud has no persistent filesystem).
# ----------------------------------------------------------------------------

SHEETS_CONFIGURED = (
    GSPREAD_AVAILABLE and "gcp_service_account" in st.secrets and "sheet_id" in st.secrets
)

SHEET_COLUMNS = (
    ["Unique_Code", "Submission_No", "Timestamp_UTC", "Submission_Type"]
    + SIMPLE_DEMO_FIELDS
    + ["Pursuing", "Undergraduate", "Postgraduate"]
    + [f"{f}_Score" for f in FACTORS]
    + ["Total_Score", "Predicted_Category", "Confidence"]
)


@st.cache_resource
def get_gsheet():
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(dict(st.secrets["gcp_service_account"]), scopes=scopes)
    client = gspread.authorize(creds)
    return client.open_by_key(st.secrets["sheet_id"]).sheet1


def log_response(row_dict: dict) -> tuple[bool, str | None]:
    """Append one response row (aligned to SHEET_COLUMNS) to the sheet. Never raises."""
    if not SHEETS_CONFIGURED:
        return False, "not_configured"
    try:
        sheet = get_gsheet()
        current_values = sheet.get_all_values()
        # Google Sheets can report a "visually blank" sheet as a non-empty list (e.g. one
        # row of empty strings left over from prior formatting/used-range metadata) even
        # after all content has been deleted — check for that explicitly rather than
        # trusting truthiness of the returned list.
        is_effectively_blank = not current_values or all(
            all(cell == "" for cell in row) for row in current_values
        )
        if is_effectively_blank:
            if current_values:
                sheet.clear()
            sheet.append_row(SHEET_COLUMNS)
        elif current_values[0] != SHEET_COLUMNS:
            return False, (
                "The sheet's header row doesn't match this app's expected columns — likely "
                "left over from an earlier version of the app. Clear all content in the "
                "Google Sheet (select all cells, delete) and submit again so a correct header "
                "can be written. Existing rows under the old header won't be found by code "
                "lookup until this is fixed."
            )
        sheet.append_row([str(row_dict.get(c, "")) for c in SHEET_COLUMNS])
        return True, None
    except Exception as e:  # noqa: BLE001
        return False, str(e)


def run_sheets_diagnostics() -> dict:
    """Live-checks the Google Sheets connection step by step and returns what actually failed."""
    result = {
        "gspread_installed": GSPREAD_AVAILABLE,
        "secrets_has_service_account": "gcp_service_account" in st.secrets,
        "secrets_has_sheet_id": "sheet_id" in st.secrets,
        "service_account_email": None,
        "connected": False,
        "can_read": False,
        "can_write": False,
        "error": None,
    }
    if not GSPREAD_AVAILABLE:
        result["error"] = "gspread/google-auth aren't installed — check requirements.txt was updated and redeployed."
        return result
    if "gcp_service_account" not in st.secrets or "sheet_id" not in st.secrets:
        result["error"] = "Secrets are missing 'gcp_service_account' and/or 'sheet_id' — check Streamlit Settings → Secrets."
        return result

    try:
        result["service_account_email"] = st.secrets["gcp_service_account"].get("client_email")
    except Exception:
        pass

    try:
        sheet = get_gsheet()
        result["connected"] = True
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Could not authenticate/open the sheet: {e}"
        return result

    try:
        sheet.get_all_values()
        result["can_read"] = True
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Connected, but couldn't read the sheet (likely a sharing/permissions issue): {e}"
        return result

    try:
        # Real-world-equivalent test: append a row (same operation the app actually
        # uses), confirm it landed, then remove it. Avoids any grid-size assumptions.
        existing_row_count = len(sheet.get_all_values())
        sheet.append_row(["__diagnostic_check__"])
        sheet.delete_rows(existing_row_count + 1)
        result["can_write"] = True
    except Exception as e:  # noqa: BLE001
        result["error"] = f"Connected and can read, but can't write (likely the service account only has Viewer access, not Editor): {e}"
        return result

    return result


def fetch_all_records() -> list[dict]:
    if not SHEETS_CONFIGURED:
        return []
    try:
        sheet = get_gsheet()
        return sheet.get_all_records()
    except Exception:
        return []


def fetch_records_for_code(code: str) -> list[dict]:
    target = code.strip().upper()
    records = [r for r in fetch_all_records() if str(r.get("Unique_Code", "")).strip().upper() == target]

    def _sub_no(r):
        try:
            return int(r.get("Submission_No", 0) or 0)
        except (TypeError, ValueError):
            return 0

    records.sort(key=_sub_no)
    return records


def generate_unique_code() -> str:
    existing = {str(r.get("Unique_Code", "")) for r in fetch_all_records()}
    while True:
        code = "ASP-" + "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if code not in existing:
            return code


def make_excel_bytes(rows: list[dict]) -> bytes:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "AspireAI"
    if rows:
        headers = list(rows[0].keys())
        ws.append(headers)
        for r in rows:
            ws.append([r.get(h, "") for h in headers])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


# ----------------------------------------------------------------------------
# Wizard step definitions
# ----------------------------------------------------------------------------
# Each step: dict with "kind" in {"select", "branch", "dynamic_select", "likert"}

DEMO_STEPS = [{"kind": "select", "field": f, "label": DEMOGRAPHIC_LABELS[f]} for f in SIMPLE_DEMO_FIELDS[:8]]
DEMO_STEPS.append({
    "kind": "branch", "field": "_pursuing", "label": "Are you currently pursuing:",
    "options": ["Graduation (Undergraduate)", "Post Graduation"],
})
DEMO_STEPS.append({"kind": "dynamic_select", "field": "_ug_pg"})
DEMO_STEPS += [{"kind": "select", "field": f, "label": DEMOGRAPHIC_LABELS[f]} for f in SIMPLE_DEMO_FIELDS[8:]]


def build_psych_steps():
    steps = []
    for factor, questions in psychometric_cols.items():
        for q in questions:
            clean_q = q.split("[", 1)[1].rstrip("]") if "[" in q else q
            steps.append({"kind": "likert", "field": q, "factor": factor, "label": clean_q})
    return steps


PSYCH_STEPS = build_psych_steps()
NEW_USER_STEPS = DEMO_STEPS + PSYCH_STEPS
RETURNING_USER_STEPS = PSYCH_STEPS


def render_step_widget(step: dict, answers: dict, widget_key: str):
    """Render the widget for one step and return its current value (or None)."""
    if step["kind"] == "select":
        field = step["field"]
        opts = list(demo_options[field].keys())
        return st.selectbox(step["label"], opts, index=None, placeholder="Select one...", key=widget_key)

    if step["kind"] == "branch":
        return st.radio(step["label"], step["options"], index=None, key=widget_key)

    if step["kind"] == "dynamic_select":
        pursuing = answers.get("_pursuing")
        if pursuing == "Post Graduation":
            label = "Which postgraduate program?"
            opts = list(POSTGRAD_GROUPS.keys())
        else:
            label = "Which undergraduate program?"
            opts = list(UNDERGRAD_GROUPS.keys())
        return st.selectbox(label, opts, index=None, placeholder="Select one...", key=widget_key)

    if step["kind"] == "likert":
        return st.radio(step["label"], LIKERT_OPTIONS, index=None, horizontal=True, key=widget_key)

    return None


def render_wizard(steps: list, mode: str, on_complete):
    """Generic one-question-at-a-time wizard. Calls on_complete(answers) once the last step is submitted."""
    step_key = f"{mode}_step"
    answers_key = f"{mode}_answers"
    st.session_state.setdefault(step_key, 0)
    st.session_state.setdefault(answers_key, {})

    step_idx = st.session_state[step_key]
    answers = st.session_state[answers_key]
    total = len(steps)

    st.progress((step_idx + 1) / total)
    st.caption(f"Question {step_idx + 1} of {total}")

    if st.button("🔄 Restart this form", key=f"{mode}_restart"):
        st.session_state[step_key] = 0
        st.session_state[answers_key] = {}
        st.rerun()

    step = steps[step_idx]
    widget_key = f"{mode}_w_{step_idx}_{step['field']}"
    value = render_step_widget(step, answers, widget_key)

    col_back, col_next = st.columns([1, 1])
    with col_back:
        if step_idx > 0:
            if st.button("← Back", key=f"{mode}_back_{step_idx}", use_container_width=True):
                st.session_state[step_key] -= 1
                st.rerun()
    with col_next:
        label = "Submit ✅" if step_idx == total - 1 else "Next →"
        if st.button(label, key=f"{mode}_next_{step_idx}", type="primary", use_container_width=True):
            if value is None:
                st.warning("Please answer this question before continuing — all questions are required.")
            else:
                answers[step["field"]] = value
                if step_idx < total - 1:
                    st.session_state[step_key] += 1
                    st.rerun()
                else:
                    on_complete(answers)


# ----------------------------------------------------------------------------
# Prediction logic (shared)
# ----------------------------------------------------------------------------

def resolve_demographics(answers: dict) -> dict:
    """Turn wizard answers into {field: raw_encoder_string} for all 13 demographic fields."""
    demo_raw = {}
    for field in SIMPLE_DEMO_FIELDS:
        display_choice = answers[field]
        demo_raw[field] = demo_options[field][display_choice]

    pursuing = answers["_pursuing"]
    ug_pg_choice = answers["_ug_pg"]
    if pursuing == "Post Graduation":
        demo_raw["Postgraduate"] = POSTGRAD_GROUPS[ug_pg_choice]
        demo_raw["Undergraduate"] = NOT_APPLICABLE_RAW
    else:
        demo_raw["Undergraduate"] = UNDERGRAD_GROUPS[ug_pg_choice]
        demo_raw["Postgraduate"] = NOT_APPLICABLE_RAW
    demo_raw["_pursuing_display"] = pursuing
    return demo_raw


def compute_prediction(demo_raw: dict, likert_answers: dict) -> dict:
    row = {}
    for field in feature_cols:
        if field in demo_raw:
            row[field] = label_encoders[field].transform([demo_raw[field]])[0]

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
    confidence = float(probabilities[prediction])

    normalized_intensity = {
        f: factor_scores[f] / (5 * len(psychometric_cols[f])) for f in factor_scores
    }
    ranked_factors = sorted(normalized_intensity, key=normalized_intensity.get, reverse=True)
    elevated_factors = [f for f in ranked_factors if normalized_intensity[f] >= HIGH_FACTOR_INTENSITY_THRESHOLD]

    return {
        "factor_scores": factor_scores,
        "total_score": total_score,
        "predicted_label": predicted_label,
        "probabilities": probabilities,
        "confidence": confidence,
        "normalized_intensity": normalized_intensity,
        "ranked_factors": ranked_factors,
        "elevated_factors": elevated_factors,
    }


def render_prediction_results(results: dict):
    predicted_label = results["predicted_label"]
    factor_scores = results["factor_scores"]
    probabilities = results["probabilities"]
    total_score = results["total_score"]
    confidence = results["confidence"]
    ranked_factors = results["ranked_factors"]
    elevated_factors = results["elevated_factors"]
    normalized_intensity = results["normalized_intensity"]

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
                Model confidence: <b>{confidence*100:.1f}%</b> &nbsp;·&nbsp;
                Most influencing factor: <b>{FACTOR_INTERVENTIONS[ranked_factors[0]]['title']}</b>
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
        fig_prob.update_layout(xaxis_title="Probability (%)", xaxis_range=[0, 100], height=320,
                                margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_prob, use_container_width=True)

    with col_b:
        st.markdown("**Contribution of each factor**")
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
        fig_factors.update_layout(xaxis_title="Sub-score", height=320, margin=dict(l=10, r=10, t=10, b=10))
        st.plotly_chart(fig_factors, use_container_width=True)

    st.caption(
        "Sub-scores are the sum of your Likert responses (1–5) within each dimension. "
        "Higher scores indicate greater self-reported stress in that dimension."
    )

    st.divider()
    st.subheader("Recommended next steps")

    for tip in CATEGORY_INTERVENTIONS[predicted_label]:
        st.markdown(f"- {tip}")

    show_media_for(predicted_label)

    if elevated_factors and predicted_label in ("Very Low Stress", "Low Stress"):
        elevated_titles = ", ".join(FACTOR_INTERVENTIONS[f]["title"] for f in elevated_factors)
        st.info(
            f"Your overall predicted stress level is **{predicted_label}**, but "
            f"**{elevated_titles}** scored notably high on its own. Overall stress being low "
            "doesn't cancel out a specific area that's genuinely weighing on you — it's worth "
            "looking at the section(s) below flagged 🔺 even if the general picture looks fine."
        )

    st.markdown("**Your factors, ranked from most to least affected:**")
    for rank, factor in enumerate(ranked_factors, start=1):
        pct = normalized_intensity[factor] * 100
        title = FACTOR_INTERVENTIONS[factor]["title"]
        flag = " 🔺" if factor in elevated_factors else ""
        with st.expander(f"{rank}. {title} — {pct:.0f}% intensity{flag}",
                          expanded=(rank == 1 or factor in elevated_factors)):
            for tip in FACTOR_INTERVENTIONS[factor]["tips"]:
                st.markdown(f"- {tip}")
            show_media_for(factor)

    if len(elevated_factors) == 2:
        pair_insight = PAIR_INTERVENTIONS.get(frozenset(elevated_factors))
        if pair_insight:
            st.markdown("**How your elevated factors interact:**")
            st.info(pair_insight)
    elif len(elevated_factors) >= 3:
        elevated_titles = ", ".join(FACTOR_INTERVENTIONS[f]["title"] for f in elevated_factors)
        st.markdown("**Multiple areas elevated at once:**")
        st.warning(
            f"You have {len(elevated_factors)} dimensions elevated together ({elevated_titles}). "
            "Trying to fix everything simultaneously usually backfires — pick whichever one "
            "feels most within your control right now and start there. Improvement in one "
            "area often eases the others somewhat, especially if they're related."
        )

    if predicted_label in ("Moderate Stress", "High Stress", "Very High Stress") or "FE" in elevated_factors:
        st.markdown("**Try a guided breathing exercise**")
        st.caption("Box breathing: 4 seconds in, 4 seconds hold, 4 seconds out, 4 seconds hold.")
        show_breathing_exercise()

    if predicted_label in ("High Stress", "Very High Stress"):
        st.warning(
            "If you're in emotional distress or having thoughts of self-harm, please reach out "
            "to a mental health professional or a crisis line in your area right away — you don't "
            "have to handle this alone."
        )


def render_comparison(prev: dict, results: dict):
    st.divider()
    st.subheader("How this compares to your last assessment")

    prev_total = float(prev.get("Total_Score", 0) or 0)
    new_total = results["total_score"]
    total_delta = new_total - prev_total
    pct_change = (total_delta / prev_total * 100) if prev_total else 0.0

    prev_category = prev.get("Predicted_Category", "")
    new_category = results["predicted_label"]
    prev_rank = CLASS_ORDER.index(prev_category) if prev_category in CLASS_ORDER else None
    new_rank = CLASS_ORDER.index(new_category)

    if prev_rank is not None and new_rank < prev_rank:
        verdict = "✅ Improved — your predicted stress category moved down."
        verdict_type = "success"
    elif prev_rank is not None and new_rank > prev_rank:
        verdict = "⚠️ Category moved up — worth checking in on what's changed."
        verdict_type = "warning"
    elif pct_change <= -10:
        verdict = "✅ Total psychometric score dropped meaningfully — intervention appears to be helping."
        verdict_type = "success"
    elif pct_change >= 10:
        verdict = "⚠️ Total psychometric score increased — consider revisiting the approach or seeking additional support."
        verdict_type = "warning"
    else:
        verdict = "➖ Roughly stable — no strong change in either direction since last time."
        verdict_type = "info"

    col1, col2, col3 = st.columns(3)
    col1.metric("Previous category", prev_category or "—")
    col2.metric("Current category", new_category)
    col3.metric("Total score", f"{new_total:.0f}", delta=f"{total_delta:+.0f} ({pct_change:+.1f}%)",
                delta_color="inverse")

    getattr(st, verdict_type)(verdict)

    st.markdown("**Per-factor change since last assessment:**")
    factor_rows = []
    for f in FACTORS:
        prev_score = float(prev.get(f"{f}_Score", 0) or 0)
        new_score = results["factor_scores"][f]
        factor_rows.append((FACTOR_NAMES[f], prev_score, new_score, new_score - prev_score))

    fig = go.Figure()
    fig.add_trace(go.Bar(name="Previous", y=[r[0] for r in factor_rows], x=[r[1] for r in factor_rows],
                          orientation="h", marker_color="#b0bec5"))
    fig.add_trace(go.Bar(name="Current", y=[r[0] for r in factor_rows], x=[r[2] for r in factor_rows],
                          orientation="h", marker_color="#5c6bc0"))
    fig.update_layout(barmode="group", height=320, margin=dict(l=10, r=10, t=30, b=10),
                       legend=dict(orientation="h", yanchor="bottom", y=1.02))
    st.plotly_chart(fig, use_container_width=True)

    for title, prev_s, new_s, delta in factor_rows:
        direction = "increased" if delta > 0 else ("decreased" if delta < 0 else "stayed the same")
        st.caption(f"- **{title}**: {prev_s:.0f} → {new_s:.0f} ({direction}, {delta:+.0f})")


# ----------------------------------------------------------------------------
# Session state / navigation
# ----------------------------------------------------------------------------

st.session_state.setdefault("page", "welcome")


def goto(page: str):
    st.session_state["page"] = page
    st.rerun()


# ----------------------------------------------------------------------------
# Page: Welcome
# ----------------------------------------------------------------------------

def render_welcome():
    st.title("🧠 DOAST-AI")
    st.caption(
        "A validated psychometric screening tool for students aged 18–25. "
        "Answer honestly — there are no right or wrong answers."
    )
    with st.expander("About this tool", expanded=False):
        st.markdown(
            """
This tool estimates an academic stress category from **5 validated psychometric
dimensions** — Personal Inadequacy, Interaction with Peers & Teachers, Fear of
Examination, Inadequate Facilities at College, and Parental Expectations &
Socio-Economic Status — combined with basic demographic information.

**This is a research/screening tool, not a clinical diagnosis.** If you are
struggling with stress, anxiety, or your mental health, please reach out to a
counselor, doctor, or a trusted person in your life.
            """
        )

    if not SHEETS_CONFIGURED:
        st.warning(
            "Note: persistent storage isn't configured for this app yet, so unique codes "
            "won't be retrievable in a future session. New assessments still work, but the "
            "'Returning User' comparison feature needs Google Sheets set up first."
        )

    with st.expander("🔧 Connection diagnostics (Google Sheets)", expanded=False):
        if st.button("Run diagnostics"):
            diag = run_sheets_diagnostics()
            st.write("gspread/google-auth installed:", "✅" if diag["gspread_installed"] else "❌")
            st.write("Secrets has `gcp_service_account`:", "✅" if diag["secrets_has_service_account"] else "❌")
            st.write("Secrets has `sheet_id`:", "✅" if diag["secrets_has_sheet_id"] else "❌")
            if diag["service_account_email"]:
                st.write("Service account email:", f"`{diag['service_account_email']}`")
            st.write("Can authenticate & open sheet:", "✅" if diag["connected"] else "❌")
            st.write("Can read the sheet:", "✅" if diag["can_read"] else "❌")
            st.write("Can write to the sheet:", "✅" if diag["can_write"] else "❌")
            if diag["error"]:
                st.error(diag["error"])
            elif diag["can_write"]:
                st.success("Everything checks out — Google Sheets is fully connected.")

    st.divider()
    st.subheader("Let's get started")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🆕 New Assessment**")
        st.caption("First time here — fill out the full questionnaire and get a unique code to track progress.")
        if st.button("Start New Assessment", use_container_width=True, type="primary"):
            goto("new_wizard")
    with col2:
        st.markdown("**🔁 Returning User**")
        st.caption("Already have a code from a previous assessment — retake just the questionnaire and compare.")
        if st.button("I Have a Code", use_container_width=True):
            goto("return_code")


# ----------------------------------------------------------------------------
# Page: New assessment wizard
# ----------------------------------------------------------------------------

def render_new_wizard():
    st.title("🆕 New Assessment")
    if st.button("← Back to start"):
        goto("welcome")
    st.caption("Answer every question — demographics first, then the questionnaire. All fields are required.")

    def on_complete(answers):
        demo_raw = resolve_demographics(answers)
        likert_answers = {q["field"]: answers[q["field"]] for q in PSYCH_STEPS}
        results = compute_prediction(demo_raw, likert_answers)
        code = generate_unique_code()

        sheet_row = {
            "Unique_Code": code, "Submission_No": 1,
            "Timestamp_UTC": dt.datetime.utcnow().isoformat(timespec="seconds"),
            "Submission_Type": "Baseline",
            "Pursuing": demo_raw["_pursuing_display"],
        }
        for f in SIMPLE_DEMO_FIELDS + ["Undergraduate", "Postgraduate"]:
            sheet_row[f] = demo_raw[f]
        for f in FACTORS:
            sheet_row[f"{f}_Score"] = results["factor_scores"][f]
        sheet_row["Total_Score"] = results["total_score"]
        sheet_row["Predicted_Category"] = results["predicted_label"]
        sheet_row["Confidence"] = round(results["confidence"], 4)

        saved, err = log_response(sheet_row)

        st.session_state["last_code"] = code
        st.session_state["last_results"] = results
        st.session_state["last_sheet_row"] = sheet_row
        st.session_state["last_saved"] = saved
        st.session_state["last_save_error"] = err
        goto("new_results")

    render_wizard(NEW_USER_STEPS, mode="new", on_complete=on_complete)


def render_new_results():
    code = st.session_state.get("last_code")
    results = st.session_state.get("last_results")
    sheet_row = st.session_state.get("last_sheet_row")
    saved = st.session_state.get("last_saved")

    if not results:
        goto("welcome")
        return

    st.title("🆕 New Assessment — Results")

    st.markdown(
        f"""
        <div style="padding:1rem 1.5rem;border-radius:0.6rem;background:#e3f2fd;
                    border:1px solid #90caf9;margin-bottom:0.5rem;">
            <div style="font-size:0.9rem;color:#555;">Your unique code — save this to track your progress later</div>
            <div style="font-size:1.6rem;font-weight:700;color:#1565c0;letter-spacing:1px;">{code}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if saved:
        st.caption("✅ Your response has been saved. Use this code next time to compare your progress.")
    elif SHEETS_CONFIGURED:
        st.caption("⚠️ Couldn't save to persistent storage — this code won't be retrievable later.")
        err = st.session_state.get("last_save_error")
        if err and err != "not_configured":
            with st.expander("Why did this fail?"):
                st.code(err)
    else:
        st.caption("⚠️ Persistent storage isn't configured — this code won't be retrievable in a future session.")

    excel_bytes = make_excel_bytes([sheet_row])
    st.download_button(
        "⬇️ Download your response as Excel",
        data=excel_bytes,
        file_name=f"AspireAI_{code}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    render_prediction_results(results)

    st.divider()
    if st.button("Start Over", use_container_width=True):
        for k in ("new_step", "new_answers", "last_code", "last_results", "last_sheet_row", "last_saved"):
            st.session_state.pop(k, None)
        goto("welcome")


# ----------------------------------------------------------------------------
# Page: Returning user
# ----------------------------------------------------------------------------

def render_return_code_entry():
    st.title("🔁 Returning User")
    if st.button("← Back to start"):
        goto("welcome")

    if not SHEETS_CONFIGURED:
        st.error(
            "Persistent storage isn't configured for this app, so previous codes can't be "
            "looked up. Ask the app owner to complete the Google Sheets setup."
        )
        return

    code = st.text_input("Enter your unique code (e.g. ASP-XXXXXX)")
    if st.button("Look Up", type="primary"):
        records = fetch_records_for_code(code.strip())
        if not records:
            st.error("No submissions found for that code. Double-check it, or start a New Assessment.")
        else:
            st.session_state["return_code"] = code.strip()
            st.session_state["return_records"] = records
            goto("return_wizard")


def render_return_wizard():
    code = st.session_state.get("return_code")
    records = st.session_state.get("return_records")
    if not records:
        goto("return_code")
        return

    st.title("🔁 Returning User")
    st.caption(f"Code: **{code}** · Previous submissions: {len(records)}")
    if st.button("← Back to start"):
        goto("welcome")
    st.caption("Just the questionnaire this time — your demographics are already on file.")

    def on_complete(answers):
        baseline = records[0]
        demo_raw = {f: baseline.get(f, NOT_APPLICABLE_RAW) for f in SIMPLE_DEMO_FIELDS}
        demo_raw["Undergraduate"] = baseline.get("Undergraduate", NOT_APPLICABLE_RAW)
        demo_raw["Postgraduate"] = baseline.get("Postgraduate", NOT_APPLICABLE_RAW)

        likert_answers = {q["field"]: answers[q["field"]] for q in PSYCH_STEPS}
        results = compute_prediction(demo_raw, likert_answers)

        submission_no = len(records) + 1
        sheet_row = {
            "Unique_Code": code, "Submission_No": submission_no,
            "Timestamp_UTC": dt.datetime.utcnow().isoformat(timespec="seconds"),
            "Submission_Type": "Follow-up",
            "Pursuing": baseline.get("Pursuing", ""),
        }
        for f in SIMPLE_DEMO_FIELDS + ["Undergraduate", "Postgraduate"]:
            sheet_row[f] = demo_raw[f]
        for f in FACTORS:
            sheet_row[f"{f}_Score"] = results["factor_scores"][f]
        sheet_row["Total_Score"] = results["total_score"]
        sheet_row["Predicted_Category"] = results["predicted_label"]
        sheet_row["Confidence"] = round(results["confidence"], 4)

        saved, err = log_response(sheet_row)

        st.session_state["last_results"] = results
        st.session_state["last_sheet_row"] = sheet_row
        st.session_state["last_saved"] = saved
        st.session_state["last_save_error"] = err
        st.session_state["last_prev"] = records[-1]  # most recent prior submission
        st.session_state["last_all_rows"] = records + [sheet_row]
        goto("return_results")

    render_wizard(RETURNING_USER_STEPS, mode="return", on_complete=on_complete)


def render_return_results():
    results = st.session_state.get("last_results")
    prev = st.session_state.get("last_prev")
    sheet_row = st.session_state.get("last_sheet_row")
    saved = st.session_state.get("last_saved")
    all_rows = st.session_state.get("last_all_rows", [])
    code = st.session_state.get("return_code")

    if not results:
        goto("welcome")
        return

    st.title("🔁 Returning User — Results")
    st.caption(f"Code: **{code}** · Submission #{sheet_row['Submission_No']}")

    if saved:
        st.caption("✅ This follow-up has been saved.")
    else:
        st.caption("⚠️ Couldn't save this follow-up to persistent storage.")
        err = st.session_state.get("last_save_error")
        if err and err != "not_configured":
            with st.expander("Why did this fail?"):
                st.code(err)

    excel_bytes = make_excel_bytes(all_rows)
    st.download_button(
        "⬇️ Download all your responses as Excel",
        data=excel_bytes,
        file_name=f"AspireAI_{code}_history.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        use_container_width=True,
    )

    render_comparison(prev, results)
    render_prediction_results(results)

    st.divider()
    if st.button("Start Over", use_container_width=True):
        for k in ("return_step", "return_answers", "return_code", "return_records",
                  "last_results", "last_sheet_row", "last_saved", "last_prev", "last_all_rows"):
            st.session_state.pop(k, None)
        goto("welcome")


# ----------------------------------------------------------------------------
# Router
# ----------------------------------------------------------------------------

PAGES = {
    "welcome": render_welcome,
    "new_wizard": render_new_wizard,
    "new_results": render_new_results,
    "return_code": render_return_code_entry,
    "return_wizard": render_return_wizard,
    "return_results": render_return_results,
}

PAGES.get(st.session_state["page"], render_welcome)()
