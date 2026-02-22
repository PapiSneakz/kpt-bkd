from typing import Any
from .tenant_config import TenantConfig, enabled_services

SYSTEM_BASE = """Je bent KlusPilot: een professionele lead- en intake-assistent voor een Nederlands installatiebedrijf.
Doel: (1) snel kwalificeren, (2) gegevens verzamelen, (3) afspraak of terugbelverzoek regelen,
(4) veilige prijsindicatie "vanaf" geven indien mogelijk, (5) vertrouwen geven.

Stijl:
- Kort, vriendelijk, zakelijk.
- Stel 1 vraag tegelijk.
- Gebruik keuzes/knoppen als tekstlijsten.

Regels:
- Vraag altijd: spoed ja/nee, dienst (categorie), postcode+huisnummer, naam, telefoon.
- Geef nooit harde diagnose; gebruik "waarschijnlijk" en "indicatie".
- Bij direct gevaar: adviseer veilig handelen en bij acuut gevaar 112.
- Output altijd Nederlands.
"""


def build_welcome(cfg: TenantConfig) -> str:
    lines = [
        f"Hi! Ik ben **KlusPilot**, de assistent van **{cfg.business_name}**.",
        "Waar kunnen we je mee helpen? Kies een optie:"
    ]
    for s in enabled_services(cfg):
        lines.append(f"- {s['label']}")
    lines.append("\nIs het **spoed**? (Ja/Nee)")
    return "\n".join(lines)


def service_labels(cfg: TenantConfig) -> dict[str, str]:
    return {s["key"]: s["label"] for s in enabled_services(cfg)}


def emergency_safety_text(service_key: str | None) -> str:
    if service_key == "plumbing":
        return "Bij veel water/lekkage: draai de **hoofdkraan** dicht en zet apparaten uit waar mogelijk."
    if service_key == "electric":
        return "Bij gevaar: schakel de **groep/hoofschakelaar** uit. Raak niets nats aan."
    if service_key in ("heating", "hvac"):
        return "Bij gaslucht/rook: ventileer, bedien geen schakelaars. Bij direct gevaar: **112**."
    return "Bij direct gevaar: **112**."


def price_hint(cfg: TenantConfig, service_key: str | None, extra: dict[str, Any]) -> str | None:
    if not service_key:
        return None

    svc = next((s for s in enabled_services(cfg) if s.get("key") == service_key), None)
    if not svc:
        return None

    p = svc.get("pricing", {}) or {}

    if service_key == "plumbing":
        where = (extra.get("where") or "").lower()
        if "wc" in where:
            return f"Indicatie: vanaf €{p.get('wc_from', 130)} + eventuele materialen."
        if "hoofd" in where or "meerdere" in where:
            return f"Indicatie: vanaf €{p.get('main_drain_from', 180)} + eventuele materialen."
        return f"Indicatie: vanaf €{p.get('sink_from', 110)} + eventuele materialen."

    if service_key == "electric":
        issue = (extra.get("issue") or "").lower()
        if "kortsluit" in issue:
            return f"Indicatie: vanaf €{p.get('short_circuit_from', 165)} + eventuele materialen."
        return f"Indicatie: vanaf €{p.get('outage_from', 150)} + eventuele materialen."

    if service_key == "heating":
        issue = (extra.get("issue") or "").lower()
        if "geen warmte" in issue or "koud" in issue:
            return f"Inspectie: vanaf €{p.get('no_heat_inspection_from', 95)} (excl. onderdelen)."
        return f"Inspectie: vanaf €{p.get('boiler_inspection_from', 110)} (excl. onderdelen)."

    if service_key == "hvac":
        want = (extra.get("want") or "").lower()
        if "onderhoud" in want:
            return f"Onderhoud: vanaf €{p.get('maintenance_from', 145)}."
        return f"Inspectie: vanaf €{p.get('inspection_from', 110)}."

    if service_key == "sanitary":
        want = (extra.get("want") or "").lower()
        if "install" in want:
            return f"Indicatie: vanaf €{p.get('install_from', 195)} + eventuele materialen."
        return f"Indicatie: vanaf €{p.get('repair_from', 120)} + eventuele materialen."

    if service_key == "solar":
        want = (extra.get("want") or "").lower()
        if "advies" in want or "consult" in want:
            return f"Advies/consult: vanaf €{p.get('consult_from', 75)}."
        return f"Inspectie: vanaf €{p.get('inspection_from', 120)}."

    return None
