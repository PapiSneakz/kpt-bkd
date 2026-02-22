from fastapi import Request, HTTPException
from .config import settings


def require_admin(request: Request):
    if not request.session.get("is_admin"):
        raise HTTPException(status_code=401, detail="Not logged in")


def check_credentials(username: str, password: str) -> bool:
    return username == settings.ADMIN_USER and password == settings.ADMIN_PASS
