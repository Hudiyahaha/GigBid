from __future__ import annotations

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select

from apps.api.auth import token_store
from apps.api.db import SavedSearch, User, UserSettings, session
from apps.api.schemas import Credentials, Onboarding, Simple, TokenOut
from apps.api.security import check_pw, current_user, hash_pw, issue

router = APIRouter(prefix="/auth", tags=["auth"])


def user_out(u: User) -> dict:
    return {"id": u.id, "email": u.email, "display_name": u.display_name, "persona": u.persona, "onboarded": u.onboarded,
            "connected": token_store.connected(u.id)}


@router.post("/register", response_model=TokenOut)
def register(c: Credentials) -> TokenOut:
    with session() as s:
        if s.execute(select(User).where(User.email == c.email.lower())).scalar_one_or_none():
            raise HTTPException(409, "email already registered")
        u = User(id="u-" + uuid.uuid4().hex[:10], email=c.email.lower(), password_hash=hash_pw(c.password),
                 display_name=c.display_name or c.email.split("@")[0])
        s.add(u)
        s.add(UserSettings(user_id=u.id))
    return TokenOut(token=issue(u.id), user=user_out(u))


@router.post("/login", response_model=TokenOut)
def login(c: Credentials) -> TokenOut:
    with session() as s:
        u = s.execute(select(User).where(User.email == c.email.lower())).scalar_one_or_none()
    if not u or not check_pw(c.password, u.password_hash):
        raise HTTPException(401, "wrong email or password")
    return TokenOut(token=issue(u.id), user=user_out(u))


@router.get("/me")
def me(u: User = Depends(current_user)) -> dict:
    return user_out(u)


@router.post("/onboarding")
def onboarding(o: Onboarding, u: User = Depends(current_user)) -> dict:
    with session() as s:
        user = s.get(User, u.id)
        user.persona, user.onboarded = o.persona, True
        st = s.get(UserSettings, u.id) or UserSettings(user_id=u.id)
        st.hourly_floor, st.min_project, st.weekly_connects_budget = o.hourly_floor, o.min_project, o.weekly_connects_budget
        st.marketplace_mode = o.marketplace
        s.merge(st)
        for q in o.saved_searches[:10]:
            s.add(SavedSearch(user_id=u.id, query=q[:200], interval_minutes=60))
    if o.marketplace == "gigsim":
        # GigSim demo accounts exist per persona; a user may paste their own GigSim token instead
        token_store.put(u.id, "gigsim", {"token": o.gigsim_token or f"gigsim-dev-token-{o.persona}"})
    with session() as s:
        return user_out(s.get(User, u.id))


@router.get("/upwork/start")
async def upwork_start(u: User = Depends(current_user)) -> dict:
    """Begin the OAuth 2.1 flow with Upwork's official MCP server; the UI opens the returned URL."""
    import asyncio

    from mcp_servers.marketplace.adapters.upwork_live import PENDING_AUTH, UpworkLiveAdapter
    adapter = UpworkLiveAdapter(u.id)
    task = asyncio.create_task(adapter._load_tools())
    for _ in range(100):
        if u.id in PENDING_AUTH or task.done():
            break
        await asyncio.sleep(0.1)
    if u.id in PENDING_AUTH:
        return {"authorize_url": PENDING_AUTH[u.id]["url"]}
    if task.done() and not task.exception():
        return {"connected": True}
    raise HTTPException(502, f"could not start Upwork OAuth: {task.exception() if task.done() else 'timeout'}")


@router.get("/upwork/callback")
async def upwork_callback(request: Request, code: str, state: str | None = None) -> RedirectResponse:
    from mcp_servers.marketplace.adapters.upwork_live import PENDING_AUTH
    for _uid, pending in list(PENDING_AUTH.items()):
        if not pending["future"].done():
            pending["future"].set_result((code, state))
    return RedirectResponse("/settings?upwork=connected")


@router.delete("/connections/{provider}", response_model=Simple)
def disconnect(provider: str, u: User = Depends(current_user)) -> Simple:
    token_store.delete(u.id, provider)
    return Simple()
