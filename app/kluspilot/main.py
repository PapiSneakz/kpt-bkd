from fastapi import FastAPI, Depends, HTTPException, Request, Query, Form, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from pydantic import BaseModel
from typing import Optional, List, Dict, Any
from starlette.middleware.sessions import SessionMiddleware
from pathlib import Path
import os

from .db import Base, engine, get_db
from .models import Conversation, Message, Lead
from .schemas import ChatStartRequest, ChatStartResponse, ChatRequest, ChatResponse
from .tenant_config import load_tenant, enabled_services, save_tenant, TenantConfig, ServiceItem
from .flows import build_welcome
from .ai import chat
from .config import settings
from .notify import send_lead_email
from .admin_auth import require_admin, check_credentials
from .tenant_auth import verify_password, hash_password

app = FastAPI(title="KlusPilot API")
templates = Jinja2Templates(directory="kluspilot/templates")

# ✅ Tenant assets (uploads zoals achtergrond/logo) serveren
# FIX: assets moeten NIET in TENANTS_DIR (kan read-only zijn),
# maar in een aparte writable map (TENANT_ASSETS_DIR)
TENANT_ASSETS_BASE = Path(os.getenv("TENANT_ASSETS_DIR", "/app/tenant-assets")).resolve()
TENANT_ASSETS_BASE.mkdir(parents=True, exist_ok=True)
app.mount("/tenant-assets", StaticFiles(directory=str(TENANT_ASSETS_BASE)), name="tenant-assets")

# ✅ Sessions (admin + tenant portal)
app.add_middleware(SessionMiddleware, secret_key=settings.SESSION_SECRET)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",

        "http://localhost:5500",
        "http://127.0.0.1:5500",

        # ✅ FIX: Live Server draait vaak op 5501 (of schuift door)
        "http://localhost:5501",
        "http://127.0.0.1:5501",
        "http://localhost:5502",
        "http://127.0.0.1:5502",
        "http://localhost:5503",
        "http://127.0.0.1:5503",

        "http://localhost:8000",
        "http://127.0.0.1:8000",
        "null",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ======================================================================
# MULTI-TENANT: tenant_id uit subdomain/host
# ======================================================================

RESERVED_SUBDOMAINS = {"www", "admin", "portal", "app", "api"}


def tenant_id_from_host(request: Request) -> Optional[str]:
    """
    Lokaal (zonder domein):
      bedrijf1.localhost:8000 -> bedrijf1
    Productie straks:
      bedrijf1.jouwdomein.nl   -> bedrijf1  (als je ROOT_DOMAIN instelt)
    """
    host = (request.headers.get("host") or "").lower()
    host = host.split(":")[0]

    # ✅ werkt meestal direct zonder hosts file
    if host.endswith(".localhost"):
        sub = host[: -len(".localhost")]
        if sub and sub not in RESERVED_SUBDOMAINS:
            return sub
        return None

    # Voor later: als je settings.ROOT_DOMAIN toevoegt
    root_domain = getattr(settings, "ROOT_DOMAIN", None)
    if root_domain:
        root = str(root_domain).lower().strip()
        if host == root or host == f"www.{root}":
            return None
        if host.endswith("." + root):
            sub = host[: -(len(root) + 1)]
            if sub and sub not in RESERVED_SUBDOMAINS:
                return sub

    return None


def resolve_tenant_id(request: Request, explicit: Optional[str] = None) -> str:
    # 1) expliciet (query/body) voor testen
    if explicit:
        return explicit.strip()

    # 2) host/subdomain (SaaS manier)
    from_host = tenant_id_from_host(request)
    if from_host:
        return from_host

    # 3) fallback (demo)
    return "demo-company"


# ======================================================================
# DATABASE INIT
# ======================================================================

@app.on_event("startup")
def init_db():
    Base.metadata.create_all(bind=engine)


# ======================================================================
# BASIC ROUTES
# ======================================================================

@app.get("/health")
def health():
    return {"ok": True, "version": "1.0.0"}


# ======================================================================
# ✅ LIVE DEMO PAGE (Option B)
# ======================================================================

