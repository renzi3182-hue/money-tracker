"""API JSON per la versione web (Vercel). Calcoli in src/stats.py, accesso al DB in src/db.py: qui solo validazione,
login e trasformazione in JSON. In locale serve anche public/ (su Vercel la serve la CDN):
    .venv/bin/uvicorn api.index:app --app-dir code/money-tracker --port 8520

Variabili d'ambiente: DATABASE_URL (Neon), SESSION_SECRET (firma dei cookie, almeno 32 caratteri), OWNER_EMAIL e
APP_PASSWORD (il proprietario si registra con la vecchia password unica e ritrova i dati con user_id USER_ID, default
"me"). Ognuno si registra con email e password e vede solo i suoi dati. Senza DATABASE_URL: SQLite locale e nessun login."""
import asyncio
import hashlib
import hmac
import math
import os
import re
import secrets
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
MIN_PASSWORD = 8
MAX_FAILED, LOCK_MINUTES = 5, 15  # dopo 5 password sbagliate di fila l'account resta chiuso 15 minuti
SESSION_DAYS = 90  # con "Ricordami"
HASH_ROUNDS = 300_000  # PBKDF2: circa 0,2 s per login, rende lento provare password a tappeto se il DB uscisse
EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")
USER = os.environ.get("USER_ID", "me")  # user_id dei dati del proprietario (OWNER_EMAIL), e di tutti in locale


class Invalid(Exception):
    pass


def _json(data, status_code: int = 200) -> JSONResponse:
    return JSONResponse(data, status_code, headers={"Cache-Control": "no-store"})  # dati personali: mai in cache


# --- login -----------------------------------------------------------------------------------------
# Account con email e password (tabella users su Neon). Il cookie è "id.scadenza.firma": HMAC con SESSION_SECRET
# anche sull'hash della password, così cambiarla chiude le sessioni aperte. "Ricordami" = cookie di 90 giorni;
# senza, cookie di sessione (sparisce chiudendo il browser) e comunque scaduto dopo 12 ore.
def _hash(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, HASH_ROUNDS)
    return f"pbkdf2_sha256${HASH_ROUNDS}${salt.hex()}${digest.hex()}"


def _check(password: str, stored: str) -> bool:
    _, rounds, salt, digest = stored.split("$")
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(rounds))
    return hmac.compare_digest(test.hex(), digest)


DUMMY_HASH = f"pbkdf2_sha256${HASH_ROUNDS}${'00' * 16}${'00' * 32}"  # per le email sconosciute


def _sign(user_id: int, expires: int, password_hash: str) -> str:
    msg = f"{user_id}.{expires}.{password_hash}".encode()
    return hmac.new(os.environ["SESSION_SECRET"].encode(), msg, hashlib.sha256).hexdigest()


def _auth_required() -> bool:
    return db.remote()


def _auth_configured() -> bool:
    return len(os.environ.get("SESSION_SECRET", "")) >= 32


def _user(request: Request):
    """Riga dell'account dal cookie, o None. In locale senza DB online: nessun login, dati di USER."""
    uid, _, rest = (request.cookies.get(COOKIE) or "").partition(".")
    expires, _, sig = rest.partition(".")
    if not (_auth_configured() and uid.isdigit() and expires.isdigit() and int(expires) > time.time()):
        return None
    row = db.find_user(user_id=int(uid))
    return row if row and hmac.compare_digest(sig, _sign(row.id, int(expires), row.password)) else None


def _data_id(request: Request) -> str | None:
    if not _auth_required():
        return USER
    row = _user(request)  # fail-closed: senza SESSION_SECRET nessun cookie è valido
    return row.data_id if row else None


def api(handler):
    """Controlla il login, passa all'handler lo user_id dei dati, converte gli errori di validazione in 400 e il
    risultato in JSON."""
    async def wrapped(request: Request):
        user = _data_id(request)
        if user is None:
            return _json({"error": "login"}, status_code=401)
        try:
            body = await request.json() if request.method in ("POST", "PUT", "PATCH", "DELETE") else {}
            res = _json(_clean(handler(body if isinstance(body, dict) else {}, user)))
            if handler.__name__ == "dashboard":
                _snapshot_cookie(res, request.cookies.get(COOKIE, ""))
            return res
        except Invalid as e:
            return _json({"error": str(e)}, status_code=400)
        except ValueError:
            return _json({"error": "Richiesta non valida."}, status_code=400)
    return wrapped


