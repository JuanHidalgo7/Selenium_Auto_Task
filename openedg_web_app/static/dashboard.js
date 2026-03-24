const statusText = document.getElementById("statusText");
const suspiciousEl = document.getElementById("suspicious");
const unverifiedEl = document.getElementById("unverified");
const orgAppsEl = document.getElementById("orgapps");

function setStatus(message) {
  if (statusText) {
    statusText.textContent = message;
  }
}

function setCounter(el, value) {
  el.textContent = value && `${value}`.trim() ? value : "N/A";
}

async function refreshCounters() {
  setStatus("Updating data from dashboard...");

  try {
    const response = await fetch("/api/counters", {
      method: "GET",
      headers: { "Accept": "application/json" },
      credentials: "same-origin",
      cache: "no-store"
    });

    if (!response.ok) {
      const errorPayload = await response.json().catch(() => ({}));
      throw new Error(errorPayload.error || `HTTP ${response.status}`);
    }

    const data = await response.json();

    setCounter(suspiciousEl, data.suspicious);
    setCounter(unverifiedEl, data.unverified);
    setCounter(orgAppsEl, data.org_apps);
    setStatus(`Last updated: ${new Date().toLocaleTimeString()}`);
  } catch (error) {
    setStatus(`Error: ${error.message}`);
  }
}

refreshCounters();
setInterval(refreshCounters, 300000);
