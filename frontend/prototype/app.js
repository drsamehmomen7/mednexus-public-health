// ---------- Report type selection ----------
const reportCards = document.querySelectorAll(".report-card");
const summaryText = document.getElementById("summary-text");

let selectedType = "notifiable";
let inputMode = "paste";
// Tracks which pasted text auto-detection has already run (and been
// shown to the reviewer) for, so a second click on unchanged text always
// proceeds to extraction instead of re-blocking on the same suggestion —
// see the extractBtn handler below.
let lastDetectedText = null;
// Whether ANY extract call (single-report or batch) has completed
// successfully yet on this page load — the backend loads its GLiNER
// model once per process and reuses it (see ner_client.py), so the
// first extraction call after a fresh backend start takes ~30s
// (measured directly against the real backend) while every one after
// it is under a second. Read before each extract call, set true right
// after it succeeds — by both the single-report flow and the batch
// orchestration below, since either one can be what actually warms up
// the model first.
let hasWarmedExtractor = false;

const typeLabels = {
  notifiable: "Notifiable Disease",
  immunization: "Immunization",
  laboratory: "Laboratory",
  syndromic: "Syndromic",
  outbreak: "Outbreak / Cluster",
};

// Which report types actually have a working backend behind them. Only
// these two get real /extract and /save routes; everything else in the
// UI is a placeholder for a report type whose schema exists but whose
// extraction pipeline hasn't been built yet (see CURRENT_STATUS.md) — the
// card is still selectable (so the full report-type lineup is visible),
// it just shows an honest "not built yet" message instead of silently
// running the wrong pipeline against it.
const ENDPOINTS = {
  notifiable: {
    extract: "/reports/notifiable-disease/extract",
    save: "/reports/notifiable-disease/save",
    batches: "/reports/notifiable-disease/batches",
    savePayloadKey: "case",
    dashboard: "dashboard.html",
  },
  immunization: {
    extract: "/reports/immunization/extract",
    save: "/reports/immunization/save",
    batches: "/reports/immunization/batches",
    savePayloadKey: "record",
    dashboard: "immunization-dashboard.html",
  },
  laboratory: {
    extract: "/reports/laboratory/extract",
    save: "/reports/laboratory/save",
    batches: "/reports/laboratory/batches",
    savePayloadKey: "report",
    dashboard: "laboratory-dashboard.html",
  },
};

// Per-type field type map, so the Save step converts each edited text
// input back to the right JSON type instead of sending everything as a
// string. Only fields that need a NON-string type are listed — anything
// else passes through as-is (matches how enum fields like
// diagnosis_status/patient_sex/route/adverse_event_severity are already
// handled: the schema validates the string value, no JS-side conversion
// needed for those).
const FIELD_TYPES = {
  notifiable: {
    lab_confirmed: "bool",
    patient_age: "int",
  },
  immunization: {
    dose_number: "int",
    patient_age: "int",
    patient_age_months: "int",
    adverse_event_reported: "bool",
  },
  laboratory: {
    patient_age: "int",
  },
};

// Which extracted field each report type's terminology-code preview watches, and how to label and
// describe it. Config only — holds no lookup logic itself; GET /terminology/preview
// (services/vocabularies.py) is the one place that decides what a value actually resolves to, and
// it's the SAME lookup the save endpoints already use — this block never duplicates it.
const TERMINOLOGY_PREVIEW = {
  notifiable: { field: "disease_name", label: "ICD-10 code", noun: "disease name" },
  immunization: { field: "vaccine_name", label: "CVX code", noun: "vaccine name" },
  laboratory: { field: "test_name", label: "LOINC code", noun: "test name" },
};

// ---------- Shared field-table rendering + edit collection ----------
// Used by BOTH the single-report flow (extractBtn's handler, below) and
// every batch review card (Milestone 4) — one implementation, not two.
// Behavior is unchanged from what used to be inline in extractBtn's
// handler; this is a pure extraction, not a rewrite.

// fieldTypes is accepted for parity with collectEditedRecord's signature
// and reserved for future per-type widgets (e.g. a checkbox for a bool
// field) — today every field still renders as a plain text input,
// exactly as before; the type only matters when reading edits back out.
//
// type and previewIdSuffix drive the terminology-code preview block appended after the table (see
// TERMINOLOGY_PREVIEW above). previewIdSuffix defaults to "" for the single-report flow's one
// instance; a Batch Upload card will pass its own item id so multiple cards' previews stay
// independent DOM nodes (Milestone 3 — not built yet, this parameter just avoids a second
// signature change to this shared function when it is). Passing a type with no TERMINOLOGY_PREVIEW
// entry (or none at all) simply omits the block.
function renderFieldsTable(fields, confidence, fieldTypes, type, previewIdSuffix = "") {
  const rows = Object.entries(fields)
    .filter(([, value]) => value !== null && value !== undefined)
    .map(([key, value]) => {
      const conf = confidence[key];
      let badge = "";

      if (conf) {
        if (conf.source === "rule_based") {
          badge = `<span style="font-size:11px; padding:2px 8px; border-radius:999px; background:#eef1f4; color:#57685e;">rule-based</span>`;
        } else if (conf.source === "gazetteer") {
          badge = `<span style="font-size:11px; padding:2px 8px; border-radius:999px; background:#eef6e8; color:#4d7a2f;">gazetteer match</span>`;
        } else if (conf.score === null) {
          badge = `<span style="font-size:11px; padding:2px 8px; border-radius:999px; background:#fdecea; color:#8a3a1f;">not found</span>`;
        } else {
          const pct = Math.round(conf.score * 100);
          // Low confidence gets a visibly different color — this is the
          // signal a reviewer should not skip past without a second look.
          const low = conf.score < 0.6;
          const bg = low ? "#fdecea" : "#eef6e8";
          const fg = low ? "#8a3a1f" : "#4d7a2f";
          badge = `<span style="font-size:11px; padding:2px 8px; border-radius:999px; background:${bg}; color:${fg};">${pct}% confidence</span>`;
        }
      }

      const isLongText = key === "source_excerpt";
      const fieldInput = isLongText
        ? `<span style="color:var(--ink-soft);">${value}</span>`
        : `<input type="text" value="${String(value).replace(/"/g, "&quot;")}" data-field="${key}"
             style="width:100%; border:1px solid var(--border); border-radius:6px; padding:4px 8px; font-size:13px; font-family:inherit;" />`;

      return `
        <tr>
          <td style="padding:6px 12px 6px 0; color:var(--ink-soft); white-space:nowrap; vertical-align:top;">${key}</td>
          <td style="padding:6px 0; width:100%;">${fieldInput}</td>
          <td style="padding:6px 0 6px 12px; white-space:nowrap;">${badge}</td>
        </tr>
      `;
    })
    .join("");

  const previewConfig = TERMINOLOGY_PREVIEW[type];
  const previewBlock = previewConfig
    ? renderTerminologyPreviewPlaceholder(previewConfig, `terminology-preview${previewIdSuffix}`)
    : "";

  return `
    <table style="width:100%; text-align:left; font-size:13px; border-collapse:collapse;">
      ${rows}
    </table>
    ${previewBlock}
    <p style="margin:12px 0 0; font-size:12px; color:var(--ink-soft);">
      Fields are editable. Anything below 60% confidence or marked
      "not found" should be checked against the original text before use.
    </p>
  `;
}