@app.get("/demo", response_class=HTMLResponse)
def demo_page():
    return """
<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>KlusPilot — Live Demo</title>
  <style>
    :root{color-scheme:dark}
    body{margin:0;background:#070a14;color:#fff;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial}
    .bg{
      position:fixed;inset:0;z-index:-1;
      background:
        radial-gradient(900px 500px at 20% 20%, rgba(34,197,94,.20), transparent 60%),
        radial-gradient(800px 500px at 80% 30%, rgba(59,130,246,.18), transparent 60%),
        radial-gradient(900px 600px at 50% 90%, rgba(168,85,247,.14), transparent 60%),
        linear-gradient(180deg, #050714, #070a14);
    }
    .wrap{max-width:1050px;margin:0 auto;padding:18px}
    .top{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
    .brand{display:flex;gap:12px;align-items:center}
    .logo{
      width:44px;height:44px;border-radius:16px;
      background:linear-gradient(135deg,#22c55e,#3b82f6);
      display:grid;place-items:center;font-weight:900;color:#071018;
      box-shadow:0 0 0 1px rgba(255,255,255,.08) inset, 0 18px 60px rgba(34,197,94,.15);
    }
    .title{font-weight:900;font-size:18px;line-height:1}
    .sub{opacity:.7;font-size:12px;margin-top:3px}
    .pill{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.06);padding:8px 10px;border-radius:999px;font-size:12px;opacity:.92}
    .grid{margin-top:14px;display:grid;grid-template-columns:1.1fr .9fr;gap:14px}
    @media (max-width: 980px){.grid{grid-template-columns:1fr}}
    .card{
      border-radius:22px;
      background:rgba(255,255,255,.06);
      border:1px solid rgba(255,255,255,.14);
      backdrop-filter: blur(14px);
      -webkit-backdrop-filter: blur(14px);
      overflow:hidden;
      box-shadow:0 0 0 1px rgba(255,255,255,.06) inset;
    }
    .cardHead{display:flex;align-items:center;justify-content:space-between;gap:10px;padding:14px 14px;border-bottom:1px solid rgba(255,255,255,.10)}
    .cardHead b{font-size:14px}
    .muted{font-size:12px;opacity:.7}
    .chat{height:66vh;overflow:auto;padding:14px}
    .row{display:flex;gap:10px;padding:12px;border-top:1px solid rgba(255,255,255,.10);background:rgba(0,0,0,.15)}
    input,select,button{font:inherit}
    input,select{
      width:100%;
      padding:12px 12px;border-radius:14px;
      border:1px solid rgba(255,255,255,.14);
      background:rgba(0,0,0,.25);color:#fff;outline:none;
    }
    input:focus,select:focus{box-shadow:0 0 0 3px rgba(34,197,94,.20)}
    button{
      padding:12px 14px;border-radius:14px;border:0;
      background:linear-gradient(90deg,#22c55e,#3b82f6);
      color:#071018;font-weight:900;cursor:pointer;
      box-shadow:0 18px 50px rgba(59,130,246,.12);
      white-space:nowrap;
    }
    button.secondary{
      background:rgba(255,255,255,.06);
      color:#fff;border:1px solid rgba(255,255,255,.14);
      box-shadow:none;font-weight:800;
    }
    .msg{margin:10px 0;display:flex}
    .msg.you{justify-content:flex-end}
    .bubble{
      max-width:min(720px, 92%);
      border-radius:16px;
      padding:10px 12px;
      border:1px solid rgba(255,255,255,.12);
      background:rgba(0,0,0,.25);
      line-height:1.35;
      white-space:pre-wrap;
    }
    .msg.you .bubble{
      background:rgba(34,197,94,.16);
      border-color:rgba(34,197,94,.25);
    }
    .meta{font-size:11px;opacity:.65;margin-top:6px}
    .side{padding:14px}
    .kpi{display:grid;grid-template-columns:1fr 1fr;gap:10px}
    .kpi .box{padding:12px;border-radius:18px;background:rgba(0,0,0,.20);border:1px solid rgba(255,255,255,.10)}
    .kpi .box .big{font-weight:950;font-size:18px}
    .kpi .box .sm{font-size:12px;opacity:.75}
    .tips{margin-top:10px;padding:12px;border-radius:18px;background:rgba(0,0,0,.20);border:1px solid rgba(255,255,255,.10)}
    a{color:#fff}
    code{background:rgba(0,0,0,.25);padding:2px 6px;border-radius:10px;border:1px solid rgba(255,255,255,.10)}
  </style>
</head>
<body>
  <div class="bg"></div>

  <div class="wrap">
    <div class="top">
      <div class="brand">
        <div class="logo">KP</div>
        <div>
          <div class="title">KlusPilot — Live demo</div>
          <div class="sub">Test alsof je klant bent: lekkage, storing, verstopping…</div>
        </div>
      </div>
      <div class="pill">Endpoint: <code>/chat/start</code> + <code>/chat</code> • Tenant: <code>demo-company</code></div>
    </div>

    <div class="grid">
      <div class="card">
        <div class="cardHead">
          <div>
            <b>Demo chat</b>
            <div class="muted">Kies tenant, klik Start, en stuur een bericht.</div>
          </div>
          <div style="display:flex;gap:8px;flex-wrap:wrap">
            <button class="secondary" id="btnReset">Reset</button>
            <button id="btnStart">Start demo</button>
          </div>
        </div>

        <div id="chat" class="chat"></div>

        <div class="row">
          <select id="tenant">
            <option value="demo-company">demo-company</option>
          </select>
          <input id="inp" placeholder="Typ je bericht… (bijv. 'Mijn cv geeft storing')" />
          <button id="send">Verstuur</button>
        </div>
      </div>

      <div class="card">
        <div class="cardHead">
          <div>
            <b>Tips</b>
            <div class="muted">Handige prompts om te testen.</div>
          </div>
        </div>
        <div class="side">
          <div class="kpi">
            <div class="box">
              <div class="big" id="convId">—</div>
              <div class="sm">conversation_id</div>
            </div>
            <div class="box">
              <div class="big" id="status">—</div>
              <div class="sm">status</div>
            </div>
          </div>

          <div class="tips">
            <div class="sm" style="opacity:.8;margin-bottom:8px">Probeer bijvoorbeeld:</div>
            <ul style="margin:0;padding-left:18px;line-height:1.8;font-size:13px;opacity:.92">
              <li>“Mijn afvoer is verstopt en loopt niet weg.”</li>
              <li>“Ik heb kortsluiting in de meterkast.”</li>
              <li>“CV storing, geen warmte, het is spoed.”</li>
              <li>“Wat kost het ongeveer?”</li>
            </ul>
            <div class="meta">Let op: deze demo gebruikt jouw backend direct, dus hij werkt ook als je later tenants toevoegt.</div>
          </div>

          <div class="tips" style="margin-top:10px">
            <div class="sm" style="opacity:.8;margin-bottom:8px">Troubleshooting</div>
            <div style="font-size:13px;opacity:.9;line-height:1.6">
              Krijg je errors? Check dan <code>docker compose logs -f api</code>.
              Zorg dat <code>OPENAI_API_KEY</code> goed staat en dat de DB draait.
            </div>
          </div>

        </div>
      </div>
    </div>
  </div>

<script>
  const chatEl = document.getElementById("chat");
  const inp = document.getElementById("inp");
  const tenant = document.getElementById("tenant");
  const convIdEl = document.getElementById("convId");
  const statusEl = document.getElementById("status");

  let conversation_id = null;

  function add(role, text){
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "Jij" ? "you" : "bot");
    const b = document.createElement("div");
    b.className = "bubble";
    b.innerHTML = "<b>" + role + "</b><div class='meta'></div>" + (text || "");
    wrap.appendChild(b);
    chatEl.appendChild(wrap);
    chatEl.scrollTop = chatEl.scrollHeight;
  }

  function setMeta(){
    convIdEl.textContent = conversation_id ? String(conversation_id) : "—";
  }

  async function startDemo(){
    add("KlusPilot", "Demo starten…");
    const res = await fetch("/chat/start", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ tenant_id: tenant.value })
    });
    if(!res.ok){
      const t = await res.text();
      add("Error", "Start failed: " + t);
      return;
    }
    const j = await res.json();
    conversation_id = j.conversation_id;
    setMeta();
    statusEl.textContent = "open";
    if(j.first_message){
      add("KlusPilot", j.first_message);
    } else {
      add("KlusPilot", "Demo gestart. Stel je vraag!");
    }
  }

  async function send(){
    const text = inp.value.trim();
    if(!text) return;
    if(!conversation_id){
      add("Tip", "Klik eerst op Start demo.");
      return;
    }
    inp.value = "";
    add("Jij", text);

    const res = await fetch("/chat", {
      method: "POST",
      headers: {"Content-Type":"application/json"},
      body: JSON.stringify({ conversation_id, message: text })
    });
    if(!res.ok){
      const t = await res.text();
      add("Error", "Chat failed: " + t);
      return;
    }
    const j = await res.json();
    if(j.reply) add("KlusPilot", j.reply);
    if(j.status) statusEl.textContent = j.status;
  }

  document.getElementById("btnStart").addEventListener("click", startDemo);
  document.getElementById("send").addEventListener("click", send);
  document.getElementById("btnReset").addEventListener("click", () => {
    conversation_id = null;
    chatEl.innerHTML = "";
    statusEl.textContent = "—";
    setMeta();
    add("KlusPilot", "Reset klaar. Klik op Start demo.");
  });

  inp.addEventListener("keydown", (e) => { if(e.key === "Enter") send(); });

  add("KlusPilot", "Welkom! Klik op <b>Start demo</b> en typ je eerste bericht.");
</script>
</body>
</html>
"""


