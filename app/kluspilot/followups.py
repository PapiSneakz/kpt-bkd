FOLLOWUP_2H = "Hoi! Zal ik een tijdslot reserveren? Dan ben je verzekerd van hulp."
FOLLOWUP_24H = "Wil je dat we dit nog oppakken? Ik kan ook een plek voor morgen plannen."

def followup_message(hours: int) -> str:
    return FOLLOWUP_2H if hours == 2 else FOLLOWUP_24H