def _snapshot_cookie(res, token):
    """Impronta non utilizzabile per il login: lega la copia locale alla sessione persistente."""
    parts = token.split(".")
    if len(parts) != 3 or not parts[1].isdigit():
        return
    remaining = int(parts[1]) - int(time.time())
    # Solo le sessioni Ricordami durano più di dodici ore.
    if remaining > 12 * 3600:
        res.set_cookie("mt_snapshot", hashlib.sha256(token.encode()).hexdigest(),
                       max_age=remaining, secure=bool(os.environ.get("VERCEL")), samesite="strict")


def _logged(row, remember: bool) -> JSONResponse:
    days = SESSION_DAYS if remember else 0.5
    expires = int(time.time() + days * 86400)
    res = _json({"ok": True, "email": row.email})
    res.set_cookie(COOKIE, f"{row.id}.{expires}.{_sign(row.id, expires, row.password)}",
                   max_age=SESSION_DAYS * 86400 if remember else None, httponly=True,
                   secure=bool(os.environ.get("VERCEL")), samesite="strict")
    token = f"{row.id}.{expires}.{_sign(row.id, expires, row.password)}"
    if remember:
        _snapshot_cookie(res, token)
    else:
        res.delete_cookie("mt_snapshot")
    return res


async def _credentials(request: Request) -> tuple[str, str, bool]:
    try:
        body = await request.json()
    except ValueError:
        body = {}
    if not isinstance(body, dict):
        body = {}
    email, password = body.get("email"), body.get("password")
    if not isinstance(email, str) or not isinstance(password, str):
        raise Invalid("Scrivi email e password.")
    return email.strip().lower(), password, body.get("remember") is True


async def session(request: Request):
    row = _user(request) if _auth_required() else None
    return _json({"auth": _auth_required(), "configured": _auth_configured(),
                  "logged_in": not _auth_required() or row is not None, "email": row.email if row else None})


async def register(request: Request):
    if not (_auth_required() and _auth_configured()):
        return _json({"error": "Login non configurato."}, status_code=503)
    try:
        email, password, remember = await _credentials(request)
    except Invalid as e:
        return _json({"error": str(e)}, status_code=400)
    if len(email) > 200 or not EMAIL.fullmatch(email):
        return _json({"error": "Email non valida."}, status_code=400)
    if not MIN_PASSWORD <= len(password) <= 200:
        return _json({"error": f"La password deve avere almeno {MIN_PASSWORD} caratteri."}, status_code=400)
    data_id = email
    if email == os.environ.get("OWNER_EMAIL", "").strip().lower():
        # Il proprietario eredita i dati già su Neon (user_id USER): solo chi conosce la vecchia APP_PASSWORD
        owner_password = os.environ.get("APP_PASSWORD", "")
        if not owner_password or not hmac.compare_digest(password.encode(), owner_password.encode()):
            await asyncio.sleep(1)
            return _json({"error": "Per questa email usa la password dell'app che avevi già."}, status_code=403)
        data_id = USER
    if db.add_user(email, _hash(password), data_id) is None:
        return _json({"error": "Esiste già un account con questa email: accedi."}, status_code=409)
    return _logged(db.find_user(email=email), remember)


async def login(request: Request):
    if not (_auth_required() and _auth_configured()):
        return _json({"error": "Login non configurato."}, status_code=503)
    try:
        email, password, remember = await _credentials(request)
    except Invalid as e:
        return _json({"error": str(e)}, status_code=400)
    row = db.find_user(email=email)
    if row and row.locked_until > time.time():
        minutes = math.ceil((row.locked_until - time.time()) / 60)
        return _json({"error": f"Troppi tentativi sbagliati: riprova tra {minutes} minuti."}, status_code=429)
    # Email sconosciuta: l'hash si calcola lo stesso, così il tempo di risposta non dice se l'account esiste
    ok = _check(password, row.password if row else DUMMY_HASH) and row is not None
    if not ok:
        if row:
            locked = time.time() + LOCK_MINUTES * 60 if row.failed + 1 >= MAX_FAILED else 0.0
            db.login_attempt(row.id, False, locked)
        await asyncio.sleep(1)
        return _json({"error": "Email o password sbagliate."}, status_code=401)
    db.login_attempt(row.id, True)
    return _logged(row, remember)


async def logout(request: Request):
    res = _json({"ok": True})
    res.delete_cookie(COOKIE)
    res.delete_cookie("mt_snapshot")
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
    }
    if freq == "M":
        out["cumulative"] = stats.cumulative_month(df, today)
    return out