# ======================================================================
# ADMIN LOGIN
# ======================================================================

@app.get("/admin/login", response_class=HTMLResponse)
def admin_login_page():
    return """
    <!doctype html>
    <html lang="nl">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width,initial-scale=1"/>
      <title>Admin login</title>
      <style>
        body{font-family:Arial;margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1020;color:#fff}
        .card{width:min(420px,92vw);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:18px}
        label{display:block;font-size:12px;opacity:.85;margin:12px 0 6px}
        input{width:100%;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff}
        button{margin-top:14px;width:100%;padding:12px;border-radius:12px;border:0;background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;font-weight:800;cursor:pointer}
        .muted{font-size:12px;opacity:.75;margin-top:10px}
      </style>
    </head>
    <body>
      <form class="card" method="post" action="/admin/login">
        <h2 style="margin:0 0 8px">Admin</h2>
        <div class="muted">Log in om leads te bekijken en tenants te beheren.</div>
        <label>Gebruikersnaam</label>
        <input name="username" autocomplete="username"/>
        <label>Wachtwoord</label>
        <input name="password" type="password" autocomplete="current-password"/>
        <button type="submit">Inloggen</button>
      </form>
    </body>
    </html>
    """


@app.post("/admin/login")
def admin_login(request: Request, username: str = Form(...), password: str = Form(...)):
    if not check_credentials(username, password):
        return HTMLResponse("Onjuiste gegevens. <a href='/admin/login'>Probeer opnieuw</a>.", status_code=401)
    request.session["is_admin"] = True
    return RedirectResponse(url="/admin/dashboard", status_code=302)


@app.post("/admin/logout")
def admin_logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/admin/login", status_code=302)

