"""API JSON per la versione web (Vercel). Calcoli in src/stats.py, accesso al DB in src/db.py: qui solo validazione,
login e trasformazione in JSON. In locale serve anche public/ (su Vercel la serve la CDN):
    .venv/bin/uvicorn api.index:app --app-dir code/money-tracker --port 8520

Variabili d'ambiente: DATABASE_URL (Neon), APP_PASSWORD e SESSION_SECRET (login), USER_ID (default "me", lo user_id dei
dati già su Neon). Senza DATABASE_URL: SQLite locale e nessun login."""
import hashlib
import hmac
import math
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from src import db, stats  # noqa: E402

COOKIE = "mt_session"
SESSION_DAYS = 90
USER = os.environ.get("USER_ID", "me")


class Invalid(Exception):
    pass


def _json(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code, headers={"Cache-Control": "no-store"})  # dati personali: mai in cache


# --- login -----------------------------------------------------------------------------------------
# Password unica nelle variabili d'ambiente; il cookie è "scadenza.firma" con HMAC. La chiave dipende anche dalla
# password: cambiandola su Vercel tutte le sessioni aperte decadono.
def _key() -> bytes:
    return hmac.new(os.environ["SESSION_SECRET"].encode(), os.environ["APP_PASSWORD"].encode(), hashlib.sha256).digest()


def _sign(expires: int) -> str:
    return f"{expires}.{hmac.new(_key(), str(expires).encode(), hashlib.sha256).hexdigest()}"


def _auth_required() -> bool:
    return db.remote()


def _auth_configured() -> bool:
    return bool(os.environ.get("APP_PASSWORD") and os.environ.get("SESSION_SECRET"))


def _logged_in(request: Request) -> bool:
    if not _auth_required():
        return True
    if not _auth_configured():  # fail-closed: DB online senza password = nessuno entra
        return False
    expires, _, _sig = (request.cookies.get(COOKIE) or "").partition(".")
    return expires.isdigit() and int(expires) > time.time() and hmac.compare_digest(request.cookies[COOKIE], _sign(int(expires)))


def api(handler):
    """Controlla il login, converte gli errori di validazione in 400 e il risultato in JSON."""
    async def wrapped(request: Request):
        if not _logged_in(request):
            return _json({"error": "login"}, status_code=401)
        try:
            body = await request.json() if request.method in ("POST", "PATCH", "DELETE") else {}
            return _json(_clean(handler(body if isinstance(body, dict) else {})))
        except Invalid as e:
            return _json({"error": str(e)}, status_code=400)
        except ValueError:
            return _json({"error": "Richiesta non valida."}, status_code=400)
    return wrapped


async def session(request: Request):
    return _json({"auth": _auth_required(), "logged_in": _logged_in(request), "configured": _auth_configured()})


async def login(request: Request):
    if not (_auth_required() and _auth_configured()):
        return _json({"error": "Login non configurato."}, status_code=503)
    try:
        password = str((await request.json()).get("password", ""))
    except ValueError:
        password = ""
    if not hmac.compare_digest(password.encode(), os.environ["APP_PASSWORD"].encode()):
        time.sleep(1)  # shortcut: rallenta i tentativi ma non li blocca; per un vero limite serve uno store (Vercel KV)
        return _json({"error": "Password sbagliata."}, status_code=401)
    expires = int(time.time()) + SESSION_DAYS * 86400
    res = _json({"ok": True})
    res.set_cookie(COOKIE, _sign(expires), max_age=SESSION_DAYS * 86400, httponly=True,
                   secure=bool(os.environ.get("VERCEL")), samesite="strict")
    return res


async def logout(request: Request):
    res = _json({"ok": True})
    res.delete_cookie(COOKIE)
    return res


# --- validazione -----------------------------------------------------------------------------------
def _num(body: dict, key: str, low: float = 0.0, high: float = 1e9, strict: bool = False, default=None) -> float:
    v = body.get(key, default)
    if isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v):
        raise Invalid(f"Valore non valido: {key}.")
    if v < low or v > high or (strict and v <= low):
        raise Invalid(f"Valore fuori intervallo: {key}.")
    return float(v)


def _choice(body: dict, key: str, options: list) -> str:
    if body.get(key) not in options:
        raise Invalid(f"Valore non valido: {key}.")
    return body[key]


def _day(body: dict) -> date:
    try:
        day = date.fromisoformat(str(body.get("date")))
    except ValueError:
        raise Invalid("Data non valida.")
    if day > date.today():
        raise Invalid("La data non può essere nel futuro.")
    return day