// The terminology-code preview: a separate block below the field table, not another row inside
// it — deliberately, so it never reads as "another extracted field" the way every row in that
// table does (real, editable, badge-confirmed). Starts in a neutral "Checking…" state; the actual
// value is filled in by refreshTerminologyPreview() right after this HTML is inserted, and again
// on every edit of the field it watches (see the delegated 'change' listeners near each caller).
function renderTerminologyPreviewPlaceholder(config, id) {
  return `
    <div id="${id}" style="margin-top:12px; padding:10px 12px; border:1px dashed var(--border);
         border-radius:8px; background:#f6f8f5; font-size:12.5px;">
      <div style="text-transform:uppercase; letter-spacing:0.04em; font-size:10.5px; color:var(--ink-soft); margin-bottom:4px;">
        Preview — not saved yet
      </div>
      <div data-preview-body>${_terminologyPreviewLine(config, "Checking…")}</div>
    </div>
  `;
}

function _terminologyPreviewLine(config, valueHtml) {
  return `<strong style="color:var(--ink); font-weight:600;">${config.label}:</strong> <span style="color:var(--ink-soft);">${valueHtml}</span>`;
}

// Builds the resolved-state body for a terminology preview, from a GET /terminology/preview
// response ({system, code, status, note, in_vocabulary}). The wording here is exactly what
// distinguishes a genuinely uncoded term (in_vocabulary true, code null — a real clinical
// decision, always paired with a note explaining it) from one that simply doesn't match anything
// in the vocabulary yet (in_vocabulary false, never has a note) — conflating those two would be
// actively misleading, not just imprecise; that distinction is the entire reason this exists.
function renderTerminologyPreviewResult(config, entry) {
  let valueHtml;
  if (entry.code) {
    valueHtml = entry.status ? `${entry.code} (${entry.status})` : entry.code;
  } else if (entry.in_vocabulary) {
    valueHtml = "Reviewed — none applies.";
  } else {
    valueHtml = "Not available yet for this wording.";
  }

  const noteHtml = entry.note
    ? `<p style="margin:6px 0 0; color:var(--ink-soft); line-height:1.4;">${entry.note}</p>`
    : "";

  return `${_terminologyPreviewLine(config, valueHtml)}${noteHtml}`;
}

function renderTerminologyPreviewError(config) {
  return _terminologyPreviewLine(config, "Couldn't check just now.");
}

// Fetches and fills in one terminology-code preview block. Called once right after the field
// table it belongs to is inserted — so the preview appears immediately, for the as-extracted
// value, not only after a first edit — and again by a delegated 'change' listener whenever the
// field it watches is edited. Purely advisory: whether this call is made, succeeds, or fails has
// zero effect on extraction, confidence, or save — save computes the real value itself,
// independently, every time, whether or not a preview was ever shown for it.
//
// The dataset.forValue check guards against a slow, now-superseded response clobbering a newer
// one: a second call (from a second edit) overwrites previewEl.dataset.forValue synchronously
// before its own fetch even starts, so when a slower first call's fetch finally resolves, it sees
// a value that no longer matches what IT was for, and discards itself instead of writing stale
// content over the newer result.
async function refreshTerminologyPreview(container, type, previewIdSuffix = "") {
  const config = TERMINOLOGY_PREVIEW[type];
  if (!config) return;

  const previewEl = document.getElementById(`terminology-preview${previewIdSuffix}`);
  const input = container.querySelector(`input[data-field="${config.field}"]`);
  const body = previewEl && previewEl.querySelector("[data-preview-body]");
  if (!body || !input) return;

  const value = input.value.trim();
  previewEl.dataset.forValue = value;
  body.innerHTML = _terminologyPreviewLine(config, "Checking…");

  try {
    const response = await fetch(
      `${API_BASE}/terminology/preview?report_type=${encodeURIComponent(type)}&value=${encodeURIComponent(value)}`
    );
    const entry = await response.json();
    if (previewEl.dataset.forValue !== value) return;
    body.innerHTML = renderTerminologyPreviewResult(config, entry);
  } catch (err) {
    if (previewEl.dataset.forValue !== value) return;
    body.innerHTML = renderTerminologyPreviewError(config);
  }
}

// container scopes the query to just this one review surface — the
// single-report flow passes resultArea; a batch card passes its own
// card element, so editing one card can never bleed into another's
// values when multiple cards are on the page at once (Milestone 4).
function collectEditedRecord(container, type, originalFields) {
  const editedRecord = { ...originalFields };
  const fieldTypes = FIELD_TYPES[type] || {};

  container.querySelectorAll('input[data-field]').forEach((input) => {
    const field = input.dataset.field;
    const value = input.value;
    const fieldType = fieldTypes[field];

    if (fieldType === "bool") {
      editedRecord[field] = value.trim().toLowerCase() === "true";
    } else if (fieldType === "int") {
      editedRecord[field] = value.trim() === "" ? null : parseInt(value, 10);
    } else {
      editedRecord[field] = value;
    }
  });

  return editedRecord;
}

// FastAPI's error `detail` is a plain string for most errors (e.g. the
// GLiNER-not-installed 503 on /extract), but a structured array of
// {type, loc, msg, ...} objects for Pydantic validation errors (422s,
// the realistic way a save fails — an edited field value the schema
// rejects). Interpolating that array directly into a template literal
// renders as "[object Object]"; this is what both save paths use
// instead. Discovered live while verifying Milestone 5's forced-failure
// case, and just as real a bug in the single-report flow, which uses
// the identical pattern and would have hit it the same way.
function formatSaveError(detail, fallback) {
  if (!detail) return fallback;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail.map((e) => {
      const field = Array.isArray(e.loc) ? e.loc[e.loc.length - 1] : null;
      return field ? `${field}: ${e.msg}` : e.msg;
    }).join("; ");
  }
  return fallback;
}

function updateSummary() {
  summaryText.textContent = `${typeLabels[selectedType]} · ${inputMode === "paste" ? "Text input" : "File upload"} · Local processing`;
}

reportCards.forEach((card) => {
  card.addEventListener("click", () => {
    reportCards.forEach((c) => c.setAttribute("aria-pressed", "false"));
    card.setAttribute("aria-pressed", "true");
    selectedType = card.dataset.type;
    updateSummary();
    resultArea.innerHTML = `<span class="placeholder-text">Extracted fields will appear here after processing.</span>`;
  });
});

// ---------- Input tabs ----------
const tabs = document.querySelectorAll(".tab");
const panels = document.querySelectorAll(".tab-panel");

tabs.forEach((tab) => {
  tab.addEventListener("click", () => {
    tabs.forEach((t) => t.classList.remove("active"));
    panels.forEach((p) => p.classList.remove("active"));
    tab.classList.add("active");
    document.querySelector(`.tab-panel[data-panel="${tab.dataset.tab}"]`).classList.add("active");
    inputMode = tab.dataset.tab;
    updateSummary();
  });
});

// ---------- Mode switch: Single report vs Batch upload ----------
// Only hides/shows the two panes; nothing inside either is reset.
const modeTabs = document.querySelectorAll(".mode-tab");

