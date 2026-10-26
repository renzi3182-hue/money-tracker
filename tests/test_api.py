from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

from api.index import app

TODAY = date.today().isoformat()


@pytest.fixture
def client(tmp_path, monkeypatch):
    # DATABASE_URL presente = login obbligatorio, come online; qui punta a un SQLite temporaneo
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{tmp_path / 'm.db'}")
    monkeypatch.setenv("APP_PASSWORD", "segreta-lunga-di-prova")
    monkeypatch.setenv("SESSION_SECRET", "x" * 32)
    return TestClient(app)


def login(client):
    assert client.post("/api/login", json={"password": "segreta-lunga-di-prova"}).status_code == 200


def test_login_required_and_fail_closed(client, monkeypatch):
    assert client.get("/api/dashboard").status_code == 401
    assert client.post("/api/login", json={"password": "no"}).status_code == 401
    login(client)
    assert client.get("/api/dashboard").status_code == 200
    client.cookies.set("mt_session", "9999999999.falsa")
    assert client.get("/api/dashboard").status_code == 401
    login(client)
    monkeypatch.setenv("APP_PASSWORD", "nuova-password-lunga")  # cambiare password chiude le sessioni aperte
    assert client.get("/api/dashboard").status_code == 401
    monkeypatch.setenv("APP_PASSWORD", "corta")  # sotto i 16 caratteri il login resta chiuso
    assert client.post("/api/login", json={"password": "corta"}).status_code == 503
    monkeypatch.delenv("APP_PASSWORD")  # DB online senza password: nessuno entra
    assert client.get("/api/dashboard").status_code == 401


def test_movements_roundtrip_and_validation(client):
    login(client)
    ok = {"date": TODAY, "kind": "spesa", "amount": 12.5, "category": "Casa", "method": "Carta", "note": " pane "}
    assert client.post("/api/movements", json=ok).status_code == 200
    for bad in ({"amount": 0}, {"amount": "12"}, {"category": "Stipendio"}, {"kind": "regalo"},
                {"date": (date.today() + timedelta(days=1)).isoformat()}):
        assert client.post("/api/movements", json=ok | bad).status_code == 400, bad
    data = client.get("/api/dashboard").json()
    assert [m["note"] for m in data["movements"]] == ["pane"]
    assert data["periods"]["M"]["spent"] == 12.5 and data["periods"]["D"]["category"][0]["category"] == "Casa"
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