def _wealth(df: pd.DataFrame, user: str) -> dict:
    """Liquidità (contanti e conto insieme) e investimenti (valore ai prezzi attuali) separati: il totale è solo la loro somma."""
    ops, ins = db.load_investments(user)
    pos = stats.ledger(ops, ins)[0]
    start = db.load_start(user)
    return {"start": {"date": start[0], "amount": start[1]} if start else None,
            "cash": stats.cash(start, df, ops), "invested": pos["value"].sum(), "gain": pos["gain"].sum(),
            "positions": len(pos)}


@api
def dashboard(_, user):
    df, today = db.load(user), date.today()
    return {
        "auth_required": _auth_required(),
        "wealth": _wealth(df, user),
        "today": today,
        "options": {"kinds": db.KINDS, "expense": db.EXPENSE_CATEGORIES, "income": db.INCOME_CATEGORIES,
                    "asset_kinds": db.ASSET_KINDS, "sides": db.SIDES,
                    "profiles": list(stats.FIRE_PROFILES), "compounding": list(stats.COMPOUNDING)},
        "movements": df,
        "periods": {f: _period(df, today, f) for f in ("M", "W", "D")} if not df.empty else None,
        "balance": stats.monthly_balance(df, today) if not df.empty else [],
    }


@api
def add_movement(body, user):
    kind = _choice(body, "kind", db.KINDS)
    category = _choice(body, "category", db.EXPENSE_CATEGORIES if kind == "spesa" else db.INCOME_CATEGORIES)
    amount = _num(body, "amount", strict=True)
    db.add(_day(body), kind, amount, category, "", _text(body, "note", 200), user_id=user)
    return {"ok": True}


@api
def set_start(body, user):
    db.set_start(_day(body), _num(body, "amount", low=-1e9), user_id=user)
    return {"ok": True}


@api
def delete_movements(body, user):
    db.delete(_ids(body), user_id=user)
    return {"ok": True}


# --- investimenti ----------------------------------------------------------------------------------
@api
def investments(_, user):
    ops, ins = db.load_investments(user)
    pos, sales = stats.ledger(ops, ins)
    today = date.today()
    bag, taxed = stats.tax_bag(sales, today.year)
    expiring = bag.loc[bag["expires"] == today.year, "residual"].sum()
    saving, expense = stats.fire_defaults(db.load(user), today)
    return {
        "operations": ops, "instruments": ins, "positions": pos,
        "bag": bag, "sales": taxed.sort_values("date", ascending=False),
        "expiring": expiring, "tax_year": taxed.loc[taxed["date"].dt.year == today.year, "tax"].sum(),
        # minusvalenze in scadenza: si recuperano vendendo in guadagno posizioni non ETF
        "usable": pos.loc[(pos["kind"] != "ETF") & (pos["gain"] > 0), "name"].tolist(),
        "saving": saving, "expense": expense, "year": today.year,
    }


@api
def add_operation(body, user):
    side = _choice(body, "side", db.SIDES)
    name = _text(body, "name", 60)
    qty, price = _num(body, "quantity", strict=True), _num(body, "price", strict=True)
    fees = _num(body, "fees", default=0)
    ops, ins = db.load_investments(user)
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
    db.add_operation(_day(body), name, side, qty, price, fees, kind, user_id=user)
    return {"ok": True}


@api
def delete_operations(body, user):
    db.delete_operations(_ids(body), user_id=user)
    return {"ok": True}


@api
def update_instruments(body, user):
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
            db.update_instruments(pd.DataFrame(part), user_id=user)
    return {"ok": True}


@api
def rebalance(body, user):
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
def fire(body, user):
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
def interest(body, user):
    principal, monthly = _num(body, "principal"), _num(body, "monthly")
    rate, inflation = _num(body, "rate", high=30), _num(body, "inflation", high=20)
    years = int(_num(body, "years", low=1, high=60))
    tax = _choice(body, "tax", [0, 12.5, 26])
    per_year = stats.COMPOUNDING[_choice(body, "compounding", list(stats.COMPOUNDING))]
    growth = stats.interest_schedule(principal, monthly, rate, years, per_year, inflation, tax)
    return {"rows": growth.reset_index(), "doubling": stats.years_to_double(rate)}


routes = [
    Route("/api/session", session), Route("/api/login", login, methods=["POST"]),
    Route("/api/register", register, methods=["POST"]), Route("/api/logout", logout, methods=["POST"]),
    Route("/api/dashboard", dashboard),
    Route("/api/movements", add_movement, methods=["POST"]), Route("/api/movements", delete_movements, methods=["DELETE"]),
    Route("/api/start", set_start, methods=["PUT"]),
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
