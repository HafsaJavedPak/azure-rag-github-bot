# app/config.py

import os
from dotenv import load_dotenv

load_dotenv()  # reads .env into the process environment — no-op in prod if vars are set another way

GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")

if not GITHUB_TOKEN:
    raise RuntimeError(
        "GITHUB_TOKEN is not set. Add it to .env (GITHUB_TOKEN=your_personal_access_token)."
    )

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not GEMINI_API_KEY:
    raise RuntimeError(
        "GEMINI_API_KEY is not set. Add it to .env (GEMINI_API_KEY=your_api_key)."
    )

GITHUB_CLIENT_ID = os.getenv("GITHUB_CLIENT_ID")

if not GITHUB_CLIENT_ID:
    raise RuntimeError(
        "GITHUB_CLIENT_ID is not set. Add it to .env (GITHUB_CLIENT_ID=your_oauth_app_client_id)."
    )

GITHUB_CLIENT_SECRET = os.getenv("GITHUB_CLIENT_SECRET")

if not GITHUB_CLIENT_SECRET:
    raise RuntimeError(
        "GITHUB_CLIENT_SECRET is not set. Add it to .env (GITHUB_CLIENT_SECRET=your_oauth_app_client_secret)."
    )

# Not a secret — safe to default rather than require, unlike the two above.
GITHUB_OAUTH_REDIRECT_URI = os.getenv(
    "GITHUB_OAUTH_REDIRECT_URI", "http://127.0.0.1:8000/auth/github/callback"
)
