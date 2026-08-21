"""Role review: any user can hold any combination of hats — base role
(admin/manager/instructor/member), studio owner, studio manager, and
franchise owner. This endpoint shows the full picture per user, e.g. a user
who is both a studio owner and an instructor.
"""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session as DBSession

from app.dependencies import get_current_user, get_db, require_admin, get_operating_studio_id
from app.models.franchise import Franchise
from app.models.franchise_owner import FranchiseOwner
from app.models.studio import Studio
from app.models.studio_owner import StudioOwner
from app.models.user import User

router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("/summary")
def roles_summary(db: DBSession = Depends(get_db), _: User = Depends(require_admin)):
    studios = {s.id: s.display_name or s.name for s in db.query(Studio).all()}
    franchises = {f.id: f.name for f in db.query(Franchise).all()}

    studio_roles = {}
    for row in db.query(StudioOwner).filter(StudioOwner.is_active == True).all():
        studio_roles.setdefault(row.user_id, []).append(
            {"level": row.level or "owner", "studio": studios.get(row.studio_id, "?")}
        )

    franchise_roles = {}
    for row in db.query(FranchiseOwner).filter(FranchiseOwner.is_active == True).all():
        franchise_roles.setdefault(row.user_id, []).append(
            {"name": franchises.get(row.franchise_id, "?"), "level": row.level or "manager"})

    from app.models.user_studio import UserStudio
    member_studios = {}
    for row in db.query(UserStudio).filter(UserStudio.is_active == True).all():
        member_studios.setdefault(row.user_id, []).append(str(row.studio_id))

    users = db.query(User).order_by(User.name).all()
    return {
        "users": [
            {
                "user_id": str(u.id),
                "name": u.name,
                "email": u.email,
                "is_active": u.is_active,
                "base_role": u.role,
                "studio_owner_of": [r["studio"] for r in studio_roles.get(u.id, []) if r["level"] == "owner"],
                "studio_manager_of": [r["studio"] for r in studio_roles.get(u.id, []) if r["level"] == "manager"],
                "franchise_owner_of": [f["name"] for f in franchise_roles.get(u.id, []) if f["level"] == "owner"],
                "franchise_manager_of": [f["name"] for f in franchise_roles.get(u.id, []) if f["level"] == "manager"],
                "franchise_reports_of": [f["name"] for f in franchise_roles.get(u.id, []) if f["level"] == "reports"],
                "instructor_studio_ids": member_studios.get(u.id, []),
            }
            for u in users
        ]
    }


