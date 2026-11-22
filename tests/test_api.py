from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from api.index import app

TODAY = date.today().isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # DATABASE_URL presente = login obbligatorio, come online; qui punta a un SQLite temporaneo
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    monkeypatch.setenv("OWNER_EMAIL", "Io@Esempio.it")
    monkeypatch.setenv("APP_PASSWORD", "vecchia-password-unica")
    monkeypatch.setattr("api.index.HASH_ROUNDS", 1000)  # test veloci
    return TestClient(app)


def login(client, email="anna@esempio.it", password="password-anna", remember=True):
    res = client.post("/api/register", json={"email": email, "password": password, "remember": remember})
    if res.status_code == 409:
        res = client.post("/api/login", json={"email": email, "password": password, "remember": remember})
    assert res.status_code == 200, res.json()


def test_register_login_and_fail_closed(client, monkeypatch):
    assert client.get("/api/dashboard").status_code == 401
    for bad in ({"email": "non-email", "password": "abbastanza"}, {"email": "a@b.it", "password": "corta"}, {}):
        assert client.post("/api/register", json=bad).status_code == 400, bad
    login(client)
    assert client.get("/api/session").json() == {"auth": True, "configured": True, "logged_in": True,
                                                 "email": "anna@esempio.it"}
    assert client.post("/api/register", json={"email": "ANNA@esempio.it", "password": "altra-pass"}).status_code == 409
    client.post("/api/logout")
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/login", json={"email": "anna@esempio.it", "password": "sbagliata"}).status_code == 401
    assert client.post("/api/login", json={"email": "nessuno@esempio.it", "password": "x" * 8}).status_code == 401
    login(client)
    assert client.get("/api/dashboard").status_code == 200
    client.cookies.set("mt_session", "1.9999999999.falsa")
    assert client.get("/api/dashboard").status_code == 401
    login(client)
    monkeypatch.setenv("SESSION_SECRET", "y" * 32)  # cambiare il segreto chiude le sessioni aperte
    assert client.get("/api/dashboard").status_code == 401
    monkeypatch.setenv("SESSION_SECRET", "corto")  # segreto troppo corto: nessuno entra
    assert client.post("/api/login", json={"email": "anna@esempio.it", "password": "password-anna"}).status_code == 503


def test_remember_me_sets_persistent_cookie(client):
    res = client.post("/api/register", json={"email": "a@esempio.it", "password": "password-a", "remember": True})
    assert "Max-Age=7776000" in res.headers["set-cookie"]
    res = client.post("/api/login", json={"email": "a@esempio.it", "password": "password-a", "remember": False})
    assert "Max-Age" not in next(c for c in res.headers.get_list("set-cookie") if c.startswith("mt_session="))  # cookie di sessione
    assert client.get("/api/dashboard").status_code == 200


def test_lockout_after_failed_attempts(client):
    login(client)
    client.post("/api/logout")
    for _ in range(5):
        assert client.post("/api/login", json={"email": "anna@esempio.it", "password": "sbagliata"}).status_code == 401
    # anche con la password giusta: chiuso per qualche minuto
    assert client.post("/api/login", json={"email": "anna@esempio.it", "password": "password-anna"}).status_code == 429


def test_each_user_sees_only_own_data(client):
    movement = {"date": TODAY, "kind": "spesa", "amount": 10, "category": "Casa"}
    login(client)
    assert client.post("/api/movements", json=movement).status_code == 200
    mine = client.get("/api/dashboard").json()["movements"]
    client.post("/api/logout")
    login(client, "bruno@esempio.it", "password-bruno")
    assert client.get("/api/dashboard").json()["movements"] == []
    client.request("DELETE", "/api/movements", json={"ids": [mine[0]["id"]]})  # id di un altro: non cancella nulla
    client.post("/api/logout")
    login(client)
    assert len(client.get("/api/dashboard").json()["movements"]) == 1


def test_owner_inherits_existing_data(client):
    from src import db
    db.add(date.today(), "spesa", 5, "Casa", "", user_id="me")  # dati di prima del login a account
    owner = {"email": "io@esempio.it", "password": "un-altra-password"}
    assert client.post("/api/register", json=owner).status_code == 403  # serve la vecchia APP_PASSWORD
    assert client.post("/api/register", json=owner | {"password": "vecchia-password-unica"}).status_code == 200
    assert len(client.get("/api/dashboard").json()["movements"]) == 1


