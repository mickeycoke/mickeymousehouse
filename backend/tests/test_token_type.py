"""Only real login tokens (type='access') may authenticate the API. Invite /
reset tokens each have their own decoder and must never work as an access
token (a magic link is not a login)."""
from app.utils.tokens import create_invite_token, create_access_token, create_reset_token


def test_invite_token_rejected_as_access_token(client, admin_user):
    invite = create_invite_token(str(admin_user.id))
    r = client.get("/api/users", headers={"Authorization": f"Bearer {invite}"})
    assert r.status_code == 401

    # A genuine access token for the same user still works.
    access = create_access_token(str(admin_user.id), admin_user.role)
    ok = client.get("/api/users", headers={"Authorization": f"Bearer {access}"})
    assert ok.status_code == 200


def test_reset_token_rejected_as_access_token(client, admin_user):
    reset = create_reset_token(str(admin_user.id))
    r = client.get("/api/users", headers={"Authorization": f"Bearer {reset}"})
    assert r.status_code == 401