# ======================================================================
# ADMIN TENANT MANAGER
# ======================================================================

def _list_tenant_ids() -> List[str]:
    tenants_dir = Path(settings.TENANTS_DIR).resolve()
    if not tenants_dir.exists():
        return []
    items: List[str] = []
    for p in tenants_dir.glob("*.yaml"):
        items.append(p.stem)
    return sorted(set(items))

@app.get("/admin/tenants", response_class=HTMLResponse)
def admin_tenants_page(_=Depends(require_admin)):
    tenant_ids = _list_tenant_ids()
    rows = "\n".join([f"<li><code>{tid}</code></li>" for tid in tenant_ids]) or "<li><i>Geen tenants gevonden</i></li>"

    return HTMLResponse(
        f"""
<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Admin • Tenants</title>
  <style>
    body{{font-family:Arial;margin:0;min-height:100vh;background:#0b1020;color:#fff}}
    .wrap{{max-width:980px;margin:0 auto;padding:18px}}
    .card{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:18px}}
    label{{display:block;font-size:12px;opacity:.85;margin:12px 0 6px}}
    input,textarea{{width:100%;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff}}
    textarea{{min-height:120px;font-family:ui-monospace,Menlo,Consolas,monospace}}
    .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
    @media (max-width:900px){{.row{{grid-template-columns:1fr}}}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}}
    button{{padding:12px 14px;border-radius:12px;border:0;background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;font-weight:800;cursor:pointer}}
    .ghost{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14)}}
    .muted{{font-size:12px;opacity:.75;margin-top:10px}}
    code{{background:rgba(0,0,0,.2);padding:2px 6px;border-radius:8px}}
    a{{color:#fff}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <h2 style="margin:0">Tenants</h2>
        <div style="display:flex;gap:10px;flex-wrap:wrap">
          <a class="ghost" style="display:inline-block;padding:10px 12px;border-radius:12px;text-decoration:none;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.08)" href="/admin/dashboard">← Dashboard</a>
          <form method="post" action="/admin/logout" style="margin:0">
            <button class="ghost" type="submit">Uitloggen</button>
          </form>
        </div>
      </div>

      <h3 style="margin:18px 0 8px">Bestaande tenants</h3>
      <ul style="margin:0 0 14px 18px;padding:0;line-height:1.8">{rows}</ul>

      <hr style="border:0;border-top:1px solid rgba(255,255,255,.14);margin:18px 0">

      <h3 style="margin:0 0 8px">Nieuwe tenant aanmaken</h3>
      <form method="post" action="/admin/tenants/create">
        <div class="row">
          <div>
            <label>tenant_id (subdomain naam, bijv. <code>bedrijf-abc</code>)</label>
            <input name="tenant_id" placeholder="bedrijf-abc" required />
          </div>
          <div>
            <label>Bedrijfsnaam</label>
            <input name="business_name" placeholder="Bedrijf ABC" required />
          </div>
        </div>

        <div class="row">
          <div>
            <label>Notificatie e-mail (optioneel)</label>
            <input name="notify_email" placeholder="leads@bedrijf.nl" />
          </div>
          <div>
            <label>WhatsApp nummer (zonder +, optioneel)</label>
            <input name="whatsapp_number" placeholder="31612345678" />
          </div>
        </div>

        <div class="row">
          <div>
            <label>WhatsApp aan</label>
            <input type="checkbox" name="whatsapp_enabled" value="1" />
          </div>
          <div></div>
        </div>

        <div class="row">
          <div>
            <label>Tenant portal username</label>
            <input name="tenant_admin_username" placeholder="bedrijf" required />
          </div>
          <div>
            <label>Tenant portal password</label>
            <input name="tenant_admin_password" type="password" placeholder="Kies een sterk wachtwoord" required />
          </div>
        </div>

        <label>Diensten (1 per regel: <code>key: label</code>)</label>
        <textarea name="services" placeholder="plumbing: Loodgieter&#10;electric: Elektricien"></textarea>

        <div class="actions">
          <button type="submit">Tenant aanmaken</button>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
        """,
        status_code=200,
    )

