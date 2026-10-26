"""Movimenti (spese ed entrate) e investimenti (strumenti e operazioni). Online Postgres (Neon) con l'URL nella variabile
d'ambiente DATABASE_URL (su Streamlit la imposta app.py dai secrets); senza, SQLite locale in data/money.db.
Ogni query filtra per user_id."""
import os
from datetime import date
from functools import cache
from pathlib import Path

import pandas as pd
import sqlalchemy as sa

LOCAL_URL = f"sqlite:///{Path(__file__).resolve().parent.parent / 'data' / 'money.db'}"

KINDS = ["spesa", "entrata"]
EXPENSE_CATEGORIES = ["Spesa alimentare", "Casa", "Bollette", "Trasporti", "Ristoranti", "Svago", "Salute",
                      "Abbonamenti", "Abbigliamento", "Altro"]
INCOME_CATEGORIES = ["Stipendio", "Extra", "Rimborso", "Altro"]
METHODS = ["Carta", "Contanti", "Bonifico", "Satispay", "PayPal"]
# Il tipo decide le tasse: ETF = redditi di capitale (i guadagni non usano lo zainetto), titoli di Stato al 12,5%
ASSET_KINDS = ["ETF", "ETC", "Azione", "Obbligazione", "Titolo di Stato"]
SIDES = ["acquisto", "vendita"]

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

# Prezzo attuale (aggiornato a mano) e peso obiettivo per il ribilanciatore: uno per strumento
instruments = sa.Table(
    "instruments", _meta,
    sa.Column("user_id", sa.Text, primary_key=True),
    sa.Column("name", sa.Text, primary_key=True),
    sa.Column("kind", sa.Text, nullable=False),
    sa.Column("price", sa.Float, nullable=False),
    sa.Column("target", sa.Float, nullable=False, server_default="0"),
)
operations = sa.Table(
    "operations", _meta,
    sa.Column("id", sa.Integer, primary_key=True),
    sa.Column("user_id", sa.Text, nullable=False),
    sa.Column("date", sa.Date, nullable=False),
    sa.Column("name", sa.Text, nullable=False),
    sa.Column("side", sa.Text, sa.CheckConstraint("side IN ('acquisto', 'vendita')"), nullable=False),
    sa.Column("quantity", sa.Float, sa.CheckConstraint("quantity > 0"), nullable=False),
    sa.Column("price", sa.Float, sa.CheckConstraint("price > 0"), nullable=False),
    sa.Column("fees", sa.Float, sa.CheckConstraint("fees >= 0"), nullable=False, server_default="0"),
)


def remote() -> bool:
    return bool(os.environ.get("DATABASE_URL"))


def _engine(url: str | None = None) -> sa.Engine:
    """url esplicito (test) > DATABASE_URL > SQLite locale."""
    return _create(url or os.environ.get("DATABASE_URL") or LOCAL_URL)


@cache
def _create(url: str) -> sa.Engine:
    # Neon e Vercel danno postgres(ql)://: SQLAlchemy lo leggerebbe come psycopg 3, installato c'è psycopg2
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            url = "postgresql+psycopg2://" + url.removeprefix(prefix)
    if url.startswith("sqlite:///"):
        Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
    # pool_pre_ping: Neon chiude le connessioni quando si addormenta, senza ping la prima query dopo fallisce
    engine = sa.create_engine(url, pool_pre_ping=True)
    _meta.create_all(engine)
    return engine


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


def add_operation(day: date, name: str, side: str, quantity: float, price: float, fees: float = 0.0,
                  kind: str | None = None, user_id: str = "me", url: str | None = None) -> None:
    """Salva l'operazione; al primo acquisto di uno strumento lo crea (serve kind) col prezzo dell'operazione."""
    name = name.strip()
    with _engine(url).begin() as con:
        known = con.execute(sa.select(instruments.c.name).where(instruments.c.user_id == user_id,
                                                                instruments.c.name == name)).first()
        if not known:
            con.execute(instruments.insert().values(user_id=user_id, name=name, kind=kind, price=price))
        con.execute(operations.insert().values(user_id=user_id, date=day, name=name, side=side, quantity=quantity,
                                               price=price, fees=round(fees, 2)))


def delete_operations(ids: list[int], user_id: str = "me", url: str | None = None) -> None:
    """Cancella le operazioni e gli strumenti rimasti senza operazioni."""
    with _engine(url).begin() as con:
        con.execute(operations.delete().where(operations.c.id.in_(ids), operations.c.user_id == user_id))
        used = sa.select(operations.c.name).where(operations.c.user_id == user_id)
        con.execute(instruments.delete().where(instruments.c.user_id == user_id, instruments.c.name.not_in(used)))


def update_instruments(rows: pd.DataFrame, user_id: str = "me", url: str | None = None) -> None:
    """rows: colonna name più le colonne da aggiornare (price e/o target)."""
    cols = [c for c in rows.columns if c in ("price", "target")]
    with _engine(url).begin() as con:
        for r in rows.to_dict("records"):
            con.execute(instruments.update().where(instruments.c.user_id == user_id, instruments.c.name == r["name"])
                        .values({c: float(r[c]) for c in cols}))


def load_investments(user_id: str = "me", url: str | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(operazioni dalla più recente, strumenti per nome)."""
    o, i = operations.c, instruments.c
    with _engine(url).connect() as con:
        ops = pd.read_sql(sa.select(o.id, o.date, o.name, o.side, o.quantity, o.price, o.fees)
                          .where(o.user_id == user_id).order_by(o.date.desc(), o.id.desc()), con)
        ins = pd.read_sql(sa.select(i.name, i.kind, i.price, i.target).where(i.user_id == user_id).order_by(i.name), con)
    ops["date"] = pd.to_datetime(ops["date"])
    return ops, ins