function setMode(mode) {
  modeTabs.forEach((t) => {
    const on = t.dataset.mode === mode;
    t.setAttribute("aria-pressed", String(on));
    document.getElementById(`mode-${t.dataset.mode}`).hidden = !on;
  });
  history.replaceState(null, "", mode === "batch" ? "#batch" : location.pathname + location.search);
}

modeTabs.forEach((t) => t.addEventListener("click", () => setMode(t.dataset.mode)));
if (location.hash === "#batch") setMode("batch");

// ---------- Extract button: calls the real backend ----------
const extractBtn = document.getElementById("extract-btn");
const resultArea = document.getElementById("result-area");
// Port 8002: local port convention reserves 8001 for MedNexus Main and
// 8002 for Public Health, so the two projects' backends never collide.
const API_BASE = "http://127.0.0.1:8002";

// Holds the most recent extraction so the Save button can send back
// original field types + the confidence report, merged with whatever the
// reviewer edited in the input boxes.
let lastFields = null;
let lastConfidence = null;

extractBtn.addEventListener("click", async () => {
  const reportText = document.querySelector('.tab-panel[data-panel="paste"] textarea').value.trim();

  if (!reportText) {
    resultArea.innerHTML = `<span class="placeholder-text">Paste some report text first.</span>`;
    return;
  }

  // Run the same auto-detection the upload path already runs, so a
  // report-type card left selected from a previous test can't silently
  // route this text through the wrong extractor. Only re-detects when
  // the pasted text has actually changed since the last time detection
  // ran (and was shown) for it — a click on unchanged text always
  // proceeds to extraction below, whether that's because the reviewer
  // accepted the auto-switch or deliberately picked a different card
  // themselves; either way that's their confirmed choice, not something
  // to keep re-litigating.
  if (reportText !== lastDetectedText) {
    lastDetectedText = reportText;
    try {
      const detectRes = await fetch(`${API_BASE}/reports/detect-type`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: reportText }),
      });
      const detectData = await detectRes.json();
      const detectedType = detectData.detected_type;
      const detectedLabel = TYPE_LABELS_FOR_DETECTION[detectedType];

      if (detectedLabel && detectedType !== selectedType) {
        selectReportCard(detectedType);
        resultArea.innerHTML = `
          <span class="placeholder-text">
            Detected: ${detectedLabel}. Selected automatically — pick a different
            card above if that's wrong, then Extract Report Data.
          </span>
        `;
        return;
      }
    } catch (err) {
      // Detection is a pre-check, not a hard requirement — if the
      // backend is unreachable, fall through and let the extract call
      // below report that clearly instead of failing silently here.
    }
  }

  const config = ENDPOINTS[selectedType];

  if (!config) {
    resultArea.innerHTML = `
      <span class="placeholder-text">
        ${typeLabels[selectedType]} extraction isn't built yet — schema exists,
        pipeline doesn't. Try Notifiable Disease or Immunization for now.
      </span>
    `;
    return;
  }

  resultArea.innerHTML = `<span class="placeholder-text">Extracting...</span>`;

  try {
    const response = await fetch(`${API_BASE}${config.extract}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: reportText }),
    });

    const data = await response.json();

    if (!response.ok) {
      // e.g. 503 when the GLiNER model isn't installed/downloaded yet
      resultArea.innerHTML = `
        <div style="width:100%; text-align:left; font-size:13px; color:#8a3a1f;">
          <strong>Extraction unavailable:</strong>
          <p style="margin:8px 0 0; white-space:pre-wrap;">${data.detail}</p>
        </div>
      `;
      return;
    }

    lastFields = data.extracted;
    lastConfidence = data.confidence || {};
    hasWarmedExtractor = true;

    resultArea.innerHTML = `
      <div style="width:100%;">
        ${renderFieldsTable(lastFields, lastConfidence, FIELD_TYPES[selectedType] || {}, selectedType)}
        <div style="margin-top:14px; padding-top:14px; border-top:1px solid var(--border);">
          <label for="batch-select" style="display:block; font-size:12px; color:var(--ink-soft); margin-bottom:5px;">
            Save to
          </label>
          <select id="batch-select" style="width:100%; max-width:320px; padding:8px 10px; font-size:13px;
                  border:1px solid var(--border); border-radius:8px; font-family:inherit;">
            <option value="">Original data (no batch)</option>
            <option value="__new__">+ New batch...</option>
          </select>
          <input id="batch-new-input" type="text" placeholder="Batch name, e.g. Farwaniya Q1 2026"
                 hidden style="width:100%; max-width:320px; margin-top:8px; padding:8px 10px; font-size:13px;
                 border:1px solid var(--border); border-radius:8px; font-family:inherit;" />
        </div>
        <button id="save-btn" class="btn-primary" style="margin-top:14px;">
          Save reviewed record
        </button>
        <div id="save-status" style="margin-top:8px; font-size:12px;"></div>
        <div id="save-cta" class="save-cta"></div>
      </div>
    `;

    populateBatchSelect();
    refreshTerminologyPreview(resultArea, selectedType);
    document.getElementById("save-btn").addEventListener("click", saveRecord);
  } catch (err) {
    resultArea.innerHTML = `
      <span class="placeholder-text">
        Could not reach the backend at ${API_BASE}. Is the server running
        (uvicorn app.main:app --reload)?
      </span>
    `;
  }
});

// Delegated (not attached per-render) so it survives resultArea's innerHTML being replaced by
// every new extraction — same reasoning as Batch Upload's own delegated 'change' listener on
// batchProgressGrid, further down. Recomputes on blur-with-a-real-change (the native 'change'
// event on a text input), not on every keystroke. A fresh extraction's first preview is handled
// separately, by the explicit refreshTerminologyPreview() call right above.
resultArea.addEventListener("change", (e) => {
  const config = TERMINOLOGY_PREVIEW[selectedType];
  if (config && e.target.matches(`input[data-field="${config.field}"]`)) {
    refreshTerminologyPreview(resultArea, selectedType);
  }
});

// ---------- Upload a document: parse, detect type, hand off to Extract ----------
const dropzone = document.getElementById("dropzone");
const fileInput = document.getElementById("file-input");
const uploadStatus = document.getElementById("upload-status");

const TYPE_LABELS_FOR_DETECTION = {
  notifiable: "Notifiable Disease",
  immunization: "Immunization",
  laboratory: "Laboratory",
  unknown: null,
};

function selectReportCard(type) {
  const card = document.querySelector(`.report-card[data-type="${type}"]`);
  if (!card) return;
  reportCards.forEach((c) => c.setAttribute("aria-pressed", "false"));
  card.setAttribute("aria-pressed", "true");
  selectedType = type;
  updateSummary();
}

function switchToTab(tabName) {
  tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
  panels.forEach((p) => p.classList.toggle("active", p.dataset.panel === tabName));
  inputMode = tabName;
  updateSummary();
}

async function handleUploadedFile(file) {
  uploadStatus.style.color = "var(--ink-soft)";
  uploadStatus.textContent = `Reading ${file.name}...`;

  const formData = new FormData();
  formData.append("file", file);

  try {
    const parseRes = await fetch(`${API_BASE}/reports/parse-document`, {
      method: "POST",
      body: formData,
    });
    const parseData = await parseRes.json();

    if (!parseRes.ok) {
      uploadStatus.style.color = "#8a3a1f";
      uploadStatus.textContent = parseData.detail || "Could not read that file.";
      return;
    }

    const extractedText = parseData.text;

    // Show the extracted text on the paste tab immediately — the person
    // should see exactly what MedNexus will work from, and can edit it,
    // before anything is classified or extracted.
    document.querySelector('.tab-panel[data-panel="paste"] textarea').value = extractedText;

    uploadStatus.textContent = "Detecting report type...";

    const detectRes = await fetch(`${API_BASE}/reports/detect-type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: extractedText }),
    });
    const detectData = await detectRes.json();
    const detectedType = detectData.detected_type;
    const detectedLabel = TYPE_LABELS_FOR_DETECTION[detectedType];

    switchToTab("paste");

    if (detectedLabel) {
      selectReportCard(detectedType);
      uploadStatus.style.color = "#4d7a2f";
      uploadStatus.textContent =
        `Detected: ${detectedLabel}. Selected automatically — pick a different ` +
        `card above if that's wrong, then Extract Report Data.`;
    } else {
      uploadStatus.style.color = "var(--ink-soft)";
      uploadStatus.textContent =
        "Couldn't confidently detect the report type — text loaded below. " +
        "Pick the right card above, then Extract Report Data.";
    }
  } catch (err) {
    uploadStatus.style.color = "#8a3a1f";
    uploadStatus.textContent = `Could not reach the backend at ${API_BASE}.`;
  }
}

