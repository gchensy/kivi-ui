from conftest import PASSWORD, client

from kivi_ui.models import Role, UserStatus

SIGNUP = {
    "username": "Zhang.San",
    "email": "ZS@Example.com",
    "display_name": " 张三 ",
    "password": "abc12345x",
}


def test_signup_waits_for_approval_then_signs_in(anon, make_user, login):
    created = anon.post("/api/v1/auth/signup", json=SIGNUP)
    assert created.status_code == 201
    body = created.json()
    assert body["requires_approval"] is True
    assert body["user"] | {"id": None, "created_at": None} == body["user"] | {
        "username": "zhang.san",
        "email": "zs@example.com",
        "display_name": "张三",
        "role": "analyst",
        "status": "pending",
        "id": None,
        "created_at": None,
    }

    pending = anon.post("/api/v1/auth/login", json={"username": "zhang.san", "password": "abc12345x"})
    assert pending.status_code == 403 and pending.json()["code"] == "account_pending"

    make_user("root", Role.admin)
    admin = login("root")
    activated = admin.patch(f"/api/v1/users/{body['user']['id']}", json={"status": "active"})
    assert activated.json()["status"] == "active"

    user = login("zs@example.com", "abc12345x")  # email works as the login name
    assert user.get("/api/v1/auth/me").json()["username"] == "zhang.san"


def test_duplicate_and_weak_signups_are_rejected(anon):
    assert anon.post("/api/v1/auth/signup", json=SIGNUP).status_code == 201
    again = anon.post("/api/v1/auth/signup", json=SIGNUP | {"email": "other@example.com"})
    assert again.status_code == 409 and again.json()["code"] == "username_taken"
    again = anon.post("/api/v1/auth/signup", json=SIGNUP | {"username": "other"})
    assert again.json()["code"] == "email_taken"
    weak = anon.post("/api/v1/auth/signup", json=SIGNUP | {"username": "x", "password": "letters"})
    assert weak.status_code == 422
    assert {e["field"] for e in weak.json()["detail"]} == {"username", "password"}


def test_signup_modes(anon, monkeypatch):
    monkeypatch.setenv("KIVI_SIGNUP_MODE", "closed")
    from kivi_ui.config import get_settings

    get_settings.cache_clear()
    assert anon.post("/api/v1/auth/signup", json=SIGNUP).json()["code"] == "signup_closed"
    monkeypatch.setenv("KIVI_SIGNUP_MODE", "open")
    get_settings.cache_clear()
    body = anon.post("/api/v1/auth/signup", json=SIGNUP).json()
    assert body["requires_approval"] is False and body["user"]["status"] == "active"


def test_lockout_after_repeated_failures(anon, make_user):
    make_user("li")
    for _ in range(5):
        response = anon.post("/api/v1/auth/login", json={"username": "li", "password": "wrong1234"})
        assert response.json()["code"] == "invalid_credentials"
    locked = anon.post("/api/v1/auth/login", json={"username": "li", "password": PASSWORD})
    assert locked.status_code == 423 and locked.json()["detail"]["minutes"] >= 1


def test_disabled_and_unknown_accounts(anon, make_user):
    make_user("gone", status=UserStatus.disabled)
    assert (
        anon.post("/api/v1/auth/login", json={"username": "gone", "password": PASSWORD}).json()["code"]
        == "account_disabled"
    )
    assert (
        anon.post("/api/v1/auth/login", json={"username": "nobody", "password": PASSWORD}).status_code == 401
    )


def test_password_change_ends_other_sessions(make_user, login):
    make_user("wang")
    first, second = login("wang"), login("wang")
    wrong = first.post(
        "/api/v1/auth/password", json={"current_password": "nope", "new_password": "newpass123"}
    )
    assert wrong.json()["code"] == "wrong_password"
    changed = first.post(
        "/api/v1/auth/password", json={"current_password": PASSWORD, "new_password": "newpass123"}
    )
    assert changed.status_code == 200
    assert first.get("/api/v1/auth/me").status_code == 200  # reissued cookie
    assert second.get("/api/v1/auth/me").status_code == 401
    login("wang", "newpass123")


def test_profile_update_and_logout(make_user, login):
    make_user("zhao")
    make_user("qian")
    user = login("zhao")
    updated = user.patch("/api/v1/auth/me", json={"display_name": "赵", "locale": "en-US"})
    assert updated.json()["display_name"] == "赵" and updated.json()["locale"] == "en-US"
    taken = user.patch("/api/v1/auth/me", json={"email": "QIAN@example.com"})
    assert taken.json()["code"] == "email_taken"
    assert user.post("/api/v1/auth/logout").status_code == 204
    assert user.get("/api/v1/auth/me").status_code == 401


def test_unsafe_requests_need_the_ajax_header(make_user):
    make_user("sun")
    bare = client()
    bare.headers.pop("X-Requested-With")
    response = bare.post("/api/v1/auth/login", json={"username": "sun", "password": PASSWORD})
    assert response.status_code == 403 and response.json()["code"] == "csrf_header_missing"
