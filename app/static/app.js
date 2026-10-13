const form = document.getElementById("form");
const btn = document.getElementById("btn");
const status = document.getElementById("status");
const steps = document.getElementById("steps");
const stepList = document.getElementById("step-list");
const report = document.getElementById("report");
const reportBody = document.getElementById("report-body");

form.addEventListener("submit", async (e) => {
  e.preventDefault();
  const query = document.getElementById("query").value.trim();
  if (!query) return;

  btn.disabled = true;
  status.classList.remove("hidden");
  status.textContent = "Agent running…";
  steps.classList.add("hidden");
  report.classList.add("hidden");
  stepList.innerHTML = "";

  try {
    const res = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ query }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();

    status.textContent = `Done · mode=${data.mode} · ticker=${data.ticker || "—"}`;
    for (const s of data.steps || []) {
      const li = document.createElement("li");
      const tool = s.tool ? `<code>${s.tool}</code>` : "<em>final</em>";
      li.innerHTML = `<strong>${tool}</strong> — ${escapeHtml(s.thought || "")}`;
      stepList.appendChild(li);
    }
    steps.classList.remove("hidden");
    reportBody.textContent = data.report_markdown || "";
    report.classList.remove("hidden");
  } catch (err) {
    status.textContent = `Failed: ${err.message}`;
  } finally {
    btn.disabled = false;
  }
});

function escapeHtml(str) {
  return str
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;");
}