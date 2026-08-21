from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import (
    attachments,
    auth,
    franchise_owners,
    franchise_studios,
    franchises,
    login_events,
    notes,
    onboard,
    owner_billing,
    ownership,
    pricing_tiers,
    questions,
    roles,
    studio_assignment,
    studio_billing,
    studio_owners,
    studios,
    users,
)

app = FastAPI(title="Mickeymouse House API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(onboard.router)
app.include_router(users.router)
app.include_router(studio_billing.router)
app.include_router(owner_billing.router)
app.include_router(pricing_tiers.router)
app.include_router(franchises.router)
app.include_router(franchise_owners.router)
app.include_router(franchise_studios.router)
app.include_router(studio_owners.router)
app.include_router(studio_assignment.router)
app.include_router(studios.router)
app.include_router(ownership.router)
app.include_router(roles.router)
app.include_router(login_events.router)
app.include_router(notes.router)
app.include_router(notes.admin_router)
app.include_router(questions.router)
app.include_router(questions.admin_router)
app.include_router(attachments.router)


@app.get("/api/health")
def health():
    # `environment` lets deploy tooling refuse to run destructive checks
    # against production. Non-secret — safe to expose.
    import os
    return {"status": "ok", "environment": os.getenv("APP_ENV", "development")}