def test_movements_roundtrip_and_validation(client):
    login(client)
    ok = {"date": TODAY, "kind": "spesa", "amount": 12.5, "category": "Casa", "note": " pane "}
    assert client.post("/api/movements", json=ok).status_code == 200
    for bad in ({"amount": 0}, {"amount": "12"}, {"category": "Stipendio"}, {"kind": "regalo"},
                {"date": (date.today() + timedelta(days=1)).isoformat()}):
        assert client.post("/api/movements", json=ok | bad).status_code == 400, bad
    data = client.get("/api/dashboard").json()
    assert [m["note"] for m in data["movements"]] == ["pane"]
    assert data["periods"]["M"]["spent"] == 12.5 and data["periods"]["D"]["category"][0]["category"] == "Casa"
    assert data["wealth"]["cash"] is None
    assert client.put("/api/start", json={"date": TODAY, "amount": 1000}).status_code == 200
    assert client.put("/api/start", json={"date": TODAY, "amount": "1000"}).status_code == 400
    assert client.get("/api/dashboard").json()["wealth"]["cash"] == 1000  # movimenti del giorno stesso già dentro
    client.request("DELETE", "/api/movements", json={"ids": [data["movements"][0]["id"]]})
    assert client.get("/api/dashboard").json()["periods"] is None


def test_investments_flow(client):
    login(client)
    buy = {"date": TODAY, "side": "acquisto", "name": "VWCE", "new": True, "kind": "ETF", "quantity": 2, "price": 100,
           "fees": 1}
    assert client.post("/api/operations", json=buy).status_code == 200
    assert client.post("/api/operations", json=buy).status_code == 400  # nome già usato
    sell = {"date": TODAY, "side": "vendita", "name": "VWCE", "quantity": 3, "price": 110}
    assert client.post("/api/operations", json=sell).json()["error"] == "Ne hai solo 2 quote."
    assert client.patch("/api/instruments", json={"rows": [{"name": "VWCE", "price": 120, "target": 60}]}).status_code == 200
    inv = client.get("/api/investments").json()
    assert inv["positions"][0]["value"] == 240 and inv["instruments"][0]["target"] == 60
    buy_split = client.post("/api/rebalance", json={"cash": 100, "rows": [{"value": 240, "target": 50},
                                                                          {"value": 0, "target": 50}]}).json()["buy"]
    assert buy_split == [0, 100]
    fire = client.post("/api/fire", json={"capital": 0, "saving": 1000, "expense": 21000, "profile": "Bilanciato"}).json()
    assert fire["target"] == 600000 and fire["p10"] <= fire["p50"] <= fire["p90"]
    rows = client.post("/api/interest", json={"principal": 1000, "monthly": 0, "rate": 10, "inflation": 0, "years": 2,
                                             "tax": 0, "compounding": "Annuale"}).json()["rows"]
    assert round(rows[-1]["Composto"], 2) == 1210


def test_dashboard_bootstrap_auth_state(client):
    # L'avvio può richiedere direttamente la dashboard, senza /api/session.
    assert client.get("/api/dashboard").status_code == 401
    login(client)
    response = client.get("/api/dashboard")
    assert response.json()["auth_required"] is True
    assert response.headers["cache-control"] == "no-store"
    client.post("/api/logout")
    assert client.get("/api/dashboard").status_code == 401


def test_snapshot_marker_is_bound_to_remembered_session(client):
    import hashlib

    login(client)
    token = client.cookies.get("mt_session")
    marker = client.cookies.get("mt_snapshot")
    assert marker == hashlib.sha256(token.encode()).hexdigest()
    # Il marcatore leggibile non è una credenziale di accesso.
    client.cookies.delete("mt_session")
    assert client.get("/api/dashboard").status_code == 401
    assert client.cookies.get("mt_snapshot") == marker
    login(client)
    client.cookies.delete("mt_snapshot")  # upgrade di una sessione già esistente
    assert client.get("/api/dashboard").status_code == 200
    assert client.cookies.get("mt_snapshot")
    client.post("/api/logout")
    assert not client.cookies.get("mt_snapshot")
    assert not client.cookies.get("mt_session")


def test_snapshot_marker_disabled_without_remember_and_rotates_for_accounts(client):
    login(client)
    first = client.cookies.get("mt_snapshot")
    login(client, email="bruno@esempio.it", password="password-bruno")
    assert client.cookies.get("mt_snapshot") != first
    client.post("/api/login", json={"email": "bruno@esempio.it", "password": "password-bruno", "remember": False})
    assert not client.cookies.get("mt_snapshot")
    assert client.get("/api/dashboard").status_code == 200
    assert not client.cookies.get("mt_snapshot")
