# app/routes/auth.py

import secrets

import requests
from fastapi import APIRouter, HTTPException
from fastapi.responses import RedirectResponse

from app.auth.github_oauth import build_authorize_url, exchange_code_for_token
from app.storage import db

router = APIRouter(prefix="/auth/github", tags=["auth"])

# In-memory set of states issued but not yet consumed by a callback.
# Fine for a single-process local app; a multi-instance deployment would
# need a shared store (Redis, DB row) instead so any instance can validate
# a callback regardless of which one issued the login redirect.
_pending_states: set[str] = set()


@router.get("/login")
def github_login():
    state = secrets.token_urlsafe(16)
    _pending_states.add(state)
    return RedirectResponse(build_authorize_url(state))


@router.get("/callback")
def github_callback(code: str, state: str):
    if state not in _pending_states:
        raise HTTPException(status_code=400, detail="Invalid or expired state")
    _pending_states.discard(state)

    access_token = exchange_code_for_token(code)

    user_resp = requests.get(
        "https://api.github.com/user",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/vnd.github.v3+json",
        },
    )
    user_resp.raise_for_status()
    github_username = user_resp.json()["login"]

    db.save_github_token(access_token, github_username)

    return {"connected": True, "github_username": github_username}
