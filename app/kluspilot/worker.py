from __future__ import annotations

from datetime import datetime, timedelta

from celery import Celery
from sqlalchemy.orm import Session

from .config import settings
from .db import SessionLocal
from .models import Lead, Conversation
from .tenant_config import load_tenant
from .notify import send_lead_email


celery_app = Celery("kluspilot", broker=settings.REDIS_URL, backend=settings.REDIS_URL)


def _db() -> Session:
    return SessionLocal()


@celery_app.task
def notify_new_lead(lead_id: str) -> None:
    db = _db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead:
            return
        conv = lead.conversation
        cfg = load_tenant(conv.tenant_id)

        if not cfg.notify_email:
            return

        subject = f"Nieuwe lead: {conv.service_key or 'Onbekend'} – {conv.address or ''}".strip()
        text_body = (
            f"Nieuwe lead via KlusPilot\n\n"
            f"Bedrijf: {cfg.business_name}\n"
            f"Dienst: {conv.service_key or '-'}\n"
            f"Spoed: {conv.urgency or '-'}\n"
            f"Probleem: {conv.issue_summary or '-'}\n"
            f"Adres: {conv.address or '-'}\n"
            f"Naam: {conv.customer_name or '-'}\n"
            f"Telefoon: {conv.customer_phone or '-'}\n"
            f"Status: {conv.status}\n"
            f"Score: {lead.score}\n\n"
            f"Conversation ID: {conv.id}\n"
        )

        send_lead_email(cfg.notify_email, subject, text_body)

    finally:
        db.close()


@celery_app.task
def _scan_followup_2h() -> None:
    db = _db()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=2)
        leads = (
            db.query(Lead)
            .join(Conversation, Lead.conversation_id == Conversation.id)
            .filter(Lead.followup_2h_sent == False)  # noqa
            .filter(Lead.created_at <= cutoff)
            .filter(Conversation.status.in_(["open", "needs_call"]))
            .all()
        )
        for lead in leads:
            followup_2h_if_needed.delay(lead.id)
    finally:
        db.close()


@celery_app.task
def followup_2h_if_needed(lead_id: str) -> None:
    db = _db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead or lead.followup_2h_sent:
            return
        conv = lead.conversation
        cfg = load_tenant(conv.tenant_id)

        if cfg.notify_email:
            msg = (
                f"Follow-up (2 uur): lead nog open\n\n"
                f"Dienst: {conv.service_key or '-'}\n"
                f"Naam: {conv.customer_name or '-'}\n"
                f"Telefoon: {conv.customer_phone or '-'}\n"
                f"Adres: {conv.address or '-'}\n"
                f"Conversation ID: {conv.id}\n"
            )
            send_lead_email(cfg.notify_email, "Follow-up 2 uur – lead open", msg)

        lead.followup_2h_sent = True
        db.commit()

    finally:
        db.close()


@celery_app.task
def _scan_followup_24h() -> None:
    db = _db()
    try:
        cutoff = datetime.utcnow() - timedelta(hours=24)
        leads = (
            db.query(Lead)
            .join(Conversation, Lead.conversation_id == Conversation.id)
            .filter(Lead.followup_24h_sent == False)  # noqa
            .filter(Lead.created_at <= cutoff)
            .filter(Conversation.status.in_(["open", "needs_call"]))
            .all()
        )
        for lead in leads:
            followup_24h_if_needed.delay(lead.id)
    finally:
        db.close()


@celery_app.task
def followup_24h_if_needed(lead_id: str) -> None:
    db = _db()
    try:
        lead = db.get(Lead, lead_id)
        if not lead or lead.followup_24h_sent:
            return
        conv = lead.conversation
        cfg = load_tenant(conv.tenant_id)

        if cfg.notify_email:
            msg = (
                f"Follow-up (24 uur): lead nog open\n\n"
                f"Dienst: {conv.service_key or '-'}\n"
                f"Naam: {conv.customer_name or '-'}\n"
                f"Telefoon: {conv.customer_phone or '-'}\n"
                f"Adres: {conv.address or '-'}\n"
                f"Conversation ID: {conv.id}\n"
            )
            send_lead_email(cfg.notify_email, "Follow-up 24 uur – lead open", msg)

        lead.followup_24h_sent = True
        db.commit()

    finally:
        db.close()


celery_app.conf.beat_schedule = {
    "scan-followup-2h-every-10m": {
        "task": "kluspilot.worker._scan_followup_2h",
        "schedule": 600.0,
    },
    "scan-followup-24h-every-30m": {
        "task": "kluspilot.worker._scan_followup_24h",
        "schedule": 1800.0,
    },
}