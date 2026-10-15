"""Movimenti (spese ed entrate) in SQLite. user_id c'è già: col login basta passare l'utente vero."""
import sqlite3
from datetime import date
from pathlib import Path

import pandas as pd

DB_PATH = Path(__file__).resolve().parent.parent / "data" / "money.db"

KINDS = ["spesa", "entrata"]
EXPENSE_CATEGORIES = ["Spesa alimentare", "Casa", "Bollette", "Trasporti", "Ristoranti", "Svago", "Salute",
                      "Abbonamenti", "Abbigliamento", "Altro"]
INCOME_CATEGORIES = ["Stipendio", "Extra", "Rimborso", "Altro"]
METHODS = ["Carta", "Contanti", "Bonifico", "Satispay", "PayPal"]

_SCHEMA = """CREATE TABLE IF NOT EXISTS movements (
    id INTEGER PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'me',
    date TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (kind IN ('spesa', 'entrata')),
    amount REAL NOT NULL CHECK (amount > 0),
    category TEXT NOT NULL,
    method TEXT NOT NULL,
    note TEXT NOT NULL DEFAULT ''
)"""


def _conn(path: Path = DB_PATH) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path)
    con.execute(_SCHEMA)
    return con


def add(day: date, kind: str, amount: float, category: str, method: str, note: str = "",
        user_id: str = "me", path: Path = DB_PATH) -> None:
    with _conn(path) as con:
        con.execute("INSERT INTO movements (user_id, date, kind, amount, category, method, note) VALUES (?,?,?,?,?,?,?)",
                    (user_id, day.isoformat(), kind, round(amount, 2), category, method, note.strip()))


def delete(ids: list[int], user_id: str = "me", path: Path = DB_PATH) -> None:
    with _conn(path) as con:
        con.executemany("DELETE FROM movements WHERE id = ? AND user_id = ?", [(i, user_id) for i in ids])


def load(user_id: str = "me", path: Path = DB_PATH) -> pd.DataFrame:
    with _conn(path) as con:
        df = pd.read_sql("SELECT id, date, kind, amount, category, method, note FROM movements WHERE user_id = ? "
                         "ORDER BY date DESC, id DESC", con, params=(user_id,))
    df["date"] = pd.to_datetime(df["date"])
    return df