def _ids(body: dict) -> list[int]:
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
        raise Invalid("Nessun elemento selezionato.")
    return ids


def _text(body: dict, key: str, limit: int) -> str:
    v = body.get(key, "")
    if not isinstance(v, str) or len(v) > limit:
        raise Invalid(f"Testo non valido: {key}.")
    return v.strip()


# --- JSON ------------------------------------------------------------------------------------------
def _clean(x):
    """Tipi numpy/pandas in tipi JSON; NaN e infinito in None."""
    if isinstance(x, dict):
        return {k: _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, pd.DataFrame):
        return _clean(x.to_dict("records"))
    if isinstance(x, (pd.Timestamp, date)):
        return x.strftime("%Y-%m-%d")
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (float, np.floating)):
        return None if not math.isfinite(x) else float(x)
    return x


# --- spese ed entrate ------------------------------------------------------------------------------
def _period(df: pd.DataFrame, today: date, freq: str) -> dict:
    start = stats.period_start(today, freq)
    spent, before = stats.totals(df, today, freq)
    out = {
        "start": start, "spent": spent, "before": before, "income": stats.total(df, start, today, "entrata"),
        "history": stats.history(df, today, freq),
        "category": stats.breakdown(df, start, today, "category"),
        "method": stats.breakdown(df, start, today, "method"),
    }
    if freq == "M":
        out["cumulative"] = stats.cumulative_month(df, today)
    return out


@api
def dashboard(_):
    df, today = db.load(USER), date.today()
    return {
        "today": today,
        "options": {"kinds": db.KINDS, "expense": db.EXPENSE_CATEGORIES, "income": db.INCOME_CATEGORIES,
                    "methods": db.METHODS, "asset_kinds": db.ASSET_KINDS, "sides": db.SIDES,
                    "profiles": list(stats.FIRE_PROFILES), "compounding": list(stats.COMPOUNDING)},
        "movements": df,
        "periods": {f: _period(df, today, f) for f in ("M", "W", "D")} if not df.empty else None,
        "balance": stats.monthly_balance(df, today) if not df.empty else [],
    }


@api
def add_movement(body):
    kind = _choice(body, "kind", db.KINDS)
    category = _choice(body, "category", db.EXPENSE_CATEGORIES if kind == "spesa" else db.INCOME_CATEGORIES)
    amount = _num(body, "amount", strict=True)
    db.add(_day(body), kind, amount, category, _choice(body, "method", db.METHODS), _text(body, "note", 200), user_id=USER)
    return {"ok": True}


@api
def delete_movements(body):
    db.delete(_ids(body), user_id=USER)
    return {"ok": True}


# --- investimenti ----------------------------------------------------------------------------------
@api
def investments(_):
    ops, ins = db.load_investments(USER)
    pos, sales = stats.ledger(ops, ins)
    today = date.today()
    bag, taxed = stats.tax_bag(sales, today.year)
    expiring = bag.loc[bag["expires"] == today.year, "residual"].sum()
    saving, expense = stats.fire_defaults(db.load(USER), today)
    return {
        "operations": ops, "instruments": ins, "positions": pos,
        "bag": bag, "sales": taxed.sort_values("date", ascending=False),
        "expiring": expiring, "tax_year": taxed.loc[taxed["date"].dt.year == today.year, "tax"].sum(),
        # minusvalenze in scadenza: si recuperano vendendo in guadagno posizioni non ETF
        "usable": pos.loc[(pos["kind"] != "ETF") & (pos["gain"] > 0), "name"].tolist(),
        "saving": saving, "expense": expense, "year": today.year,
    }


@api
def add_operation(body):
    side = _choice(body, "side", db.SIDES)
    name = _text(body, "name", 60)
    qty, price = _num(body, "quantity", strict=True), _num(body, "price", strict=True)
    fees = _num(body, "fees", default=0)
    ops, ins = db.load_investments(USER)
    known = name in set(ins["name"])
    kind = None
    if side == "acquisto" and not known:
        kind = _choice(body, "kind", db.ASSET_KINDS)
    if not name or (body.get("new") and known):
        raise Invalid("Scrivi un nome nuovo per lo strumento.")
    if side == "vendita":
        held = stats.ledger(ops, ins)[0].set_index("name")["quantity"].get(name, 0.0)
        if qty > held + 1e-9:
            raise Invalid(f"Ne hai solo {held:g} quote.")
    db.add_operation(_day(body), name, side, qty, price, fees, kind, user_id=USER)
    return {"ok": True}