@app.post("/admin/tenants/create")
def admin_create_tenant(
    tenant_id: str = Form(...),
    business_name: str = Form(...),
    notify_email: str = Form(default=""),
    whatsapp_enabled: Optional[str] = Form(default=None),
    whatsapp_number: str = Form(default=""),
    tenant_admin_username: str = Form(...),
    tenant_admin_password: str = Form(...),
    services: str = Form(default=""),
    _=Depends(require_admin),
):
    tenant_id = tenant_id.strip()
    tenants_dir = Path(settings.TENANTS_DIR).resolve()
    tenants_dir.mkdir(parents=True, exist_ok=True)
    yaml_path = tenants_dir / f"{tenant_id}.yaml"
    if yaml_path.exists():
        return HTMLResponse(
            f"Tenant bestaat al: <code>{tenant_id}</code>. <a href='/admin/tenants'>Terug</a>",
            status_code=400,
        )

    service_items: List[ServiceItem] = []
    for line in (services or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or ":" not in line:
            continue
        key, label = line.split(":", 1)
        key = key.strip()
        label = label.strip()
        if key and label:
            service_items.append(ServiceItem(key=key, label=label))

    cfg = TenantConfig(
        tenant_id=tenant_id,
        business_name=business_name.strip() or tenant_id,
        notify_email=notify_email.strip() or None,
        whatsapp_enabled=bool(whatsapp_enabled),
        whatsapp_number=whatsapp_number.strip() or None,
        services=service_items,
        tenant_admin_username=tenant_admin_username.strip(),
        tenant_admin_password_hash=hash_password(tenant_admin_password),
    )

    save_tenant(cfg)
    return RedirectResponse(url="/admin/tenants", status_code=302)

# ======================================================================
# TENANT PORTAL (self-service)
# ======================================================================

def require_tenant_admin(request: Request) -> str:
    if not request.session.get("tenant_admin"):
        raise HTTPException(status_code=401, detail="Tenant login required")
    tid = request.session.get("tenant_id")
    if not tid:
        raise HTTPException(status_code=401, detail="Tenant login required")
    return str(tid)

@app.get("/tenant/login", response_class=HTMLResponse)
def tenant_login_page():
    return """
    <!doctype html>
    <html lang="nl">
    <head>
      <meta charset="utf-8"/>
      <meta name="viewport" content="width=device-width,initial-scale=1"/>
      <title>Bedrijfslogin</title>
      <style>
        body{font-family:Arial;margin:0;min-height:100vh;display:grid;place-items:center;background:#0b1020;color:#fff}
        .card{width:min(520px,92vw);background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:18px}
        label{display:block;font-size:12px;opacity:.85;margin:12px 0 6px}
        input{width:100%;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff}
        button{margin-top:14px;width:100%;padding:12px;border-radius:12px;border:0;background:linear-gradient(135deg,#22c55e,#3b82f6);color:#fff;font-weight:800;cursor:pointer}
        .muted{font-size:12px;opacity:.75;margin-top:10px;line-height:1.5}
        code{background:rgba(0,0,0,.2);padding:2px 6px;border-radius:8px}
      </style>
    </head>
    <body>
      <form class="card" method="post" action="/tenant/login">
        <h2 style="margin:0 0 8px">Bedrijf</h2>
        <div class="muted">
          Log in om je wizard/branding/teksten aan te passen.<br/>
          Tip: lokaal test je tenants als <code>bedrijf1.localhost:8000</code>.
        </div>
        <label>Tenant ID</label>
        <input name="tenant_id" placeholder="bijv. demo-company" />
        <label>Gebruikersnaam</label>
        <input name="username" autocomplete="username"/>
        <label>Wachtwoord</label>
        <input name="password" type="password" autocomplete="current-password"/>
        <button type="submit">Inloggen</button>
      </form>
    </body>
    </html>
    """

@app.post("/tenant/login")
def tenant_login(
    request: Request,
    tenant_id: str = Form(...),
    username: str = Form(...),
    password: str = Form(...),
):
    try:
        cfg = load_tenant(tenant_id.strip())
    except FileNotFoundError:
        return HTMLResponse("Onbekende tenant. <a href='/tenant/login'>Probeer opnieuw</a>.", status_code=401)

    if not (cfg.tenant_admin_username and cfg.tenant_admin_password_hash):
        return HTMLResponse("Tenant login is niet ingesteld. Neem contact op met de beheerder.", status_code=401)

    if username != cfg.tenant_admin_username or not verify_password(password, cfg.tenant_admin_password_hash):
        return HTMLResponse("Onjuiste gegevens. <a href='/tenant/login'>Probeer opnieuw</a>.", status_code=401)

    request.session["tenant_admin"] = True
    request.session["tenant_id"] = cfg.tenant_id
    return RedirectResponse(url="/tenant/settings", status_code=302)

@app.post("/tenant/logout")
def tenant_logout(request: Request):
    request.session.pop("tenant_admin", None)
    request.session.pop("tenant_id", None)
    return RedirectResponse(url="/tenant/login", status_code=302)

@app.get("/tenant/settings", response_class=HTMLResponse)
def tenant_settings_page(request: Request):
    tenant_id = require_tenant_admin(request)
    cfg = load_tenant(tenant_id)

    def v(x: Optional[str]) -> str:
        return x or ""

    service_lines = []
    for s in cfg.services or []:
        service_lines.append(f"{s.key} | {s.label} | {s.description or ''} | {s.eta or 'Vandaag'} | {'1' if s.enabled else '0'}")
    services_blob = "\n".join(service_lines)

    return HTMLResponse(
        f"""
<!doctype html>
<html lang="nl">
<head>
  <meta charset="utf-8"/>
  <meta name="viewport" content="width=device-width,initial-scale=1"/>
  <title>Instellingen • {cfg.business_name}</title>
  <style>
    body{{font-family:Arial;margin:0;min-height:100vh;background:#0b1020;color:#fff}}
    .wrap{{max-width:980px;margin:0 auto;padding:18px}}
    .card{{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);border-radius:16px;padding:18px}}
    label{{display:block;font-size:12px;opacity:.85;margin:12px 0 6px}}
    input,textarea{{width:100%;padding:12px;border-radius:12px;border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);color:#fff}}
    textarea{{min-height:120px;font-family:ui-monospace,Menlo,Consolas,monospace}}
    .row{{display:grid;grid-template-columns:1fr 1fr;gap:12px}}
    @media (max-width:900px){{.row{{grid-template-columns:1fr}}}}
    .actions{{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}}
    button{{padding:12px 14px;border-radius:12px;border:0;background:linear-gradient(135deg,#7c3aed,#3b82f6);color:#fff;font-weight:800;cursor:pointer}}
    .ghost{{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.14)}}
    .muted{{font-size:12px;opacity:.75;margin-top:10px;line-height:1.5}}
    .pill{{border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.05);border-radius:999px;padding:6px 10px;font-size:12px;opacity:.9}}
    code{{background:rgba(0,0,0,.2);padding:2px 6px;border-radius:8px}}
    a{{color:#fff}}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <div style="display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap">
        <h2 style="margin:0">Instellingen: {cfg.business_name} <span class="pill">tenant_id: {cfg.tenant_id}</span></h2>
        <form method="post" action="/tenant/logout" style="margin:0"><button class="ghost" type="submit">Uitloggen</button></form>
      </div>

      <form method="post" action="/tenant/settings" enctype="multipart/form-data">
        <h3 style="margin:18px 0 8px">Basis</h3>
        <div class="row">
          <div>
            <label>Bedrijfsnaam</label>
            <input name="business_name" value="{cfg.business_name}"/>
          </div>
          <div>
            <label>Notificatie e-mail (leads)</label>
            <input name="notify_email" value="{v(cfg.notify_email)}"/>
          </div>
        </div>

        <div class="row">
          <div>
            <label>WhatsApp aan</label>
            <input name="whatsapp_enabled" value="1" type="checkbox" {'checked' if cfg.whatsapp_enabled else ''} />
          </div>
          <div>
            <label>WhatsApp nummer (zonder +)</label>
            <input name="whatsapp_number" value="{v(cfg.whatsapp_number)}" placeholder="31612345678"/>
          </div>
        </div>

        <div class="row">
          <div>
            <label>Booking link (Cal.com / Calendly)</label>
            <input name="booking_url" value="{v(getattr(cfg, 'booking_url', None))}" placeholder="https://cal.com/jouwbedrijf/..." />
            <div class="muted">Tip: hiermee kan je AI direct een afspraak-link sturen.</div>
          </div>
          <div></div>
        </div>

        <h3 style="margin:18px 0 8px">Branding</h3>
        <div class="row">
          <div>
            <label>Accent kleur (hex)</label>
            <input name="accent_color" value="{v(cfg.theme.accent_color)}" placeholder="#7c3aed"/>
          </div>
          <div>
            <label>Accent 2 kleur (hex)</label>
            <input name="accent2_color" value="{v(cfg.theme.accent2_color)}" placeholder="#3b82f6"/>
          </div>
        </div>

        <div class="row">
          <div>
            <label>Font family (optioneel)</label>
            <input name="font_family" value="{v(cfg.theme.font_family)}" placeholder="Inter"/>
          </div>
          <div></div>
        </div>

        <div class="row">
          <div>
            <label>Logo upload (png/jpg/webp)</label>
            <input name="logo" type="file" accept="image/*" />
            <div class="muted">Huidig: <code>{v(cfg.theme.logo_url)}</code></div>
          </div>
          <div>
            <label>Achtergrond upload (png/jpg/webp)</label>
            <input name="background" type="file" accept="image/*" />
            <div class="muted">Huidig: <code>{v(cfg.theme.background_url)}</code></div>
          </div>
        </div>

        <h3 style="margin:18px 0 8px">Teksten (wizard)</h3>
        <div class="row">
          <div>
            <label>Headline</label>
            <input name="headline" value="{v(cfg.content.headline)}" placeholder="Snel een vakman nodig?"/>
          </div>
          <div>
            <label>Subheadline</label>
            <input name="subheadline" value="{v(cfg.content.subheadline)}" placeholder="Binnen 2 minuten je aanvraag verstuurd."/>
          </div>
        </div>

        <div class="row">
          <div>
            <label>Panel: Wat gebeurt er na het versturen? (titel)</label>
            <input name="panel_what_next_title" value="{v(cfg.content.panel_what_next_title)}"/>
          </div>
          <div>
            <label>Panel: Tip (titel)</label>
            <input name="panel_tip_title" value="{v(cfg.content.panel_tip_title)}"/>
          </div>
        </div>

        <div class="row">
          <div>
            <label>Panel: Wat gebeurt er na het versturen? (tekst)</label>
            <textarea name="panel_what_next_text">{v(cfg.content.panel_what_next_text)}</textarea>
          </div>
          <div>
            <label>Panel: Tip (tekst)</label>
            <textarea name="panel_tip_text">{v(cfg.content.panel_tip_text)}</textarea>
          </div>
        </div>

        <div class="row">
          <div>
            <label>Privacy regel (stap 4)</label>
            <input name="privacy_line" value="{v(cfg.content.privacy_line)}"/>
          </div>
          <div>
            <label>Succesbericht</label>
            <input name="success_message" value="{v(cfg.content.success_message)}"/>
          </div>
        </div>

        <h3 style="margin:18px 0 8px">Diensten</h3>
        <div class="muted">
          Formaat per regel:<br/>
          <code>key | label | description | eta | enabled(1/0)</code><br/>
          Voorbeeld:<br/>
          <code>plumbing | Loodgieter | Lekkage of verstopping | Vandaag | 1</code>
        </div>
        <textarea name="services">{services_blob}</textarea>

        <div class="actions">
          <button type="submit">Opslaan</button>
          <a class="pill" href="/tenant/public-config?tenant_id={cfg.tenant_id}" target="_blank">Bekijk public config (JSON)</a>
        </div>
      </form>
    </div>
  </div>
</body>
</html>
        """,
        status_code=200,
    )

@app.post("/tenant/settings")
def tenant_settings_save(
    request: Request,
    business_name: str = Form(...),
    notify_email: str = Form(default=""),
    whatsapp_enabled: Optional[str] = Form(default=None),
    whatsapp_number: str = Form(default=""),
    booking_url: str = Form(default=""),

    accent_color: str = Form(default=""),
    accent2_color: str = Form(default=""),
    font_family: str = Form(default=""),

    headline: str = Form(default=""),
    subheadline: str = Form(default=""),
    panel_what_next_title: str = Form(default=""),
    panel_what_next_text: str = Form(default=""),
    panel_tip_title: str = Form(default=""),
    panel_tip_text: str = Form(default=""),
    privacy_line: str = Form(default=""),
    success_message: str = Form(default=""),

    services: str = Form(default=""),
    logo: Optional[UploadFile] = File(default=None),
    background: Optional[UploadFile] = File(default=None),
):
    tenant_id = require_tenant_admin(request)
    cfg = load_tenant(tenant_id)

    cfg.business_name = business_name.strip() or cfg.business_name
    cfg.notify_email = notify_email.strip() or None
    cfg.whatsapp_enabled = bool(whatsapp_enabled)
    cfg.whatsapp_number = whatsapp_number.strip() or None
    cfg.booking_url = booking_url.strip() or None

    cfg.theme.accent_color = accent_color.strip() or None
    cfg.theme.accent2_color = accent2_color.strip() or None
    cfg.theme.font_family = font_family.strip() or None

    cfg.content.headline = headline.strip() or None
    cfg.content.subheadline = subheadline.strip() or None
    cfg.content.panel_what_next_title = panel_what_next_title.strip() or None
    cfg.content.panel_what_next_text = panel_what_next_text.strip() or None
    cfg.content.panel_tip_title = panel_tip_title.strip() or None
    cfg.content.panel_tip_text = panel_tip_text.strip() or None
    cfg.content.privacy_line = privacy_line.strip() or None
    cfg.content.success_message = success_message.strip() or None

    new_services: List[ServiceItem] = []
    for line in (services or "").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = [p.strip() for p in line.split("|")]
        key = parts[0] if len(parts) > 0 else ""
        label = parts[1] if len(parts) > 1 else ""
        desc = parts[2] if len(parts) > 2 else ""
        eta = parts[3] if len(parts) > 3 else "Vandaag"
        enabled = (parts[4] if len(parts) > 4 else "1") != "0"
        if key and label:
            new_services.append(ServiceItem(key=key, label=label, description=desc, eta=eta or "Vandaag", enabled=enabled))
    cfg.services = new_services

    def _save_upload(file: UploadFile, kind: str) -> str:
        ext = (file.filename or "").split(".")[-1].lower() if file.filename else ""
        if ext not in {"png", "jpg", "jpeg", "webp"}:
            ext = "png"
        tdir = TENANT_ASSETS_BASE / tenant_id
        tdir.mkdir(parents=True, exist_ok=True)
        out = tdir / f"{kind}.{ext}"
        with out.open("wb") as f:
            f.write(file.file.read())
        return f"/tenant-assets/{tenant_id}/{out.name}"

    if logo is not None and getattr(logo, "filename", None):
        cfg.theme.logo_url = _save_upload(logo, "logo")

    if background is not None and getattr(background, "filename", None):
        cfg.theme.background_url = _save_upload(background, "background")

    save_tenant(cfg)
    return RedirectResponse(url="/tenant/settings", status_code=302)

@app.get("/tenant/public-config")
def tenant_public_config(request: Request, tenant_id: str = Query(default=None)):
    tid = resolve_tenant_id(request, tenant_id)
    cfg = load_tenant(tid)

    return {
        "tenant_id": cfg.tenant_id,
        "business_name": cfg.business_name,

        "theme": cfg.theme.model_dump(exclude_none=True),
        "content": cfg.content.model_dump(exclude_none=True),

        "services": enabled_services(cfg),

        "whatsapp_enabled": bool(cfg.whatsapp_enabled and cfg.whatsapp_number),
        "whatsapp_number": cfg.whatsapp_number,
        "booking_url": getattr(cfg, "booking_url", None),
    }

# ======================================================================
# CHAT ROUTES
# ======================================================================

@app.post("/chat/start", response_model=ChatStartResponse)
def start_chat(request: Request, req: ChatStartRequest, db: Session = Depends(get_db)):
    tenant_id = resolve_tenant_id(request, req.tenant_id)
    cfg = load_tenant(tenant_id)

    conv = Conversation(tenant_id=tenant_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)

    first = build_welcome(cfg)
    db.add(Message(conversation_id=conv.id, role="assistant", content=first))
    db.commit()

    return {"conversation_id": conv.id, "first_message": first}

@app.post("/chat", response_model=ChatResponse)
def chat_route(req: ChatRequest, db: Session = Depends(get_db)):
    conv = db.get(Conversation, req.conversation_id)
    if not conv:
        raise HTTPException(404, "Conversation not found")

    reply = chat(db, conv, req.message)
    return {"conversation_id": conv.id, "reply": reply, "status": conv.status}

# ======================================================================
# ADMIN EXPORTS
# ======================================================================

@app.get("/admin/leads.csv")
def export_leads(db: Session = Depends(get_db), _=Depends(require_admin)):
    import csv
    from io import StringIO

    rows = (
        db.query(Lead)
        .join(Conversation, Lead.conversation_id == Conversation.id)
        .order_by(Lead.created_at.desc())
        .all()
    )

    buff = StringIO()
    w = csv.writer(buff)
    w.writerow([
        "created_at", "tenant_id", "service_key", "urgency", "issue_summary",
        "name", "phone", "address",
        "status", "summary", "score",
        "contact_preference", "preferred_time", "appointment_status"
    ])

    for lead in rows:
        conv = lead.conversation
        w.writerow([
            lead.created_at.isoformat(),
            conv.tenant_id,
            conv.service_key,
            conv.urgency,
            conv.issue_summary,
            conv.customer_name,
            conv.customer_phone,
            conv.address,
            conv.status,
            lead.summary,
            lead.score,
            lead.contact_preference,
            lead.preferred_time,
            lead.appointment_status,
        ])

    return HTMLResponse(
        content=buff.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": "attachment; filename=leads.csv"},
    )

@app.get("/admin/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db), _=Depends(require_admin)):
    rows = (
        db.query(Lead)
        .join(Conversation, Lead.conversation_id == Conversation.id)
        .order_by(Lead.created_at.desc())
        .limit(250)
        .all()
    )

    leads = []
    for lead in rows:
        conv = lead.conversation
        leads.append({
            "created_at": lead.created_at.isoformat(timespec="seconds"),
            "tenant_id": conv.tenant_id,
            "service_key": conv.service_key or "",
            "urgency": conv.urgency or "",
            "address": conv.address or "",
            "name": conv.customer_name or "",
            "phone": conv.customer_phone or "",
            "status": conv.status or "open",
            "score": lead.score or 0,
            "pref": lead.contact_preference or "",
            "when": lead.preferred_time or "",
            "appt": lead.appointment_status or "new",
            "summary": lead.summary or "",
        })

    return templates.TemplateResponse("dashboard.html", {"request": request, "leads": leads})

class FrontendRequestPayload(BaseModel):
    service_key: Optional[str] = None
    service_label: Optional[str] = None
    postcode: Optional[str] = None
    address: Optional[str] = None
    description: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    tenant_id: Optional[str] = None

@app.post("/request")
def create_request_from_frontend(request: Request, payload: FrontendRequestPayload, db: Session = Depends(get_db)):
    tenant_id = resolve_tenant_id(request, payload.tenant_id)
    cfg = load_tenant(tenant_id)

    conv = Conversation(tenant_id=tenant_id)
    db.add(conv)
    db.commit()
    db.refresh(conv)

    first = build_welcome(cfg)
    db.add(Message(conversation_id=conv.id, role="assistant", content=first))
    db.commit()

    composed = (
        f"Nieuwe aanvraag via wizard.\n"
        f"- Dienst: {payload.service_label or '-'}\n"
        f"- Dienst key: {payload.service_key or '-'}\n"
        f"- Postcode: {payload.postcode or '-'}\n"
        f"- Adres: {payload.address or '-'}\n"
        f"- Omschrijving: {payload.description or '-'}\n"
        f"- Naam: {payload.name or '-'}\n"
        f"- Email: {payload.email or '-'}\n"
        f"- Telefoon: {payload.phone or '-'}\n"
    )

    reply = chat(db, conv, composed)

    if cfg.notify_email:
        subject = f"Nieuwe aanvraag: {payload.service_label or 'Onbekend'} – {payload.postcode or ''}".strip()
        text_body = (
            f"Nieuwe aanvraag via KlusPilot\n\n"
            f"Bedrijf: {cfg.business_name}\n"
            f"Dienst: {payload.service_label or '-'}\n"
            f"Postcode: {payload.postcode or '-'}\n"
            f"Adres: {payload.address or '-'}\n"
            f"Omschrijving: {payload.description or '-'}\n"
            f"Naam: {payload.name or '-'}\n"
            f"E-mail: {payload.email or '-'}\n"
            f"Telefoon: {payload.phone or '-'}\n\n"
            f"Conversation ID: {conv.id}\n"
        )
        send_lead_email(cfg.notify_email, subject, text_body)

    return {
        "ok": True,
        "conversation_id": conv.id,
        "first_message": first,
        "reply": reply,
        "status": conv.status,
        "business_name": cfg.business_name,
        "booking_url": getattr(cfg, "booking_url", None),
    }