@router.get("/me")
def my_roles(db: DBSession = Depends(get_db), current_user: User = Depends(get_current_user),
             operating_studio_id=Depends(get_operating_studio_id)):
    """The current user's own hats — lets the UI show/hide capabilities."""
    studio_rows = (
        db.query(StudioOwner)
        .filter(StudioOwner.user_id == current_user.id, StudioOwner.is_active == True)
        .all()
    )
    franchise_count = (
        db.query(FranchiseOwner)
        .filter(FranchiseOwner.user_id == current_user.id, FranchiseOwner.is_active == True)
        .count()
    )
    is_admin = current_user.role == "admin"
    franchise_manager = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == current_user.id,
            FranchiseOwner.is_active == True,
            FranchiseOwner.level == "manager",
        )
        .count()
        > 0
    )
    franchise_reports = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == current_user.id,
            FranchiseOwner.is_active == True,
            FranchiseOwner.level == "reports",
        )
        .count()
        > 0
    )
    franchise_owner_level = (
        db.query(FranchiseOwner)
        .filter(
            FranchiseOwner.user_id == current_user.id,
            FranchiseOwner.is_active == True,
            FranchiseOwner.level == "owner",
        )
        .count()
        > 0
    )
    # The locked-down reporting persona: a franchise OWNER or REPORTS-only user
    # with nothing operational (no admin/staff base role, no studio hats, not a
    # franchise ops-manager). Both tiers get the reports-only UI; only owners
    # additionally get the Franchise Users (invite) page — driven by
    # franchise_can_invite below.
    franchise_reporting_only = (
        (franchise_owner_level or franchise_reports)
        and not is_admin
        and current_user.role not in ("manager", "instructor")
        and not studio_rows
        and not franchise_manager
    )
    # Only franchise OWNERS may add/invite reporting users; reports-only cannot.
    franchise_can_invite = franchise_reporting_only and franchise_owner_level

    # The studio this login belongs to — shown as the app header. Priority:
    # home studio, then an owned/managed studio.
    studio_name = None
    studio_id = current_user.studio_id or (studio_rows[0].studio_id if studio_rows else None)
    if studio_id:
        studio = db.query(Studio).filter(Studio.id == studio_id).first()
        studio_name = (studio.display_name or studio.name) if studio else None

    # All studios this user works at, with their role(s) at each and which is
    # primary — drives the multi-studio header switcher.
    from app.models.user_studio import UserStudio
    member_rows = db.query(UserStudio).filter(
        UserStudio.user_id == current_user.id, UserStudio.is_active == True).all()
    roles_by_studio = {}
    for r in studio_rows:
        roles_by_studio.setdefault(r.studio_id, set()).add(r.level or "owner")
    for r in member_rows:
        roles_by_studio.setdefault(r.studio_id, set()).add("instructor")
    if current_user.studio_id:
        roles_by_studio.setdefault(current_user.studio_id, set())
    names = {}
    if roles_by_studio:
        for s in db.query(Studio).filter(Studio.id.in_(list(roles_by_studio.keys()))).all():
            names[s.id] = s.display_name or s.name
    studios_list = sorted(
        [
            {"id": str(sid), "name": names.get(sid), "roles": sorted(roles_by_studio[sid]),
             "is_primary": sid == current_user.studio_id}
            for sid in roles_by_studio if names.get(sid)
        ],
        key=lambda x: (not x["is_primary"], x["name"] or ""),
    )

    return {
        "base_role": current_user.role,
        "studio_name": studio_name,
        "studios": studios_list,
        "active_studio_id": str(operating_studio_id) if operating_studio_id else None,
        "studio_owner": any((r.level or "owner") == "owner" for r in studio_rows),
        "studio_manager": any(r.level == "manager" for r in studio_rows),
        "franchise_owner": franchise_count > 0,
        "franchise_owner_level": franchise_owner_level,
        "franchise_manager": franchise_manager,
        "franchise_reporting_only": franchise_reporting_only,
        "franchise_can_invite": franchise_can_invite,
        "can_manage_users": is_admin or bool(studio_rows),
        "can_manage_setup": is_admin or current_user.role == "manager" or bool(studio_rows),
        "is_staff": is_admin or current_user.role in ("manager", "instructor")
            or bool(studio_rows) or franchise_count > 0,
    }


class StudioRoleAssignment(BaseModel):
    studio_id: UUID
    level: str = "owner"                  # 'owner' | 'manager'


class UserRolesUpdate(BaseModel):
    """Role model: checkboxes/hats per user. A user may hold owner/manager hats at
    MULTIPLE studios (studio_roles); one franchise per user for now."""
    is_admin: bool = False
    is_instructor: bool = False
    franchise_id: Optional[UUID] = None
    franchise_level: str = "reports"     # 'owner' | 'manager' | 'reports'
    # Preferred: the full set of studio owner/manager hats for this user.
    studio_roles: Optional[List[StudioRoleAssignment]] = None
    # Legacy single-studio fields — still honored when studio_roles is omitted.
    studio_id: Optional[UUID] = None
    studio_level: str = "owner"          # 'owner' | 'manager'
    home_studio_id: Optional[UUID] = None  # instructor's primary studio
    # The full set of studios this instructor teaches at (multi-studio). When
    # omitted, existing memberships are left alone (primary is still ensured).
    instructor_studio_ids: Optional[List[UUID]] = None


