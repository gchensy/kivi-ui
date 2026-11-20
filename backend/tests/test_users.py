from kivi_ui.models import Role, UserStatus


def test_only_admins_manage_users(make_user, login):
    make_user("root", Role.admin)
    target = make_user("ana")
    analyst = login("ana")
    assert analyst.get("/api/v1/users").status_code == 403
    assert analyst.get("/api/v1/audit-logs").status_code == 403
    assert analyst.patch(f"/api/v1/users/{target.id}", json={"role": "admin"}).status_code == 403


def test_list_filters_and_counts(make_user, login):
    make_user("root", Role.admin)
    make_user("p1", status=UserStatus.pending)
    make_user("p2", status=UserStatus.pending)
    make_user("off", status=UserStatus.disabled)
    admin = login("root")
    page = admin.get("/api/v1/users").json()
    assert page["total"] == 4
    assert page["counts"] == {"pending": 2, "active": 1, "disabled": 1}
    assert [u["status"] for u in page["items"][:2]] == ["pending", "pending"]
    pending = admin.get("/api/v1/users", params={"status": "pending"}).json()
    assert pending["total"] == 2 and pending["counts"]["active"] == 1
    assert admin.get("/api/v1/users", params={"q": "OFF"}).json()["total"] == 1


def test_admin_creates_and_promotes(make_user, login):
    make_user("root", Role.admin)
    admin = login("root")
    created = admin.post(
        "/api/v1/users",
        json={
            "username": "zhou",
            "email": "zhou@example.com",
            "display_name": "周",
            "password": "start1234",
            "role": "analyst",
        },
    )
    assert created.status_code == 201 and created.json()["status"] == "active"
    zhou = login("zhou", "start1234")
    promoted = admin.patch(f"/api/v1/users/{created.json()['id']}", json={"role": "admin"})
    assert promoted.json()["role"] == "admin"
    assert zhou.get("/api/v1/auth/me").status_code == 401  # role change ends sessions
    assert login("zhou", "start1234").get("/api/v1/users").status_code == 200


def test_admin_cannot_lock_themselves_out(make_user, login):
    root = make_user("root", Role.admin)
    admin = login("root")
    response = admin.patch(f"/api/v1/users/{root.id}", json={"status": "disabled"})
    assert response.json()["code"] == "cannot_change_self"
    other = make_user("second", Role.admin)
    demote = admin.patch(f"/api/v1/users/{other.id}", json={"role": "analyst"})
    assert demote.json()["role"] == "analyst"


def test_sole_remaining_admin_keeps_role(make_user, login, db):
    root = make_user("root", Role.admin)
    deputy = make_user("deputy", Role.admin)
    admin = login("deputy")
    assert admin.patch(f"/api/v1/users/{root.id}", json={"status": "disabled"}).status_code == 200
    db.refresh(root)
    # deputy is now the only active admin; nobody else may remove that role.
    other = login("deputy")
    response = other.patch(f"/api/v1/users/{deputy.id}", json={"role": "analyst"})
    assert response.json()["code"] == "cannot_change_self"


def test_reset_password_unlocks_and_audits(make_user, login, anon):
    make_user("root", Role.admin)
    target = make_user("wu")
    for _ in range(5):
        anon.post("/api/v1/auth/login", json={"username": "wu", "password": "wrong1234"})
    admin = login("root")
    assert (
        admin.post(
            f"/api/v1/users/{target.id}/reset-password", json={"new_password": "fresh1234"}
        ).status_code
        == 200
    )
    login("wu", "fresh1234")
    actions = [a["action"] for a in admin.get("/api/v1/audit-logs").json()["items"]]
    assert actions[:3] == ["auth.login", "user.password_reset", "auth.login"]
    assert actions.count("auth.login_failed") == 5
