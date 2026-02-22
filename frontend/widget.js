/* KlusPilot Widget (frontend/widget.js)
   ------------------------------------------------------------
   FIX: Dynamische API URL zodat localhost/127.0.0.1/LAN IP werkt.
*/

(function () {
  function getApiBaseUrl() {
    const params = new URLSearchParams(window.location.search);
    const apiOverride = params.get("api");

    if (apiOverride) {
      return apiOverride.replace(/\/$/, "");
    }

    // If opened via file:// fallback
    if (window.location.protocol === "file:") {
      return "http://localhost:8000";
    }

    const host = window.location.hostname;
    const protocol = window.location.protocol;

    return `${protocol}//${host}:8000`;
  }

  const API_BASE = getApiBaseUrl();

  const root = document.createElement("div");
  root.id = "kluspilot-widget-root";
  document.body.appendChild(root);

  root.innerHTML = `
    <div class="kp-widget">
      <div class="kp-header">
        <div class="kp-logo"></div>
        <div class="kp-title">
          <div class="kp-name">KlusPilot</div>
          <div class="kp-sub">Snel hulp aanvragen</div>
        </div>
      </div>

      <div class="kp-body">
        <div class="kp-status">
          API: <span class="kp-api-url">${API_BASE}</span>
        </div>

        <button class="kp-btn" id="kp-check">Check verbinding</button>
        <button class="kp-btn kp-primary" id="kp-load">Laad diensten</button>

        <div class="kp-services" id="kp-services"></div>
      </div>
    </div>
  `;

  const btnCheck = document.getElementById("kp-check");
  const btnLoad = document.getElementById("kp-load");
  const servicesBox = document.getElementById("kp-services");

  function setServices(html) {
    servicesBox.innerHTML = html;
  }

  async function checkConnection() {
    try {
      const res = await fetch(`${API_BASE}/health`);
      if (!res.ok) throw new Error("Health not ok");

      const data = await res.json();
      return data;
    } catch (e) {
      return null;
    }
  }

  async function loadServices() {
    try {
      const res = await fetch(`${API_BASE}/services`);
      if (!res.ok) throw new Error("Services not ok");

      const data = await res.json();
      return data.services || data || [];
    } catch (e) {
      return [];
    }
  }

  btnCheck.addEventListener("click", async () => {
    setServices("<div>Bezig met verbinden...</div>");

    const ok = await checkConnection();
    if (!ok) {
      setServices(`<div style="color:#ff7070;">❌ Kan niet verbinden met API (${API_BASE})</div>`);
      return;
    }

    setServices(`<div style="color:#7dff9d;">✅ Verbonden! (${JSON.stringify(ok)})</div>`);
  });

  btnLoad.addEventListener("click", async () => {
    setServices("<div>Diensten laden...</div>");

    const services = await loadServices();

    if (!services.length) {
      setServices(`<div style="color:#ff7070;">Geen diensten gevonden of API offline.</div>`);
      return;
    }

    const html = services
      .map(
        (s) => `
        <div class="kp-service">
          <div class="kp-service-name">${s.name}</div>
          <div class="kp-service-desc">${s.description || ""}</div>
        </div>
      `
      )
      .join("");

    setServices(html);
  });
})();