dropzone.addEventListener("click", () => fileInput.click());

fileInput.addEventListener("change", () => {
  if (fileInput.files.length) handleUploadedFile(fileInput.files[0]);
});

["dragover", "dragenter"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "var(--brand-teal)";
  })
);
["dragleave", "drop"].forEach((evt) =>
  dropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    dropzone.style.borderColor = "";
  })
);
dropzone.addEventListener("drop", (e) => {
  const file = e.dataTransfer.files[0];
  if (file) handleUploadedFile(file);
});

// ---------- Save button: persists the (possibly edited) record ----------
// ---------- Shared batch-target picker plumbing ----------
// Used by BOTH the single-report flow's batch-select (one type's own
// batches) and the Batch Upload save step (Milestone 5, a union across
// all three types, since one batch of files can span all three tables).

// Fills an already-present <select> + its "+ New batch..." text input
// from a fetched {batch_label, record_count}[] list. Split out from the
// fetch itself so the union case (fetchAllBatchRecords below) can build
// one merged list and hand it to the exact same rendering logic a
// single type's list already used.
function populateBatchOptions(selectEl, newInputEl, batchRecords) {
  // Idempotent: the Batch Upload picker is rebuilt as the ticked reports change, so drop batches an earlier call listed.
  selectEl.querySelectorAll("option[data-batch]").forEach((o) => o.remove());
  batchRecords.forEach((b) => {
    const opt = document.createElement("option");
    opt.value = b.batch_label;
    opt.dataset.batch = "1";
    opt.textContent = `${b.batch_label} (${b.record_count})`;
    selectEl.insertBefore(opt, selectEl.querySelector('option[value="__new__"]'));
  });

  // Attached unconditionally (not inside the try/catch a caller might
  // wrap its fetch in) — the "+ New batch..." option must work even if
  // fetching the existing-batches list failed. Once per <select>.
  if (selectEl.dataset.newBatchWired) return;
  selectEl.dataset.newBatchWired = "1";
  selectEl.addEventListener("change", () => {
    newInputEl.hidden = selectEl.value !== "__new__";
    if (!newInputEl.hidden) newInputEl.focus();
  });
}

function getBatchLabelFrom(selectEl, newInputEl) {
  if (!selectEl) return null;
  if (selectEl.value === "__new__") {
    const name = newInputEl.value.trim();
    return name || null;
  }
  return selectEl.value || null;
}

// One type's batches, or [] on failure — never throws, so a caller can
// always safely spread/flat the result without its own try/catch.
async function fetchBatchRecords(type) {
  const config = ENDPOINTS[type];
  try {
    const res = await fetch(`${API_BASE}${config.batches}`);
    const data = await res.json();
    return data.batches || [];
  } catch (err) {
    return [];
  }
}

// Unions all three types' batch lists by batch_label, summing
// record_count — a mixed batch's save step needs to show "Farwaniya Q1
// 2026 (7)" meaning 7 records total across whichever tables actually
// have that label, not three separate same-named entries. Deliberately
// three parallel fetches to the EXISTING per-type endpoints rather than
// a new combined backend endpoint (see the Batch Upload plan). Each entry
// also records which report types the label has records for (`types`), so
// the save picker can be narrowed to batches relevant to what's being saved.
async function fetchAllBatchRecords() {
  const types = Object.keys(ENDPOINTS);
  const perType = await Promise.all(types.map(fetchBatchRecords));
  const merged = new Map();
  perType.forEach((batches, i) => batches.forEach((b) => {
    const existing = merged.get(b.batch_label);
    if (existing) {
      existing.record_count += b.record_count;
      existing.types.push(types[i]);
    } else {
      merged.set(b.batch_label, { batch_label: b.batch_label, record_count: b.record_count, types: [types[i]] });
    }
  }));
  return Array.from(merged.values());
}

async function populateBatchSelect() {
  const select = document.getElementById("batch-select");
  const newInput = document.getElementById("batch-new-input");
  const records = await fetchBatchRecords(selectedType);
  populateBatchOptions(select, newInput, records);
}

function currentBatchLabel() {
  return getBatchLabelFrom(document.getElementById("batch-select"), document.getElementById("batch-new-input"));
}

// Post-save "View <type> Dashboard" link; each dashboard reads ?batch= on first load. New tab so unsaved review work here isn't lost.
function dashboardLink(type, batchLabel) {
  const a = document.createElement("a");
  a.className = "btn-link";
  a.href = ENDPOINTS[type].dashboard + (batchLabel ? `?batch=${encodeURIComponent(batchLabel)}` : "");
  a.target = "_blank";
  a.rel = "noopener";
  a.textContent = `View ${typeLabels[type]} Dashboard`;
  return a;
}

