from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, Request, Response, status
from sqlalchemy.orm import Session

from codeverse_api.config import get_settings, Settings
from codeverse_api.dependencies import get_db
from codeverse_api.db.models import User
from codeverse_api.security.auth import create_access_token

router = APIRouter(prefix="/auth", tags=["auth"])

_VISITOR_COOKIE = "cv_uid"
_VISITOR_COOKIE_MAX_AGE = 60 * 60 * 24 * 30  # 30 days


@router.post("/token", status_code=status.HTTP_200_OK)
def get_developer_token(
    request: Request,
    response: Response,
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
):
    if settings.public_demo:
        user = _visitor_user(request, db)
        # HttpOnly cookie keeps the same visitor on the same account across
        # page reloads (same-origin deploys send it automatically); each new
        # visitor gets a fresh, isolated account.
        response.set_cookie(
            _VISITOR_COOKIE,
            str(user.id),
            max_age=_VISITOR_COOKIE_MAX_AGE,
            httponly=True,
            samesite="lax",
        )
    else:
        user = _shared_dev_user(db)

    token = create_access_token(user.id, settings)
    return {
        "access_token": token,
        "token_type": "bearer",
        "user": {
            "id": str(user.id),
            "email": user.email,
            "display_name": user.display_name,
        }
    }


def _shared_dev_user(db: Session) -> User:
    """Local development: one stable account so your test themes persist."""
    dev_email = "dev@codeverse.io"
    user = db.query(User).filter(User.email == dev_email).first()
    if not user:
        user = User(email=dev_email, display_name="Developer User")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


def _visitor_user(request: Request, db: Session) -> User:
    """Public demo: reuse the cookie's account when valid, else mint a new
    anonymous visitor so strangers never share a workspace."""
    raw_cookie = request.cookies.get(_VISITOR_COOKIE)
    if raw_cookie:
        try:
            existing = db.get(User, uuid.UUID(raw_cookie))
        except ValueError:
            existing = None
        if existing is not None:
            return existing

    user = User(
        email=f"visitor-{uuid.uuid4().hex[:12]}@demo.codeverse.io",
        display_name="Visitor",
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user