@api
def delete_operations(body):
    db.delete_operations(_ids(body), user_id=USER)
    return {"ok": True}


@api
def update_instruments(body):
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        raise Invalid("Niente da salvare.")
    clean = []
    for r in rows:
        if not isinstance(r, dict) or not isinstance(r.get("name"), str):
            raise Invalid("Riga non valida.")
        row = {"name": r["name"]}
        if "price" in r:
            row["price"] = _num(r, "price", strict=True)
        if "target" in r:
            row["target"] = _num(r, "target", high=100)
        clean.append(row)
    for cols in ({"name", "price"}, {"name", "target"}):  # update_instruments vuole le stesse colonne su ogni riga
        part = [{k: r[k] for k in cols} for r in clean if cols <= r.keys()]
        if part:
            db.update_instruments(pd.DataFrame(part), user_id=USER)
    return {"ok": True}


@api
def rebalance(body):
    cash = _num(body, "cash")
    rows = body.get("rows")
    if not isinstance(rows, list) or not rows:
        raise Invalid("Nessuno strumento.")
    values = pd.Series([_num(r, "value") for r in rows])
    targets = pd.Series([_num(r, "target", high=100) for r in rows])
    if targets.sum() <= 0:
        raise Invalid("Dai un peso obiettivo ad almeno uno strumento.")
    return {"buy": stats.rebalance(values, targets, cash).tolist()}


@api
def fire(body):
    capital, saving = _num(body, "capital"), _num(body, "saving")
    expense = _num(body, "expense", strict=True)
    mu, sigma = stats.FIRE_PROFILES[_choice(body, "profile", list(stats.FIRE_PROFILES))]
    target = round(expense / stats.WITHDRAWAL_RATE, -3)
    paths = stats.fire_paths(capital, saving, mu, sigma)
    # "lower": con inf l'interpolazione darebbe nan
    p10, p50, p90 = np.percentile(stats.years_to_target(paths, target), [10, 50, 90], method="lower")
    faster = np.percentile(stats.years_to_target(stats.fire_paths(capital, saving + 100, mu, sigma), target), 50,
                           method="lower")
    last = min(stats.FIRE_YEARS, (p90 if p90 != float("inf") else stats.FIRE_YEARS) + 5)
    band = [{"year": y, "low": np.percentile(paths[:, y], 10), "mid": np.percentile(paths[:, y], 50),
             "high": np.percentile(paths[:, y], 90)} for y in range(int(last) + 1)]
    return {"target": target, "p10": p10, "p50": p50, "p90": p90, "faster": faster, "band": band,
            "withdrawal": stats.WITHDRAWAL_RATE, "runs": stats.FIRE_RUNS}


@api
def interest(body):
    principal, monthly = _num(body, "principal"), _num(body, "monthly")
    rate, inflation = _num(body, "rate", high=30), _num(body, "inflation", high=20)
    years = int(_num(body, "years", low=1, high=60))
    tax = _choice(body, "tax", [0, 12.5, 26])
    per_year = stats.COMPOUNDING[_choice(body, "compounding", list(stats.COMPOUNDING))]
    growth = stats.interest_schedule(principal, monthly, rate, years, per_year, inflation, tax)
    return {"rows": growth.reset_index(), "doubling": stats.years_to_double(rate)}


routes = [
    Route("/api/session", session), Route("/api/login", login, methods=["POST"]),
    Route("/api/logout", logout, methods=["POST"]),
    Route("/api/dashboard", dashboard),
    Route("/api/movements", add_movement, methods=["POST"]), Route("/api/movements", delete_movements, methods=["DELETE"]),
    Route("/api/investments", investments),
    Route("/api/operations", add_operation, methods=["POST"]),
    Route("/api/operations", delete_operations, methods=["DELETE"]),
    Route("/api/instruments", update_instruments, methods=["PATCH"]),
    Route("/api/rebalance", rebalance, methods=["POST"]),
    Route("/api/fire", fire, methods=["POST"]), Route("/api/interest", interest, methods=["POST"]),
]
app = Starlette(routes=routes)

if not os.environ.get("VERCEL"):  # in locale: anche la pagina, su Vercel la serve la CDN da public/
    from starlette.staticfiles import StaticFiles
    app.mount("/", StaticFiles(directory=ROOT / "public", html=True))
