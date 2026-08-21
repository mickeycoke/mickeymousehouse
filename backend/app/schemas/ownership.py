from uuid import UUID

from pydantic import BaseModel


class OwnershipScopeResponse(BaseModel):
    is_admin: bool
    studio_ids: list[UUID]
    franchise_ids: list[UUID]


class OwnerCandidateResponse(BaseModel):
    id: UUID
    # PIN-only instructors have no email — nullable, or the whole candidate
    # list 500s on the first email-less user.
    email: str | None = None
    name: str
    role: str
    studio_id: UUID | None = None

    model_config = {"from_attributes": True}