async function saveRecord() {
  const savedType = selectedType;
  const config = ENDPOINTS[savedType];
  const statusEl = document.getElementById("save-status");
  const ctaEl = document.getElementById("save-cta");
  statusEl.textContent = "Saving...";
  statusEl.style.color = "var(--ink-soft)";
  ctaEl.replaceChildren();

  // Start from the last extracted values, then overlay whatever the
  // reviewer edited in the input boxes — this is what makes manual
  // correction actually take effect before saving, not just cosmetic.
  const editedRecord = collectEditedRecord(resultArea, selectedType, lastFields);

  try {
    const response = await fetch(`${API_BASE}${config.save}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        [config.savePayloadKey]: editedRecord,
        confidence: lastConfidence,
        batch_label: currentBatchLabel(),
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      statusEl.textContent = `Save failed: ${formatSaveError(data.detail, response.status)}`;
      statusEl.style.color = "#8a3a1f";
      return;
    }

    const batchLabel = currentBatchLabel();
    statusEl.textContent = batchLabel
      ? `Saved to batch "${batchLabel}".`
      : "Saved to the original (unbatched) data.";
    statusEl.style.color = "#4d7a2f";
    ctaEl.replaceChildren(dashboardLink(savedType, batchLabel));
  } catch (err) {
    statusEl.textContent = `Could not reach the backend at ${API_BASE}.`;
    statusEl.style.color = "#8a3a1f";
  }
}

// ---------- Batch Upload — Milestone 2: orchestration logic only -----------
// No dropzone, no review card grid, no save-all step yet — those are
// Milestones 3, 4, and 5. This proves the per-file sequential processing
// loop and per-file error isolation work for real, against the real
// backend, via the temporary diagnostic scaffold in index.html.

function makeBatchItem(file, index) {
  return {
    id: `${file.name}-${index}`,
    file,
    filename: file.name,
    // "queued" | "parsing" | "detecting" | "extracting" | "needs-type"
    // | "ready" | "error"
    status: "queued",
    detectedType: null,
    // Reviewer-editable via the needs-type mini-picker (Milestone 4).
    // Mirrors detectedType once known.
    selectedType: null,
    rawText: null,
    extractedFields: null,
    confidence: null,
    errorMessage: null,
    // Set by the error card's "Remove from batch" button (Milestone 4).
    // Milestone 5's save step must skip excluded items even if their
    // card element is gone from the DOM.
    excluded: false,
    // Save-step state (Milestone 5) — independent of `status` above,
    // which only tracks the extraction pipeline. A "ready" item can be
    // null (never attempted), "save-error" (attempted, failed — stays
    // reviewed and retryable), or "saved" (done, locked, never
    // re-attempted even if the reviewer clicks Save again).
    saveStatus: null,
    saveError: null,
    savedId: null,
    savedBatchLabel: null,
    timing: {
      parseSeconds: null,
      detectSeconds: null,
      extractSeconds: null,
      // Whether this file's extract call was expected to be the
      // ~30s cold-model-load one, or a warm (<1s) one — decided at the
      // moment the call started, from hasWarmedExtractor. Milestone 3's
      // progress UI reads this to show the right expectation per card
      // instead of one generic estimate for every file.
      extractWasCold: null,
    },
  };
}

// Runs extraction for one item whose text is already known — split out
// from processSingleBatchItem so a later milestone's manual type-picker
// (for a "needs-type" card) can call this directly once the reviewer
// sets item.selectedType by hand, without re-running parse/detect.
//
// onUpdate(item), when given, fires after every status change (not just
// once at the end) so a live progress UI can show "reading -> detecting
// -> extracting -> ready" as it actually happens, one card at a time.
async function extractBatchItem(item, onUpdate) {
  // Route through the SAME ENDPOINTS map the single-report flow uses —
  // never build the URL from the raw detected-type label directly. That
  // exact "notifiable" (detect-type's label) vs "notifiable-disease"
  // (the URL path segment) mismatch is what broke Milestone 1's
  // diagnostic script on its first run; ENDPOINTS is the one source of
  // truth for this translation, here and in the single-report flow alike.
  const config = ENDPOINTS[item.selectedType];
  if (!config) {
    item.status = "error";
    item.errorMessage = `${typeLabels[item.selectedType] || item.selectedType} extraction isn't built yet.`;
    onUpdate && onUpdate(item);
    return;
  }

  // Decided and recorded BEFORE the call starts, not after, so a
  // progress UI can show the right expectation ("loading the model" vs
  // "extracting") for the full duration of the wait, not just in
  // hindsight once it's already done.
  const wasCold = !hasWarmedExtractor;
  item.timing.extractWasCold = wasCold;
  item.status = "extracting";
  onUpdate && onUpdate(item);

  const extractStart = performance.now();
  try {
    const response = await fetch(`${API_BASE}${config.extract}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: item.rawText }),
    });
    const data = await response.json();

    if (!response.ok) {
      item.status = "error";
      item.errorMessage = data.detail || "Extraction failed.";
      return;
    }

    item.extractedFields = data.extracted;
    item.confidence = data.confidence || {};
    item.status = "ready";
    hasWarmedExtractor = true;
  } catch (err) {
    item.status = "error";
    item.errorMessage = `Could not reach the backend at ${API_BASE}.`;
  } finally {
    item.timing.extractSeconds = (performance.now() - extractStart) / 1000;
    onUpdate && onUpdate(item);
  }
}

// Runs the full parse -> detect -> (extract, unless the type is
// ambiguous) chain for one file. Never throws — every failure is
// recorded on the item itself so the caller's loop is never at risk of
// stopping partway through a batch because of one bad file. Fires
// onUpdate(item) after every status change, same reasoning as
// extractBatchItem above.
async function processSingleBatchItem(item, onUpdate) {
  item.status = "parsing";
  onUpdate && onUpdate(item);
  const parseStart = performance.now();
  try {
    const formData = new FormData();
    formData.append("file", item.file);
    const parseRes = await fetch(`${API_BASE}/reports/parse-document`, {
      method: "POST",
      body: formData,
    });
    const parseData = await parseRes.json();
    item.timing.parseSeconds = (performance.now() - parseStart) / 1000;

    if (!parseRes.ok) {
      item.status = "error";
      item.errorMessage = parseData.detail || "Could not read that file.";
      onUpdate && onUpdate(item);
      return;
    }
    item.rawText = parseData.text;
  } catch (err) {
    item.timing.parseSeconds = (performance.now() - parseStart) / 1000;
    item.status = "error";
    item.errorMessage = `Could not reach the backend at ${API_BASE}.`;
    onUpdate && onUpdate(item);
    return;
  }

  item.status = "detecting";
  onUpdate && onUpdate(item);
  const detectStart = performance.now();
  try {
    const detectRes = await fetch(`${API_BASE}/reports/detect-type`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ text: item.rawText }),
    });
    const detectData = await detectRes.json();
    item.timing.detectSeconds = (performance.now() - detectStart) / 1000;

    if (!detectRes.ok) {
      item.status = "error";
      item.errorMessage = detectData.detail || "Detection failed.";
      onUpdate && onUpdate(item);
      return;
    }
    item.detectedType = detectData.detected_type;
  } catch (err) {
    item.timing.detectSeconds = (performance.now() - detectStart) / 1000;
    item.status = "error";
    item.errorMessage = `Could not reach the backend at ${API_BASE}.`;
    onUpdate && onUpdate(item);
    return;
  }

  // Decision (approved in the Batch Upload plan): "unknown" blocks only
  // THIS file for manual type selection in a later milestone's UI — it
  // must not silently default to some guessed type, and must not stop
  // the rest of the batch from proceeding.
  if (item.detectedType === "unknown") {
    item.status = "needs-type";
    onUpdate && onUpdate(item);
    return;
  }

  item.selectedType = item.detectedType;
  await extractBatchItem(item, onUpdate);
}

// The orchestration loop: sequential on purpose (see Milestone 1's
// measured timing — a warm extract call is well under a second, so
// there is no throughput case for concurrency here, only added
// complexity and uncertain benefit given GLiNER's inference is
// CPU-bound). Each item is wrapped in its own try/catch on top of
// processSingleBatchItem's own internal handling, so even a genuinely
// unexpected bug in this code can never take down the rest of the batch.
//
// onUpdate(item, allItems), when given, fires on every status change of
// any item — allItems is the SAME array/objects being mutated in place,
// so a renderer can just redraw the whole grid from it each time rather
// than reconciling partial updates itself.
async function processBatchFiles(files, onUpdate) {
  const items = Array.from(files).map(makeBatchItem);
  const notify = (item) => onUpdate && onUpdate(item, items);

  for (const item of items) {
    notify(item); // initial "queued" render for every file, up front
    try {
      await processSingleBatchItem(item, notify);
    } catch (err) {
      item.status = "error";
      item.errorMessage = `Unexpected error: ${err.message}`;
      notify(item);
    }
  }

  return items;
}

// ---------- Batch Upload: file selection + live progress (Milestone 3) ----
// Real dropzone + multi-select, replacing Milestone 2's plain diagnostic
// input, wired to the same processBatchFiles()/makeBatchItem() functions
// above (unchanged in behavior, just now driving real UI instead of a
// console/plain-text dump). Still no editable review card grid — that's
// Milestone 4; a "ready" card here just announces itself as ready.

const BATCH_FILE_LIMIT = 10;

const batchDropzone = document.getElementById("batch-dropzone");
const batchFileInput = document.getElementById("batch-file-input");
const batchSelectionSummary = document.getElementById("batch-selection-summary");
const batchSelectionList = document.getElementById("batch-selection-list");
const batchStartBtn = document.getElementById("batch-start-btn");
const batchOverallProgress = document.getElementById("batch-overall-progress");
const batchProgressGrid = document.getElementById("batch-progress-grid");

let pendingBatchFiles = [];

// Accumulates onto whatever is already pending, so a second Browse/drop ADDS to the first
// selection instead of replacing it. A native <input type="file"> always hands back only the
// LATEST picker result as its own .files — true regardless of whether the picker was opened via
// a scripted .click() or (as here) a native <label for>, since that only changes how the picker
// is OPENED, never what the browser reports once it closes — so remembering earlier selections
// across repeat Browse/drop actions has to be this function's job, not the input's.
function showBatchSelection(fileList) {
  const newFiles = Array.from(fileList);
  const combined = pendingBatchFiles.concat(newFiles);

  batchSelectionSummary.hidden = false;
  batchProgressGrid.innerHTML = "";
  batchOverallProgress.hidden = true;

  if (combined.length > BATCH_FILE_LIMIT) {
    pendingBatchFiles = [];
    batchStartBtn.hidden = true;
    batchSelectionList.innerHTML =
      `<span class="batch-selection-warning">Selected ${combined.length} files — ` +
      `pick ${BATCH_FILE_LIMIT} or fewer.</span>`;
    return;
  }

  pendingBatchFiles = combined;
  batchStartBtn.hidden = false;
  batchSelectionList.innerHTML =
    `<strong>${combined.length} file${combined.length === 1 ? "" : "s"} selected:</strong> ` +
    combined.map((f) => f.name).join(", ");
}

// No click handler on purpose: the dropzone is a <label for>, so the browser activates the input natively.
batchFileInput.addEventListener("change", () => {
  if (batchFileInput.files.length) showBatchSelection(batchFileInput.files);
});

["dragover", "dragenter"].forEach((evt) =>
  batchDropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    batchDropzone.style.borderColor = "var(--accent-slate)";
  })
);
["dragleave", "drop"].forEach((evt) =>
  batchDropzone.addEventListener(evt, (e) => {
    e.preventDefault();
    batchDropzone.style.borderColor = "";
  })
);
batchDropzone.addEventListener("drop", (e) => {
  if (e.dataTransfer.files.length) showBatchSelection(e.dataTransfer.files);
});

// One label/status-class pair per item status. The cold-vs-warm split
// inside "extracting" is the one the reviewer actually needs to notice —
// everything else is just "something is happening, hang on."
//
// The full items array being processed right now, kept at module scope
// so interactive handlers (needs-type picks, remove clicks) that fire
// from user clicks — not from processBatchFiles' own callback — can
// still find and mutate the right item.
let currentBatchItems = [];

// All five report types, same set and labels as the main Report Type
// card grid — a needs-type card offers the same choices a person would
// have had if they'd picked manually from the start.
const BATCH_TYPE_OPTIONS = ["notifiable", "immunization", "laboratory", "syndromic", "outbreak"];

function renderProcessingCardBody(item) {
  if (item.status === "queued") {
    return `
      <div class="batch-progress-filename" title="${item.filename}">${item.filename}</div>
      <div class="batch-progress-status batch-status-waiting">Waiting…</div>
    `;
  }
  if (item.status === "parsing" || item.status === "detecting") {
    const label = item.status === "parsing" ? "Reading file…" : "Detecting report type…";
    return `
      <div class="batch-progress-filename" title="${item.filename}">${item.filename}</div>
      <div class="batch-progress-status batch-status-active"><span class="batch-spinner"></span> ${label}</div>
    `;
  }
  // "extracting"
  const cold = item.timing.extractWasCold;
  const statusLine = cold
    ? `<div class="batch-progress-status batch-status-cold">
         <span class="batch-spinner batch-spinner-slow"></span>
         Loading extraction model — this can take up to a minute
       </div>`
    : `<div class="batch-progress-status batch-status-active">
         <span class="batch-spinner"></span> Extracting fields…
       </div>`;
  return `
    <div class="batch-progress-filename" title="${item.filename}">${item.filename}</div>
    ${statusLine}
  `;
}

function renderNeedsTypeCardBody(item) {
  const buttons = BATCH_TYPE_OPTIONS.map(
    (type) => `<button type="button" class="batch-type-btn" data-batch-type="${type}">${typeLabels[type]}</button>`
  ).join("");
  return `
    <div class="batch-progress-filename" title="${item.filename}">${item.filename}</div>
    <div class="batch-progress-status batch-status-warn">Couldn't confidently detect the type — pick one:</div>
    <div class="batch-type-options">${buttons}</div>
  `;
}

function renderErrorCardBody(item) {
  return `
    <div class="batch-progress-filename" title="${item.filename}">${item.filename}</div>
    <div class="batch-progress-status batch-status-error">✗ ${item.errorMessage}</div>
    <button type="button" class="batch-remove-btn" data-batch-remove>Remove from batch</button>
  `;
}

// The full editable review card — reuses renderFieldsTable exactly the
// way the single-report flow does. The "Reviewed" checkbox is plain,
// uncontrolled DOM state: nothing here ever sets it programmatically,
// nothing but the reviewer's own click ever checks it, and re-rendering
// this same card never happens again once it's "ready" (extraction
// doesn't re-run), so there's no risk of it silently resetting either.
// Rendered ONCE, the moment this item first reaches "ready" — nothing
// ever rebuilds this card's HTML again after that, including through
// the whole save step (Milestone 5). A save attempt only ever touches
// the #batch-save-status-<id> placeholder below directly, or disables
// individual inputs on success — never re-renders this template — so a
// reviewer's field edits and the checkbox's checked state can never be
// silently wiped out by a save in progress or a save on another card.
function renderReadyCardBody(item) {
  const label = typeLabels[item.detectedType] || item.detectedType;
  const fieldTypes = FIELD_TYPES[item.selectedType] || {};
  return `
    <div class="batch-card-header">
      <span class="batch-progress-filename" title="${item.filename}">${item.filename}</span>
      <span class="batch-type-pill">${label}</span>
    </div>
    ${renderFieldsTable(item.extractedFields, item.confidence, fieldTypes, item.selectedType, `-${item.id}`)}
    <label class="batch-reviewed-label">
      <input type="checkbox" class="batch-reviewed-checkbox">
      <span>Reviewed — ready to save</span>
    </label>
    <div class="batch-card-save-status" id="batch-save-status-${item.id}"></div>
  `;
}

function renderBatchCardBody(item) {
  switch (item.status) {
    case "queued":
    case "parsing":
    case "detecting":
    case "extracting":
      return renderProcessingCardBody(item);
    case "needs-type":
      return renderNeedsTypeCardBody(item);
    case "ready":
      return renderReadyCardBody(item);
    case "error":
      return renderErrorCardBody(item);
    default:
      return "";
  }
}

// Full rebuild — used ONCE per batch run, for the very first render
// (every item still "queued"), when there is nothing live in any card
// yet to lose. Every subsequent update goes through updateBatchCard
// instead, which touches only the one card that actually changed.
function renderBatchProgressGrid(items) {
  batchProgressGrid.innerHTML = items.map(
    (item) => `<div class="batch-progress-card" id="batch-card-${item.id}">${renderBatchCardBody(item)}</div>`
  ).join("");
}

// Targeted update: replaces only this item's own card body, leaving
// every sibling card's live DOM — field edits in progress, a checked
// Reviewed box — completely undisturbed. This is what makes it safe for
// one card to keep processing (or for the reviewer to keep editing a
// finished one) while others change state around it.
function updateBatchCard(item) {
  const el = document.getElementById(`batch-card-${item.id}`);
  if (!el) return;
  el.innerHTML = renderBatchCardBody(item);

  // Fires exactly once per card: item.status only ever transitions INTO "ready" a single time
  // (see renderReadyCardBody's own comment — nothing rebuilds a ready card's HTML again after
  // this), so this is the one moment this card's preview placeholder exists to fill in, mirroring
  // the single-report flow's own refreshTerminologyPreview() call right after its table renders.
  if (item.status === "ready") {
    refreshTerminologyPreview(el, item.selectedType, `-${item.id}`);
  }
}

const TERMINAL_STATUSES = ["ready", "error", "needs-type"];

function renderBatchOverallProgress(items) {
  const done = items.filter((i) => TERMINAL_STATUSES.includes(i.status)).length;
  batchOverallProgress.hidden = false;
  batchOverallProgress.textContent = done === items.length
    ? `Done — ${items.length} of ${items.length} processed.`
    : `Processing ${done} of ${items.length}…`;
}

// One delegated listener for the whole grid, since cards are created and
// replaced dynamically — attaching per-card listeners would mean
// re-attaching them after every render.
batchProgressGrid.addEventListener("click", async (e) => {
  const typeBtn = e.target.closest("[data-batch-type]");
  if (typeBtn) {
    const card = typeBtn.closest(".batch-progress-card");
    const item = currentBatchItems.find((i) => `batch-card-${i.id}` === card.id);
    if (!item) return;
    // Decision (approved in the Batch Upload plan): picking a type here
    // extracts ONLY this one file — every other card is untouched and
    // keeps whatever state it already had, processing or already ready.
    item.selectedType = typeBtn.dataset.batchType;
    await extractBatchItem(item, updateBatchCard);
    return;
  }

  const removeBtn = e.target.closest("[data-batch-remove]");
  if (removeBtn) {
    const card = removeBtn.closest(".batch-progress-card");
    const item = currentBatchItems.find((i) => `batch-card-${i.id}` === card.id);
    if (item) item.excluded = true;
    card.remove();
    return;
  }
});

// Reviewed checkboxes are plain, uncontrolled DOM elements (see
// renderReadyCardBody) — this is the only listener that ever reacts to
// one changing, and it only updates the Save button's label/enabled
// state, never the checkbox itself or anything else on the card.
batchProgressGrid.addEventListener("change", (e) => {
  if (e.target.classList.contains("batch-reviewed-checkbox")) {
    updateBatchSaveButton();
    return;
  }

  // Same terminology-preview recompute as the single-report flow's own delegated listener, scoped
  // to just the one card being edited via closest() — the exact isolation mechanism the type-button
  // and remove-button handlers above already use to find "which item does this event belong to",
  // so editing one card's field can never touch a sibling card's preview.
  const card = e.target.closest(".batch-progress-card");
  if (!card) return;
  const item = currentBatchItems.find((i) => `batch-card-${i.id}` === card.id);
  if (!item) return;
  const config = TERMINOLOGY_PREVIEW[item.selectedType];
  if (config && e.target.matches(`input[data-field="${config.field}"]`)) {
    refreshTerminologyPreview(card, item.selectedType, `-${item.id}`);
  }
});

batchStartBtn.addEventListener("click", async () => {
  if (!pendingBatchFiles.length) return;

  // This run's files are now spoken for. Now that showBatchSelection() genuinely accumulates
  // (see its own comment) rather than replacing, pendingBatchFiles has to be cleared here too —
  // otherwise a LATER, separate selection (after this run finishes and the dropzone unlocks)
  // would silently pick up where this one left off and re-submit these same files alongside it.
  const filesToProcess = pendingBatchFiles;
  pendingBatchFiles = [];

  batchStartBtn.disabled = true;
  batchDropzone.classList.add("batch-dropzone-locked");

  // Independent of processing itself — the save picker just needs to
  // know what batches already exist, which has nothing to do with
  // which files were selected. Runs in parallel with processing below.
  batchSaveSection.hidden = false;
  batchSaveLinks.replaceChildren();
  populateBatchSelectForUpload();
  updateBatchSaveButton();

  let gridInitialized = false;
  await processBatchFiles(filesToProcess, (item, items) => {
    currentBatchItems = items;
    if (!gridInitialized) {
      // First callback fires with every item still "queued" — the
      // whole array is already populated at this point, so this one
      // full render lays out every card before any of them starts.
      renderBatchProgressGrid(items);
      gridInitialized = true;
    } else {
      updateBatchCard(item);
    }
    renderBatchOverallProgress(items);
  });

  batchStartBtn.disabled = false;
  batchDropzone.classList.remove("batch-dropzone-locked");
});

// ---------- Batch Upload: save step (Milestone 5) --------------------
const batchSaveSection = document.getElementById("batch-save-section");
const batchSaveSelect = document.getElementById("batch-save-select");
const batchSaveNewInput = document.getElementById("batch-save-new-input");
const batchSaveBtn = document.getElementById("batch-save-btn");
const batchSaveStatus = document.getElementById("batch-save-status");
const batchSaveLinks = document.getElementById("batch-save-links");
const batchSaveNote = document.getElementById("batch-save-note");
let batchListCache = null;      // full unioned list from the last fetch
let batchListFilterKey = null;  // report types the picker is currently narrowed to

async function populateBatchSelectForUpload() {
  batchListCache = await fetchAllBatchRecords();
  batchListFilterKey = null;
  refreshBatchSaveOptions();
}

// Convenience filter only (saving still reads whatever is selected): list batches that already hold at least one record of ANY report type about to be saved; nothing ticked yet = no filter.
function refreshBatchSaveOptions() {
  if (!batchListCache) return;
  const present = new Set(reviewedUnsavedItems().map((item) => item.selectedType));
  const types = Object.keys(ENDPOINTS).filter((t) => present.has(t));
  const key = types.join(",");
  if (key === batchListFilterKey) return;
  batchListFilterKey = key;

  const matches = types.length ? batchListCache.filter((b) => b.types.some((t) => types.includes(t))) : batchListCache;
  const picked = batchSaveSelect.value;
  populateBatchOptions(batchSaveSelect, batchSaveNewInput, matches);

  // Never silently switch the target: a picked batch that stopped matching stays selected, marked.
  if (picked && picked !== "__new__" && !matches.some((b) => b.batch_label === picked)) {
    const known = batchListCache.find((b) => b.batch_label === picked);
    const opt = document.createElement("option");
    opt.value = picked;
    opt.dataset.batch = "1";
    opt.textContent = `${picked}${known ? ` (${known.record_count})` : ""} — no matching records`;
    batchSaveSelect.insertBefore(opt, batchSaveSelect.querySelector('option[value="__new__"]'));
  }
  batchSaveSelect.value = picked;

  const names = types.map((t) => typeLabels[t]);
  const joined = names.length > 1 ? `${names.slice(0, -1).join(", ")} or ${names[names.length - 1]}` : names[0];
  batchSaveNote.textContent = !types.length
    ? "Showing all batches. Tick reviewed reports to narrow this to batches that already hold the same report types."
    : matches.length
      ? `Showing batches with ${joined} records.`
      : `No existing batch has ${joined} records yet. Choose "+ New batch..." or Original data.`;
}

// Choosing something else lets a marked, no-longer-matching batch drop out of the list.
batchSaveSelect.addEventListener("change", () => {
  batchListFilterKey = null;
  refreshBatchSaveOptions();
});

// The exact set the Save button will act on: ready, not removed, not
// already saved, and currently checked. Recomputed fresh every time
// (button label, click handler, and the retry pass after a partial
// failure all call this) rather than cached, so it can never drift from
// the real DOM state of the checkboxes.
function reviewedUnsavedItems() {
  return currentBatchItems.filter((item) => {
    if (item.status !== "ready" || item.excluded || item.saveStatus === "saved") return false;
    const cardEl = document.getElementById(`batch-card-${item.id}`);
    const checkbox = cardEl && cardEl.querySelector(".batch-reviewed-checkbox");
    return !!(checkbox && checkbox.checked);
  });
}

function updateBatchSaveButton() {
  const n = reviewedUnsavedItems().length;
  batchSaveBtn.textContent = `Save ${n} Reviewed Report${n === 1 ? "" : "s"}`;
  batchSaveBtn.disabled = n === 0;
  refreshBatchSaveOptions();
}

function setCardSaveStatus(item, html) {
  const el = document.getElementById(`batch-save-status-${item.id}`);
  if (el) el.innerHTML = html;
}

// Called only on a SUCCESSFUL save — disables the card's own inputs so
// a saved record can't be edited-and-resaved by accident, without ever
// touching (or re-rendering) the rest of the card.
function lockSavedCard(item) {
  const cardEl = document.getElementById(`batch-card-${item.id}`);
  if (!cardEl) return;
  cardEl.querySelectorAll("input").forEach((input) => { input.disabled = true; });
  cardEl.classList.add("batch-card-saved");
}

// Saves exactly one item, using the SAME per-type /save endpoint and
// collectEditedRecord() the single-report flow uses — no parallel save
// implementation. Only ever touches this item's own card (the
// #batch-save-status-<id> placeholder, or disabling its own inputs on
// success) — a failure here leaves the checkbox checked and the fields
// exactly as the reviewer left them, ready to retry.
async function saveBatchItem(item, batchLabel) {
  const config = ENDPOINTS[item.selectedType];
  const cardEl = document.getElementById(`batch-card-${item.id}`);
  const editedRecord = collectEditedRecord(cardEl, item.selectedType, item.extractedFields);

  setCardSaveStatus(item, `<span class="batch-save-inprogress">Saving…</span>`);

  try {
    const response = await fetch(`${API_BASE}${config.save}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        [config.savePayloadKey]: editedRecord,
        confidence: item.confidence,
        batch_label: batchLabel,
      }),
    });
    const data = await response.json();

    if (!response.ok) {
      item.saveStatus = "save-error";
      item.saveError = formatSaveError(data.detail, `Save failed (HTTP ${response.status}).`);
      setCardSaveStatus(item, `<span class="batch-save-error">✗ ${item.saveError} Still reviewed — click Save again to retry.</span>`);
      return false;
    }

    item.saveStatus = "saved";
    item.savedId = data.id;
    item.savedBatchLabel = batchLabel;
    const target = batchLabel ? `to batch "${batchLabel}"` : "to the original (unbatched) data";
    setCardSaveStatus(item, `<span class="batch-save-success">✓ Saved ${target}.</span>`);
    lockSavedCard(item);
    return true;
  } catch (err) {
    item.saveStatus = "save-error";
    item.saveError = `Could not reach the backend at ${API_BASE}.`;
    setCardSaveStatus(item, `<span class="batch-save-error">✗ ${item.saveError} Still reviewed — click Save again to retry.</span>`);
    return false;
  }
}