@router.put("/user/{user_id}")
def set_user_roles(
    user_id: UUID,
    payload: UserRolesUpdate,
    db: DBSession = Depends(get_db),
    admin: User = Depends(require_admin),
):
    """One-stop role editor (admin): reconciles the user's base role and ALL
    hats — studio owner/manager, franchise owner — in one call."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if payload.franchise_level not in {"owner", "manager", "reports"}:
        raise HTTPException(status_code=422, detail="franchise_level must be owner, manager, or reports")

    # The desired set of studio owner/manager hats. Prefer the multi-studio
    # `studio_roles` list; fall back to the legacy single studio_id/level.
    if payload.studio_roles is not None:
        desired_studios = {r.studio_id: r.level for r in payload.studio_roles}
    elif payload.studio_id:
        desired_studios = {payload.studio_id: payload.studio_level}
    else:
        desired_studios = {}
    for lvl in desired_studios.values():
        if lvl not in {"owner", "manager"}:
            raise HTTPException(status_code=422, detail="studio level must be owner or manager")

    # Base role: admin > instructor > member. Instructor is a checkbox now.
    user.role = "admin" if payload.is_admin else ("instructor" if payload.is_instructor else "member")

    # Home studio: which studio's clients/dashboard this user sees.
    user.studio_id = payload.home_studio_id

    # Studio hats: a user may own/manage MULTIPLE studios. Reconcile to
    # desired_studios — activate one row per desired studio (partial-unique index
    # allows only one active row per (user, studio)); deactivate everything else.
    seen_studios = set()
    for row in db.query(StudioOwner).filter(StudioOwner.user_id == user_id).all():
        if row.studio_id in desired_studios and row.studio_id not in seen_studios:
            row.level = desired_studios[row.studio_id]
            row.is_active = True
            seen_studios.add(row.studio_id)
        else:
            row.is_active = False
    for sid, lvl in desired_studios.items():
        if sid not in seen_studios:
            db.add(StudioOwner(user_id=user_id, studio_id=sid,
                               level=lvl, assigned_by_user_id=admin.id, is_active=True))

    # Instructor studio memberships — the studios they TEACH at (multi-studio).
    from app.models.user_studio import UserStudio
    if payload.instructor_studio_ids is not None:
        desired_member = set(payload.instructor_studio_ids)
        if payload.home_studio_id:
            desired_member.add(payload.home_studio_id)   # primary is always a membership
        seen_member = set()
        for row in db.query(UserStudio).filter(UserStudio.user_id == user_id).all():
            if row.studio_id in desired_member and row.studio_id not in seen_member:
                row.is_active = True
                seen_member.add(row.studio_id)
            else:
                row.is_active = False
        for sid in desired_member:
            if sid not in seen_member:
                db.add(UserStudio(user_id=user_id, studio_id=sid,
                                  assigned_by_user_id=admin.id, is_active=True))
    elif payload.home_studio_id:
        # Legacy call (no explicit list): don't collapse memberships — just ensure
        # the primary studio is an active membership.
        existing = (db.query(UserStudio)
                    .filter(UserStudio.user_id == user_id, UserStudio.studio_id == payload.home_studio_id)
                    .first())
        if existing:
            existing.is_active = True
        else:
            db.add(UserStudio(user_id=user_id, studio_id=payload.home_studio_id,
                              assigned_by_user_id=admin.id, is_active=True))

    # Franchise role: ONE franchise per user
    for row in db.query(FranchiseOwner).filter(FranchiseOwner.user_id == user_id).all():
        if payload.franchise_id and row.franchise_id == payload.franchise_id:
            row.level = payload.franchise_level
            row.is_active = True
            payload.franchise_id = None
        else:
            row.is_active = False
    if payload.franchise_id:
        db.add(FranchiseOwner(user_id=user_id, franchise_id=payload.franchise_id,
                              level=payload.franchise_level, assigned_by_user_id=admin.id, is_active=True))

    db.commit()
    return {"message": "roles updated"}
