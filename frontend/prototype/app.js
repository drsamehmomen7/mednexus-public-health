// ---------- Report type selection ----------
const reportCards = document.querySelectorAll(".report-card");
const summaryText = document.getElementById("summary-text");

let selectedType = "notifiable";
let inputMode = "paste";

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
  },
  immunization: {
    extract: "/reports/immunization/extract",
    save: "/reports/immunization/save",
    batches: "/reports/immunization/batches",
    savePayloadKey: "record",
  },
  laboratory: {
    extract: "/reports/laboratory/extract",
    save: "/reports/laboratory/save",
    batches: "/reports/laboratory/batches",
    savePayloadKey: "report",
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

// ---------- Extract button: calls the real backend ----------
const extractBtn = document.getElementById("extract-btn");
const resultArea = document.getElementById("result-area");
// Port 8001, not 8000: the MedNexus de-identification project already uses
// 8000 locally, and pointing at an occupied port silently talks to the
// wrong server.
const API_BASE = "http://127.0.0.1:8001";

// Holds the most recent extraction so the Save button can send back
// original field types + the confidence report, merged with whatever the
// reviewer edited in the input boxes.
let lastFields = null;
let lastConfidence = null;

extractBtn.addEventListener("click", async () => {
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

  const reportText = document.querySelector('.tab-panel[data-panel="paste"] textarea').value.trim();

  if (!reportText) {
    resultArea.innerHTML = `<span class="placeholder-text">Paste some report text first.</span>`;
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

    const rows = Object.entries(lastFields)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => {
        const conf = lastConfidence[key];
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

    resultArea.innerHTML = `
      <div style="width:100%;">
        <table style="width:100%; text-align:left; font-size:13px; border-collapse:collapse;">
          ${rows}
        </table>
        <p style="margin:12px 0 0; font-size:12px; color:var(--ink-soft);">
          Fields are editable. Anything below 60% confidence or marked
          "not found" should be checked against the original text before use.
        </p>
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
      </div>
    `;

    populateBatchSelect();
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
async function populateBatchSelect() {
  const select = document.getElementById("batch-select");
  const newInput = document.getElementById("batch-new-input");
  const config = ENDPOINTS[selectedType];

  try {
    const res = await fetch(`${API_BASE}${config.batches}`);
    const data = await res.json();
    data.batches.forEach((b) => {
      const opt = document.createElement("option");
      opt.value = b.batch_label;
      opt.textContent = `${b.batch_label} (${b.record_count})`;
      select.insertBefore(opt, select.querySelector('option[value="__new__"]'));
    });
  } catch (err) {
    // Non-fatal — the person can still save to "no batch" or type a new
    // batch name even if the existing-batches list couldn't be fetched.
  }

  select.addEventListener("change", () => {
    newInput.hidden = select.value !== "__new__";
    if (!newInput.hidden) newInput.focus();
  });
}

function currentBatchLabel() {
  const select = document.getElementById("batch-select");
  if (!select) return null;
  if (select.value === "__new__") {
    const name = document.getElementById("batch-new-input").value.trim();
    return name || null;
  }
  return select.value || null;
}
async function saveRecord() {
  const config = ENDPOINTS[selectedType];
  const statusEl = document.getElementById("save-status");
  statusEl.textContent = "Saving...";
  statusEl.style.color = "var(--ink-soft)";

  // Start from the last extracted values, then overlay whatever the
  // reviewer edited in the input boxes — this is what makes manual
  // correction actually take effect before saving, not just cosmetic.
  const editedRecord = { ...lastFields };
  const fieldTypes = FIELD_TYPES[selectedType] || {};

  document.querySelectorAll('#result-area input[data-field]').forEach((input) => {
    const field = input.dataset.field;
    const value = input.value;
    const type = fieldTypes[field];

    if (type === "bool") {
      editedRecord[field] = value.trim().toLowerCase() === "true";
    } else if (type === "int") {
      editedRecord[field] = value.trim() === "" ? null : parseInt(value, 10);
    } else {
      editedRecord[field] = value;
    }
  });

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
      statusEl.textContent = `Save failed: ${data.detail || response.status}`;
      statusEl.style.color = "#8a3a1f";
      return;
    }

    const batchLabel = currentBatchLabel();
    statusEl.textContent = batchLabel
      ? `Saved to batch "${batchLabel}".`
      : "Saved to the original (unbatched) data.";
    statusEl.style.color = "#4d7a2f";
  } catch (err) {
    statusEl.textContent = `Could not reach the backend at ${API_BASE}.`;
    statusEl.style.color = "#8a3a1f";
  }
}
