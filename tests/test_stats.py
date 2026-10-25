from datetime import date

import pandas as pd
import pytest

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


def test_fire_defaults_use_closed_months():
    df = _df([("2026-09-01", "entrata", 2000, "Stipendio", "Bonifico"), ("2026-09-10", "spesa", 1500, "Casa", "Carta"),
              ("2026-08-01", "entrata", 2000, "Stipendio", "Bonifico"), ("2026-08-10", "spesa", 1000, "Casa", "Carta"),
              ("2026-10-02", "spesa", 5000, "Casa", "Carta")])  # mese in corso: fuori
    saving, expense = stats.fire_defaults(df, TODAY)
    assert saving == 750 and expense == 1250 * 12
    assert stats.fire_defaults(df.iloc[4:], TODAY) == (0.0, 0.0)


def test_fire_paths_without_volatility_and_years_to_target():
    paths = stats.fire_paths(1000, 100, 0.0, 0.0, years=3, runs=2)
    assert paths[0].tolist() == [1000, 2200, 3400, 4600]
    assert stats.years_to_target(paths, 3000).tolist() == [2, 2]
    assert stats.years_to_target(paths, 0).tolist() == [0, 0]
    assert stats.years_to_target(paths, 1e9).tolist() == [float("inf")] * 2


def test_simple_and_compound_interest():
    df = stats.interest_schedule(1000, 0, 10, 2, per_year=1)
    assert df.loc[2, "Semplice"] == pytest.approx(1200)
    assert df.loc[2, "Composto"] == pytest.approx(1210)


def test_interest_contributions_tax_and_inflation():
    df = stats.interest_schedule(0, 100, 0, 1, inflation_pct=10, tax_pct=26)
    assert df.loc[1, "Versato"] == pytest.approx(1200) and df.loc[1, "Composto"] == pytest.approx(1200)
    assert df.loc[1, "Composto netto reale"] == pytest.approx(1200 / 1.1)
    taxed = stats.interest_schedule(1000, 0, 10, 1, per_year=1, tax_pct=26)
    assert taxed.loc[1, "Composto netto"] == pytest.approx(1074)
    assert stats.years_to_double(7.0) == pytest.approx(10.24, abs=0.01)
    assert stats.years_to_double(0) is None


def _ops(rows):
    return pd.DataFrame(rows, columns=["date", "name", "side", "quantity", "price", "fees"]).assign(
        id=lambda d: range(len(d)), date=lambda d: pd.to_datetime(d["date"]))


INS = pd.DataFrame({"name": ["VWCE", "ENI", "BTP"], "kind": ["ETF", "Azione", "Titolo di Stato"],
                    "price": [120.0, 15.0, 100.0], "target": [80.0, 0.0, 20.0]})


def test_ledger_average_cost_and_realized_gain():
    ops = _ops([("2026-01-02", "VWCE", "acquisto", 10, 100, 2), ("2026-02-02", "VWCE", "acquisto", 10, 110, 2),
                ("2026-03-02", "VWCE", "vendita", 5, 120, 1), ("2026-03-02", "ENI", "acquisto", 10, 10, 0),
                ("2026-04-02", "ENI", "vendita", 10, 12, 0)])
    pos, sales = stats.ledger(ops, INS)
    assert pos["name"].tolist() == ["VWCE"]  # ENI venduto tutto
    v = pos.iloc[0]
    assert v["quantity"] == 15 and round(v["avg_price"], 2) == 105.2 and v["value"] == 1800
    pos0, sales0 = stats.ledger(ops.iloc[:0], INS.iloc[:0])
    assert pos0["value"].sum() == 0 and stats.tax_bag(sales0, 2026)[1]["date"].dt.year.empty
    assert [round(g, 2) for g in sales["gain"]] == [73, 20]  # 5 x (120 - 105,2) - 1


def test_tax_bag_etf_gains_do_not_use_losses_and_losses_expire():
    sales = pd.DataFrame({"date": pd.to_datetime(["2020-05-01", "2021-05-01", "2021-06-01", "2025-01-01", "2026-01-01"]),
                          "name": ["ENI", "VWCE", "ENI", "BTP", "ENI"],
                          "kind": ["Azione", "ETF", "Azione", "Titolo di Stato", "Azione"],
                          "gain": [-1000, 500, 300, -260, 900]})
    bag, taxed = stats.tax_bag(sales, 2026)
    # 2020: -1000; ETF +500 tassato pieno; ENI 2021 +300 usa la minus 2020 (resta 700, scade a fine 2024);
    # BTP 2025 -260 conta 125; ENI 2026 +900 usa i 125 del 2025, la minus 2020 è scaduta
    assert [round(x, 2) for x in taxed["tax"]] == [0, 130, 0, 0, round((900 - 125) * 0.26, 2)]
    assert bag.empty


def test_rebalance_buys_only_underweight():
    buy = stats.rebalance(pd.Series([800.0, 0.0]), pd.Series([50.0, 50.0]), 200)
    assert buy.tolist() == [0, 200]
    buy = stats.rebalance(pd.Series([600.0, 400.0]), pd.Series([50.0, 50.0]), 1000)
    assert buy.tolist() == [400, 600]
    assert stats.rebalance(pd.Series([1.0]), pd.Series([100.0]), 0).tolist() == [0]


def test_investments_db_roundtrip(tmp_path):
    url = f"sqlite:///{tmp_path / 'm.db'}"
    db.add_operation(TODAY, " VWCE ", "acquisto", 2, 100, 1, "ETF", url=url)
    db.add_operation(TODAY, "VWCE", "vendita", 1, 110, url=url)
    db.add_operation(TODAY, "ENI", "acquisto", 1, 10, 0, "Azione", user_id="altro", url=url)
    db.update_instruments(pd.DataFrame({"name": ["VWCE"], "target": [60]}), url=url)
    ops, ins = db.load_investments(url=url)
    assert len(ops) == 2 and ins[["name", "kind", "price", "target"]].values.tolist() == [["VWCE", "ETF", 100, 60]]
    db.delete_operations(ops["id"].tolist(), url=url)
    ops, ins = db.load_investments(url=url)
    assert ops.empty and ins.empty and len(db.load_investments("altro", url=url)[1]) == 1
