/**
 * IndusMind AI — Operations Command Center JavaScript
 * Fetches real-time data from /api/command-center/ and /api/briefing/
 */
(function () {
  "use strict";

  const briefingBtn = document.getElementById("briefingBtn");
  const briefingPanel = document.getElementById("briefingPanel");
  const briefingContent = document.getElementById("briefingContent");
  const closeBriefingBtn = document.getElementById("closeBriefingBtn");
  const copyBriefingBtn = document.getElementById("copyBriefingBtn");
  const refreshBtn = document.getElementById("refreshBtn");
  const ccChatForm = document.getElementById("ccChatForm");
  const ccChatInput = document.getElementById("ccChatInput");
  const ccMessages = document.getElementById("ccMessages");
  const agentStatuses = document.getElementById("agentStatuses");
  const alertCenter = document.getElementById("alertCenter");

  function getCookie(name) {
    const cookies = document.cookie.split(";");
    for (let c of cookies) {
      c = c.trim();
      if (c.startsWith(name + "=")) return decodeURIComponent(c.substring(name.length + 1));
    }
    return null;
  }

  // Fetch Command Center data
  async function loadDashboard() {
    try {
      const resp = await fetch("/api/command-center/", { headers: { "X-CSRFToken": getCookie("csrftoken") } });
      if (!resp.ok) return;
      const data = await resp.json();

      // Check if data exists
      if (!data.has_data) {
        alertCenter.innerHTML = `
          <div class="cc-empty-state" style="padding:2rem;text-align:center">
            <p style="font-size:1.25rem;margin-bottom:0.5rem">🏭 Welcome to IndusMind AI</p>
            <p style="color:#94a3b8;margin-bottom:1rem">No operational data available. Load the demo dataset to activate the Operations Dashboard.</p>
            <p style="color:#64748b;font-size:0.75rem">Run: <code style="background:#334155;padding:0.125rem 0.5rem;border-radius:0.25rem">python manage.py load_demo_data</code></p>
          </div>`;
        return;
      }

      // KPI Values
      document.getElementById("kpiHealth").textContent = data.plant_health_pct ? data.plant_health_pct + "%" : (data.plant_health || "—").toUpperCase();
      document.getElementById("kpiRisk").textContent = (data.overall_risk || "low").toUpperCase();
      document.getElementById("kpiCompliance").textContent = Math.round((data.compliance_score || 0) * 100) + "%";
      document.getElementById("kpiAlerts").textContent = data.critical_alerts || "0";
      document.getElementById("kpiEquipment").textContent = data.kpis?.total_equipment || "0";
      document.getElementById("kpiNodes").textContent = data.kpis?.total_nodes || "0";

      // Color-code risk KPI
      const riskEl = document.getElementById("kpiRisk");
      if (data.overall_risk === "critical") riskEl.style.color = "#ef4444";
      else if (data.overall_risk === "high") riskEl.style.color = "#f97316";
      else if (data.overall_risk === "medium") riskEl.style.color = "#f59e0b";
      else riskEl.style.color = "#10b981";

      // Render alerts
      if (data.warnings && data.warnings.length > 0) {
        alertCenter.innerHTML = data.warnings.map(w => `
          <div class="cc-alert-card cc-alert-${w.severity?.toLowerCase() || 'medium'}">
            <div class="cc-alert-title">${w.title || "Alert"}</div>
            <div class="cc-alert-meta">${w.severity || ""} · ${w.warning_type || ""} · Confidence: ${Math.round((w.confidence || 0) * 100)}%</div>
          </div>
        `).join("");
      } else {
        alertCenter.innerHTML = '<div class="cc-empty-state">✅ No active alerts. All systems nominal.</div>';
      }

      // Top risk equipment
      if (data.top_risk_equipment && data.top_risk_equipment.length > 0) {
        const riskHtml = data.top_risk_equipment.map(e => `<span class="cc-badge cc-badge-red" style="margin:0.125rem">${e}</span>`).join("");
        alertCenter.innerHTML += `<div style="margin-top:0.75rem;padding-top:0.75rem;border-top:1px solid #334155"><div class="cc-msg-section-title" style="margin-bottom:0.375rem">⚠️ Equipment at Risk</div>${riskHtml}</div>`;
      }
    } catch (e) { /* silent */ }
  }

  // Generate Executive Briefing
  async function generateBriefing() {
    briefingPanel.classList.remove("hidden");
    briefingContent.innerHTML = '<div class="cc-loading">🎙️ Generating executive briefing...</div>';

    try {
      const resp = await fetch("/api/briefing/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify({ query: "Generate daily operations briefing" }),
      });
      if (!resp.ok) throw new Error("Briefing failed");
      const data = await resp.json();
      const b = data.briefing || {};

      briefingContent.textContent = b.text || "Briefing unavailable.";
      document.getElementById("briefingConfidence").textContent = `Confidence: ${Math.round((b.confidence || 0) * 100)}%`;
      document.getElementById("briefingHealth").textContent = `Health: ${(b.plant_health || "—").toUpperCase()}`;
      document.getElementById("briefingRisk").textContent = `Risk: ${(b.overall_risk || "—").toUpperCase()}`;
    } catch (e) {
      briefingContent.textContent = "Failed to generate briefing. Please try again.";
    }
  }

  // Chat
  async function sendChat(query) {
    if (!query) return;
    ccMessages.innerHTML += `<div class="cc-msg cc-msg-user">${escapeHtml(query)}</div>`;
    ccMessages.innerHTML += `<div class="cc-msg cc-msg-ai cc-loading">🤖 Analyzing...</div>`;
    ccMessages.scrollTop = ccMessages.scrollHeight;

    // Show agent execution
    updateAgentStatus("running");

    try {
      const resp = await fetch("/api/query/", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": getCookie("csrftoken") },
        body: JSON.stringify({ query }),
      });
      const data = await resp.json();

      // Remove loading
      const loading = ccMessages.querySelector(".cc-loading");
      if (loading) loading.remove();

      // Render structured response
      ccMessages.innerHTML += renderResponse(data);
      ccMessages.scrollTop = ccMessages.scrollHeight;
      updateAgentStatus("completed", data.operations_report);
    } catch (e) {
      const loading = ccMessages.querySelector(".cc-loading");
      if (loading) loading.textContent = "❌ Failed. Please try again.";
      updateAgentStatus("idle");
    }
  }

  function renderResponse(data) {
    let html = '<div class="cc-msg cc-msg-ai">';
    html += `<div>${escapeHtml(data.answer || "")}</div>`;

    if (data.confidence) {
      html += `<div class="cc-msg-section"><span class="cc-badge cc-badge-blue">Confidence: ${Math.round(data.confidence * 100)}%</span></div>`;
    }
    if (data.operations_report) {
      const r = data.operations_report;
      if (r.warnings && r.warnings.length > 0) {
        html += `<div class="cc-msg-section"><div class="cc-msg-section-title">⚠️ Warnings (${r.warnings.length})</div>`;
        r.warnings.slice(0, 3).forEach(w => { html += `<div class="cc-alert-card cc-alert-${(w.severity || '').toLowerCase()}" style="margin-top:0.25rem"><div class="cc-alert-title">${w.title || ""}</div></div>`; });
        html += "</div>";
      }
      if (r.risk_assessment) {
        html += `<div class="cc-msg-section"><div class="cc-msg-section-title">🛡️ Risk</div><span class="cc-badge cc-badge-yellow">${(r.risk_assessment.overall_risk || "").toUpperCase()}</span></div>`;
      }
    }
    if (data.maintenance_analysis) {
      html += `<div class="cc-msg-section"><div class="cc-msg-section-title">🔧 Maintenance</div><span class="cc-badge cc-badge-${data.maintenance_analysis.risk_level === 'critical' ? 'red' : 'yellow'}">${(data.maintenance_analysis.risk_level || "").toUpperCase()}</span></div>`;
    }
    if (data.compliance_analysis) {
      html += `<div class="cc-msg-section"><div class="cc-msg-section-title">⚖️ Compliance</div><span class="cc-badge cc-badge-purple">${(data.compliance_analysis.compliance_status || "").replace("_", " ").toUpperCase()}</span></div>`;
    }
    if (data.suggested_followups && data.suggested_followups.length > 0) {
      html += `<div class="cc-msg-section"><div class="cc-msg-section-title">🚀 Actions</div>`;
      data.suggested_followups.forEach(q => { html += `<button class="cc-btn-sm cc-followup" style="margin:0.125rem">${escapeHtml(q)}</button>`; });
      html += "</div>";
    }
    html += "</div>";
    return html;
  }

  function updateAgentStatus(state, report) {
    const agents = ["Maintenance Agent", "Compliance Agent", "Failure Intelligence", "Knowledge Graph", "Drawing Analysis", "Warning Engine", "Trend Analysis", "Gemini Reasoning"];
    const badges = state === "running" ? '<span class="cc-badge cc-badge-yellow">Running</span>' :
                   state === "completed" ? '<span class="cc-badge cc-badge-green">✓</span>' :
                   '<span class="cc-badge cc-badge-gray">Idle</span>';
    const icons = ["🔧", "⚖️", "📚", "🧠", "📐", "⚠️", "📈", "✨"];

    if (report && report.agent_statuses) {
      agentStatuses.innerHTML = report.agent_statuses.map((a, i) =>
        `<div class="cc-agent-item"><span>${icons[i] || "🤖"} ${a.agent}</span><span class="cc-badge cc-badge-${a.status === 'completed' ? 'green' : 'gray'}">${a.status === 'completed' ? '✓' : '—'}</span></div>`
      ).join("");
    } else {
      agentStatuses.innerHTML = agents.map((a, i) =>
        `<div class="cc-agent-item"><span>${icons[i]} ${a}</span>${badges}</div>`
      ).join("");
    }
  }

  function escapeHtml(t) { const d = document.createElement("div"); d.textContent = t; return d.innerHTML; }

  // Events
  briefingBtn.addEventListener("click", generateBriefing);
  closeBriefingBtn.addEventListener("click", () => briefingPanel.classList.add("hidden"));
  copyBriefingBtn.addEventListener("click", () => navigator.clipboard?.writeText(briefingContent.textContent));
  refreshBtn.addEventListener("click", loadDashboard);

  ccChatForm.addEventListener("submit", (e) => { e.preventDefault(); sendChat(ccChatInput.value.trim()); ccChatInput.value = ""; });

  // Delegate follow-up clicks
  ccMessages.addEventListener("click", (e) => {
    if (e.target.classList.contains("cc-followup")) sendChat(e.target.textContent);
  });

  // Initial load
  loadDashboard();
})();
