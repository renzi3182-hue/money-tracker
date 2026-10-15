from datetime import date

import pandas as pd

from src import db, stats

TODAY = date(2026, 10, 15)  # giovedì


def _df(rows):
    return pd.DataFrame(rows, columns=["date", "kind", "amount", "category", "method"]).assign(
        date=lambda d: pd.to_datetime(d["date"]))


DF = _df([
    ("2026-10-15", "spesa", 10, "Ristoranti", "Carta"),
    ("2026-10-13", "spesa", 20, "Casa", "Contanti"),       # questa settimana (lun 12)
    ("2026-10-06", "spesa", 30, "Casa", "Carta"),          # settimana scorsa, entro pari giorni (lun-gio)
    ("2026-10-11", "spesa", 0.5, "Casa", "Carta"),         # domenica scorsa: fuori dal confronto a pari giorni
    ("2026-10-01", "entrata", 1000, "Stipendio", "Bonifico"),
    ("2026-09-10", "spesa", 40, "Svago", "Carta"),         # mese scorso entro il 15
    ("2026-09-20", "spesa", 50, "Svago", "Carta"),         # mese scorso dopo il 15
])


def test_period_totals():
    assert stats.totals(DF, TODAY, "D") == (10, 0)
    assert stats.totals(DF, TODAY, "W") == (30, 30)
    assert stats.totals(DF, TODAY, "M") == (60.5, 40)  # mese scorso solo fino al 15


def test_previous_month_clamped():
    assert stats.previous_window(date(2026, 3, 31), "M") == (date(2026, 2, 1), date(2026, 2, 28))


def test_breakdown_and_history():
    br = stats.breakdown(DF, date(2026, 10, 1), TODAY, "category")
    assert br.to_dict("records")[0] == {"category": "Casa", "amount": 50.5}
    h = stats.history(DF, TODAY, "W")
    assert len(h) == 12 and h["amount"].iloc[-1] == 30
    assert stats.history(DF, TODAY, "M")["amount"].iloc[-2:].tolist() == [90, 60.5]


def test_monthly_balance_and_cumulative():
    oct_ = stats.monthly_balance(DF, TODAY, 2).iloc[-1]
    assert (oct_["income"], oct_["expense"], oct_["saving"], oct_["rate"]) == (1000, 60.5, 939.5, 94.0)
    assert pd.isna(stats.monthly_balance(DF, TODAY, 2).iloc[0]["rate"])  # settembre senza entrate
    cum = stats.cumulative_month(DF, TODAY)
    assert cum[cum["serie"] == "Questo mese"]["amount"].iloc[-1] == 60.5
    assert cum[cum["serie"] == "Mese scorso"]["amount"].iloc[-1] == 90


def test_db_roundtrip(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    db.add(TODAY, "spesa", 12.345, "Casa", "Carta", " pane ", url=url)
    db.add(TODAY, "spesa", 5, "Casa", "Carta", user_id="altro", url=url)
    df = db.load(url=url)
    assert df[["amount", "note"]].values.tolist() == [[12.35, "pane"]]
    db.delete(df["id"].tolist(), url=url)
    assert db.load(url=url).empty and len(db.load("altro", url=url)) == 1
