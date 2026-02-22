from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import String, DateTime, Text, ForeignKey, Boolean, Integer, JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    tenant_id: Mapped[str] = mapped_column(String, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    last_activity_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    urgency: Mapped[str | None] = mapped_column(String, nullable=True)          # "spoed" / "niet_spoed"
    service_key: Mapped[str | None] = mapped_column(String, nullable=True)      # plumbing/electric/heating/...
    issue_summary: Mapped[str | None] = mapped_column(String, nullable=True)

    address: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_name: Mapped[str | None] = mapped_column(String, nullable=True)
    customer_phone: Mapped[str | None] = mapped_column(String, nullable=True)

    extra: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String, default="open")                 # open, booked, needs_call, closed

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan"
    )
    lead: Mapped[Optional["Lead"]] = relationship(
        back_populates="conversation",
        uselist=False
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), index=True)

    role: Mapped[str] = mapped_column(String)  # user/assistant
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class Lead(Base):
    __tablename__ = "leads"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    conversation_id: Mapped[str] = mapped_column(ForeignKey("conversations.id"), unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    summary: Mapped[str] = mapped_column(Text, default="")
    score: Mapped[int] = mapped_column(Integer, default=0)

    contact_preference: Mapped[str] = mapped_column(String, default="call")  # call|whatsapp|email
    preferred_time: Mapped[str | None] = mapped_column(String, nullable=True)
    appointment_status: Mapped[str] = mapped_column(String, default="new")  # new|needs_call|booked|closed

    followup_2h_sent: Mapped[bool] = mapped_column(Boolean, default=False)
    followup_24h_sent: Mapped[bool] = mapped_column(Boolean, default=False)

    conversation: Mapped["Conversation"] = relationship(back_populates="lead")
    appointments: Mapped[list["Appointment"]] = relationship(
        back_populates="lead",
        cascade="all, delete-orphan"
    )


class Appointment(Base):
    __tablename__ = "appointments"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    lead_id: Mapped[str] = mapped_column(ForeignKey("leads.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    # Afspraken info (optioneel)
    date: Mapped[str | None] = mapped_column(String, nullable=True)   # bijv "2026-02-20"
    time: Mapped[str | None] = mapped_column(String, nullable=True)   # bijv "14:00"
    notes: Mapped[str] = mapped_column(Text, default="")

    lead: Mapped["Lead"] = relationship(back_populates="appointments")