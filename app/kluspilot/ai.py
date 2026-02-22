from __future__ import annotations

import json
from datetime import datetime

from sqlalchemy.orm import Session
from openai import OpenAI

from .config import settings
from .models import Conversation, Message, Lead, Appointment
from .tenant_config import load_tenant, TenantConfig
from .flows import SYSTEM_BASE, service_labels, emergency_safety_text, price_hint

client = OpenAI(api_key=settings.OPENAI_API_KEY)

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "update_intake",
            "description": "Update intake fields when user provides them.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urgency": {"type": "string", "enum": ["spoed", "niet_spoed"]},
                    "service_key": {"type": "string"},
                    "issue_summary": {"type": "string"},
                    "address": {"type": "string"},
                    "customer_name": {"type": "string"},
                    "customer_phone": {"type": "string"},
                    "contact_preference": {"type": "string", "enum": ["call", "whatsapp", "email"]},
                    "preferred_time": {"type": "string"},
                    "status": {"type": "string", "enum": ["open", "booked", "needs_call", "closed"]},
                    "extra": {"type": "object"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_appointment",
            "description": "Create an appointment request for the lead.",
            "parameters": {
                "type": "object",
                "properties": {
                    "date": {"type": "string"},
                    "time": {"type": "string"},
                    "notes": {"type": "string"},
                },
            },
        },
    },
]


def ensure_lead(db: Session, conv: Conversation) -> Lead:
    if conv.lead:
        return conv.lead
    lead = Lead(conversation_id=conv.id)
    db.add(lead)
    db.commit()
    db.refresh(lead)
    return lead


def build_system_prompt(cfg: TenantConfig) -> str:
    labels = service_labels(cfg)
    services_text = "\n".join([f"- {k}: {v}" for k, v in labels.items()])

    booking_url = (cfg.booking_url or "").strip()
    booking_line = ""
    if booking_url:
        booking_line = f"\n\nAls intake compleet is, bied afspraak plannen aan via: {booking_url}"

    return (
        SYSTEM_BASE
        + "\n\nBeschikbare diensten (service_key → label):\n"
        + services_text
        + "\n\nAls service_key onbekend is: laat gebruiker kiezen uit de labels."
        + "\n\nVraag per dienst kort door:"
        + "\n- plumbing: waar (wc/keuken/douche/hoofdafvoer), verstopt/lekkage, foto optioneel"
        + "\n- electric: storing/kortsluiting/stopcontact, veiligheid"
        + "\n- heating: geen warmte/storing, toesteltype, foutcode optioneel"
        + "\n- hvac: storing of onderhoud, merk optioneel"
        + "\n- sanitary: installatie of reparatie, wat precies"
        + "\n- solar: storing/inspectie/advies, omvormer merk optioneel"
        + "\n\nAltijd eindigen met: afspraak/terugbellen + NAAM/TELEFOON/POSTCODE+HUISNR."
        + "\n\nAls het probleem beter zichtbaar is met foto/video: vraag of ze willen uploaden."
        + booking_line
    )


def _extract_text_from_chat_completion(resp) -> str:
    if not resp or not resp.choices:
        return ""
    msg = resp.choices[0].message
    return msg.content or ""


def chat(db: Session, conv: Conversation, user_message: str) -> str:
    # BELANGRIJK: cfg blijft TenantConfig (geen dict)
    cfg = load_tenant(conv.tenant_id)

    db.add(Message(conversation_id=conv.id, role="user", content=user_message))
    conv.last_activity_at = datetime.utcnow()
    db.commit()

    msgs = (
        db.query(Message)
        .filter(Message.conversation_id == conv.id)
        .order_by(Message.created_at.asc())
        .all()
    )

    input_messages = [{"role": "system", "content": build_system_prompt(cfg)}]
    for m in msgs[-24:]:
        input_messages.append(
            {"role": "user" if m.role == "user" else "assistant", "content": m.content}
        )

    resp = client.chat.completions.create(
        model=settings.OPENAI_MODEL,
        messages=input_messages,
        tools=TOOLS,
        tool_choice="auto",
    )

    reply_text = _extract_text_from_chat_completion(resp)

    tool_calls = (resp.choices[0].message.tool_calls or []) if resp.choices else []
    lead = ensure_lead(db, conv)

    for tc in tool_calls:
        if tc.function.name == "update_intake":
            args = tc.function.arguments or "{}"
            if isinstance(args, str):
                args = json.loads(args)

            if "urgency" in args:
                conv.urgency = args["urgency"]
            if "service_key" in args:
                conv.service_key = args["service_key"]
            if "issue_summary" in args:
                conv.issue_summary = args["issue_summary"]
            if "address" in args:
                conv.address = args["address"]
            if "customer_name" in args:
                conv.customer_name = args["customer_name"]
            if "customer_phone" in args:
                conv.customer_phone = args["customer_phone"]
            if "status" in args:
                conv.status = args["status"]

            if "contact_preference" in args:
                lead.contact_preference = args["contact_preference"]
            if "preferred_time" in args:
                lead.preferred_time = args["preferred_time"]

            if "extra" in args and isinstance(args["extra"], dict):
                merged = dict(conv.extra or {})
                merged.update(args["extra"])
                conv.extra = merged

            db.commit()

        if tc.function.name == "create_appointment":
            args = tc.function.arguments or "{}"
            if isinstance(args, str):
                args = json.loads(args)

            ap = Appointment(
                lead_id=lead.id,
                date=args.get("date"),
                time=args.get("time"),
                notes=args.get("notes") or "",
            )
            db.add(ap)
            lead.appointment_status = "needs_call"
            conv.status = "needs_call"
            db.commit()

    if conv.urgency == "spoed":
        safety = emergency_safety_text(conv.service_key)
        if safety and safety.lower() not in reply_text.lower():
            reply_text = f"{reply_text}\n\n{safety}"

    hint = price_hint(cfg, conv.service_key, conv.extra or {})
    if hint and ("indicatie" not in reply_text.lower()) and ("inspectie" not in reply_text.lower()):
        reply_text += f"\n\n{hint} (Definitieve prijs na inspectie.)"

    booking_url = (cfg.booking_url or "").strip()
    core_ok = bool(conv.service_key and conv.urgency and conv.address and conv.customer_phone)
    if core_ok and booking_url and ("http" in booking_url) and (booking_url not in reply_text):
        reply_text += f"\n\nWil je direct een afspraak plannen? Dat kan hier: {booking_url}"

    db.add(Message(conversation_id=conv.id, role="assistant", content=reply_text))
    db.commit()

    score = 0
    if conv.service_key:
        score += 15
    if conv.urgency:
        score += 10
    if conv.issue_summary:
        score += 10
    if conv.address:
        score += 20
    if conv.customer_phone:
        score += 35
    if conv.status in ("booked", "needs_call"):
        score += 20

    lead.score = min(score, 100)
    lead.summary = (
        f"{conv.service_key or 'onbekend'} | {conv.urgency or 'onbekend'} | "
        f"{conv.issue_summary or ''} | {conv.address or ''}"
    )
    db.commit()

    return reply_text