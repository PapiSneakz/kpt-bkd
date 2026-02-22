from typing import Optional

from .config import settings


def twilio_configured() -> bool:
    return bool(settings.TWILIO_ACCOUNT_SID and settings.TWILIO_AUTH_TOKEN and settings.TWILIO_WHATSAPP_FROM)


def send_whatsapp(to_number: str, body: str) -> Optional[str]:
    """
    to_number example: "31612345678" or "+31612345678"
    returns message SID if sent, else None
    """
    if not twilio_configured():
        return None

    # Lazy import so requirements only matters when enabled
    from twilio.rest import Client

    to = to_number.strip()
    if not to.startswith("+"):
        to = "+" + to
    if not to.startswith("+") or len(to) < 8:
        return None

    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    msg = client.messages.create(
        from_=settings.TWILIO_WHATSAPP_FROM,
        to=f"whatsapp:{to}",
        body=body,
    )
    return msg.sid