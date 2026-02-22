from __future__ import annotations

from dataclasses import dataclass
from typing import List

from .models import Conversation, Lead


@dataclass
class StateResult:
    state: str
    missing: List[str]


def compute_state(conv: Conversation, lead: Lead) -> StateResult:
    # service
    if not conv.service_key:
        return StateResult("SERVICE_SELECTION", ["service_key"])

    # urgency
    if not conv.urgency:
        return StateResult("URGENCY_CHECK", ["urgency"])

    # details
    if not conv.issue_summary:
        return StateResult("DETAILS_COLLECTION", ["issue_summary"])

    # address
    if not conv.address:
        return StateResult("ADDRESS_COLLECTION", ["address"])

    # contact
    if not conv.customer_name:
        return StateResult("CONTACT_COLLECTION", ["customer_name"])
    if not conv.customer_phone:
        return StateResult("CONTACT_COLLECTION", ["customer_phone"])

    # availability
    if not lead.preferred_time:
        return StateResult("AVAILABILITY_COLLECTION", ["preferred_time"])

    return StateResult("READY_TO_SCHEDULE", [])
