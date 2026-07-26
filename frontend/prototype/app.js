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

function updateSummary() {
  summaryText.textContent = `${typeLabels[selectedType]} · ${inputMode === "paste" ? "Text input" : "File upload"} · Local processing`;
}

reportCards.forEach((card) => {
  card.addEventListener("click", () => {
    reportCards.forEach((c) => c.setAttribute("aria-pressed", "false"));
    card.setAttribute("aria-pressed", "true");
    selectedType = card.dataset.type;
    updateSummary();
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

extractBtn.addEventListener("click", async () => {
  const reportText = document.querySelector('.tab-panel[data-panel="paste"] textarea').value.trim();

  if (!reportText) {
    resultArea.innerHTML = `<span class="placeholder-text">Paste some report text first.</span>`;
    return;
  }

  resultArea.innerHTML = `<span class="placeholder-text">Extracting...</span>`;

  try {
    const response = await fetch(`${API_BASE}/reports/notifiable-disease/extract`, {
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

    const fields = data.extracted;
    const confidence = data.confidence || {};

    const rows = Object.entries(fields)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => {
        const conf = confidence[key];
        let badge = "";

        if (conf) {
          if (conf.source === "rule_based") {
            badge = `<span style="font-size:11px; padding:2px 8px; border-radius:999px; background:#eef1f4; color:#57685e;">rule-based</span>`;
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
      </div>
    `;
  } catch (err) {
    resultArea.innerHTML = `
      <span class="placeholder-text">
        Could not reach the backend at ${API_BASE}. Is the server running
        (uvicorn app.main:app --reload)?
      </span>
    `;
  }
});
