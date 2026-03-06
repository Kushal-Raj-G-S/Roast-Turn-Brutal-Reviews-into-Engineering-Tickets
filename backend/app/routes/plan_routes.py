"""
Plan management routes.

GET  /user/plan  — current plan + usage for the authenticated user
POST /user/plan  — update plan (mock — no payment validation)
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlmodel import Session, select, func

from app.database.auth_supabase import get_current_user
from app.models.models_supabase import Profile
from app.models.bulk_models import Upload
from app.core.plans import VALID_PLANS, get_limits

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/user", tags=["plan"])


# ---------------------------------------------------------------------------
# Response / Request schemas
# ---------------------------------------------------------------------------

class PlanResponse(BaseModel):
    plan: str
    label: str
    uploads_used: int
    uploads_limit: int | None      # None = unlimited
    reviews_limit: int | None      # None = unlimited
    reset_date: str                # ISO date — first day of next month


class PlanUpdateRequest(BaseModel):
    plan: str


class PlanUpdateResponse(BaseModel):
    success: bool
    plan: str
    message: str


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_bulk_session():
    """Re-use the same engine the bulk API created."""
    from app.api.bulk_api import get_engine_instance
    engine = get_engine_instance()
    if not engine:
        raise HTTPException(status_code=503, detail="Database not initialised")
    with Session(engine) as session:
        yield session


def _month_upload_count(session: Session, user_id) -> int:
    """Count completed/processing uploads for the current calendar month."""
    now = datetime.now(timezone.utc)
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    result = session.exec(
        select(func.count(Upload.id)).where(
            Upload.user_id == user_id,
            Upload.created_at >= month_start,
        )
    ).one()
    return result or 0


def _next_reset() -> str:
    now = datetime.now(timezone.utc)
    if now.month == 12:
        return datetime(now.year + 1, 1, 1).date().isoformat()
    return datetime(now.year, now.month + 1, 1).date().isoformat()


# ---------------------------------------------------------------------------
# GET /user/plan
# ---------------------------------------------------------------------------

@router.get("/plan", response_model=PlanResponse)
async def get_user_plan(
    session: Session = Depends(_get_bulk_session),
    user: Profile = Depends(get_current_user),
):
    """Return the current plan and this month's upload usage."""
    plan = getattr(user, "plan", "free") or "free"
    limits = get_limits(plan)

    uploads_used = _month_upload_count(session, user.id)

    return PlanResponse(
        plan=plan,
        label=limits["label"],
        uploads_used=uploads_used,
        uploads_limit=limits["uploads_per_month"],
        reviews_limit=limits["max_reviews"],
        reset_date=_next_reset(),
    )


# ---------------------------------------------------------------------------
# POST /user/plan
# ---------------------------------------------------------------------------

@router.post("/plan", response_model=PlanUpdateResponse)
async def update_user_plan(
    body: PlanUpdateRequest,
    session: Session = Depends(_get_bulk_session),
    user: Profile = Depends(get_current_user),
):
    """
    Update the user's plan.

    This is a mock endpoint — no payment validation is performed.
    A real Stripe webhook would call the same DB update.
    """
    new_plan = body.plan.lower()
    if new_plan not in VALID_PLANS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid plan '{new_plan}'. Valid options: {', '.join(VALID_PLANS)}",
        )

    # Update profile in DB
    from app.models.models_supabase import Profile as ProfileModel
    from sqlalchemy import update as sa_update

    session.execute(
        sa_update(ProfileModel)
        .where(ProfileModel.id == user.id)
        .values(plan=new_plan)
    )
    session.commit()

    logger.info(f"User {user.id} plan updated → {new_plan}")

    return PlanUpdateResponse(
        success=True,
        plan=new_plan,
        message=f"Plan updated to {new_plan.capitalize()} successfully.",
    )