// One button per report type with a saved item; deep-links only when all of that type's saved records share one batch.
function renderBatchDashboardLinks() {
  const labelsByType = new Map();
  currentBatchItems.forEach((item) => {
    if (item.saveStatus !== "saved") return;
    if (!labelsByType.has(item.selectedType)) labelsByType.set(item.selectedType, new Set());
    labelsByType.get(item.selectedType).add(item.savedBatchLabel || "");
  });
  const links = Object.keys(ENDPOINTS)
    .filter((type) => labelsByType.has(type))
    .map((type) => {
      const labels = labelsByType.get(type);
      return dashboardLink(type, labels.size === 1 ? [...labels][0] : "");
    });
  batchSaveLinks.replaceChildren(...links);
}

batchSaveBtn.addEventListener("click", async () => {
  // batch_label is read ONCE for the whole click — every item in this
  // pass shares it, matching "one chosen batch for the whole set."
  const batchLabel = getBatchLabelFrom(batchSaveSelect, batchSaveNewInput);
  const toSave = reviewedUnsavedItems();
  if (!toSave.length) return;

  batchSaveBtn.disabled = true;
  batchSaveStatus.textContent = `Saving ${toSave.length} report${toSave.length === 1 ? "" : "s"}…`;

  // Sequential, same reasoning as processing itself (Milestone 1) — a
  // handful of DB inserts, no benefit to added concurrency complexity.
  let succeeded = 0;
  for (const item of toSave) {
    const ok = await saveBatchItem(item, batchLabel);
    if (ok) succeeded += 1;
  }

  batchSaveStatus.textContent = succeeded === toSave.length
    ? `Saved ${succeeded} of ${toSave.length}.`
    : `Saved ${succeeded} of ${toSave.length} — the rest failed but are still reviewed ` +
      `and ready to retry. Click Save again to retry just those.`;

  renderBatchDashboardLinks();
  updateBatchSaveButton();
});
