"""Movimenti (spese ed entrate). Online Postgres (Neon) via st.connection("sql") con l'URL in
secrets [connections.sql]; senza quel secret SQLite locale in data/money.db. Ogni query filtra per user_id."""
from datetime import date
from functools import cache
from pathlib import Path

import pandas as pd
import sqlalchemy as sa
import streamlit as st

LOCAL_URL = f"sqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'money.db'}"

KINDS = ["spesa", "entrata"]
EXPENSE_CATEGORIES = ["Spesa alimentare", "Casa", "Bollette", "Trasporti", "Ristoranti", "Svago", "Salute",
                      "Abbonamenti", "Abbigliamento", "Altro"]
INCOME_CATEGORIES = ["Stipendio", "Extra", "Rimborso", "Altro"]
METHODS = ["Carta", "Contanti", "Bonifico", "Satispay", "PayPal"]

_meta = sa.MetaData()
movements = sa.Table(
    "movements", _meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.Text, nullable=False, server_default="me"),
    sa.Column("date", sa.Date, nullable=False),
    sa.Column("kind", sa.Text, sa.CheckConstraint("kind IN ('spesa', 'entrata')"), nullable=False),
    sa.Column("amount", sa.Float, sa.CheckConstraint("amount > 0"), nullable=False),
    sa.Column("category", sa.Text, nullable=False),
    sa.Column("method", sa.Text, nullable=False),
    sa.Column("note", sa.Text, nullable=False, server_default=""),
)


def secret(key: str):
    """Valore da secrets.toml, None se manca il file o la chiave."""
    try:
        return st.secrets.get(key)
    except FileNotFoundError:
        return None


def remote() -> bool:
    return bool((secret("connections") or {}).get("sql"))


def _engine(url: str | None = None) -> sa.Engine:
    """url esplicito (test) > secrets [connections.sql] > SQLite locale."""
    url = url or (None if remote() else LOCAL_URL)
    if url and url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    # pool_pre_ping: Neon chiude le connessioni quando si addormenta, senza ping la prima query dopo fallisce
    engine = (st.connection("sql", url=url, pool_pre_ping=True) if url
              else st.connection("sql", pool_pre_ping=True)).engine
    _create(engine)
    return engine


@cache
def _create(engine: sa.Engine) -> None:
    _meta.create_all(engine)


def add(day: date, kind: str, amount: float, category: str, method: str, note: str = "",
        user_id: str = "me", url: str | None = None) -> None:
    with _engine(url).begin() as con:
        con.execute(movements.insert().values(user_id=user_id, date=day, kind=kind, amount=round(amount, 2),
                                              category=category, method=method, note=note.strip()))


def delete(ids: list[int], user_id: str = "me", url: str | None = None) -> None:
    with _engine(url).begin() as con:
        con.execute(movements.delete().where(movements.c.id.in_(ids), movements.c.user_id == user_id))


def load(user_id: str = "me", url: str | None = None) -> pd.DataFrame:
    c = movements.c
    query = (sa.select(c.id, c.date, c.kind, c.amount, c.category, c.method, c.note)
             .where(c.user_id == user_id).order_by(c.date.desc(), c.id.desc()))
    with _engine(url).connect() as con:
        df = pd.read_sql(query, con)
    df["date"] = pd.to_datetime(df["date"])
    return df
