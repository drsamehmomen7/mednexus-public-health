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
    const rows = Object.entries(fields)
      .filter(([, value]) => value !== null && value !== undefined)
      .map(([key, value]) => `<tr><td style="padding:4px 12px 4px 0; color:var(--ink-soft);">${key}</td><td>${value}</td></tr>`)
      .join("");

    resultArea.innerHTML = `
      <table style="width:100%; text-align:left; font-size:13px; border-collapse:collapse;">
        ${rows}
      </table>
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
