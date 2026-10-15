"""Calcoli sui movimenti: funzioni pure su DataFrame (colonne date, kind, amount, category, method)."""
from datetime import date, timedelta

import pandas as pd

PERIODS = {"Giorno": "D", "Settimana": "W", "Mese": "M"}
HISTORY = {"D": 30, "W": 12, "M": 12}  # quante barre nel grafico dell'andamento


def period_start(today: date, freq: str) -> date:
    if freq == "D":
        return today
    if freq == "W":
        return today - timedelta(days=today.weekday())  # settimana da lunedì
    return today.replace(day=1)


def previous_window(today: date, freq: str) -> tuple[date, date]:
    """Periodo precedente a pari giorni trascorsi: il mese scorso fino allo stesso giorno, non intero."""
    start = period_start(today, freq)
    if freq == "D":
        return today - timedelta(days=1), today - timedelta(days=1)
    if freq == "W":
        return start - timedelta(days=7), today - timedelta(days=7)
    prev_start = (start - timedelta(days=1)).replace(day=1)
    return prev_start, min(prev_start + (today - start), start - timedelta(days=1))


def _window(df: pd.DataFrame, start: date, end: date, kind: str = "spesa") -> pd.DataFrame:
    d = df["date"].dt.date
    return df[(df["kind"] == kind) & (d >= start) & (d <= end)]


def total(df: pd.DataFrame, start: date, end: date, kind: str = "spesa") -> float:
    return float(_window(df, start, end, kind)["amount"].sum())


def totals(df: pd.DataFrame, today: date, freq: str) -> tuple[float, float]:
    """Speso nel periodo corrente e nel precedente a pari giorni."""
    return total(df, period_start(today, freq), today), total(df, *previous_window(today, freq))


def breakdown(df: pd.DataFrame, start: date, end: date, column: str) -> pd.DataFrame:
    """Spese per categoria o metodo, dalla più grande."""
    w = _window(df, start, end)
    return (w.groupby(column, as_index=False)["amount"].sum().sort_values("amount", ascending=False)
            .reset_index(drop=True))


def history(df: pd.DataFrame, today: date, freq: str) -> pd.DataFrame:
    """Spese per giorno/settimana/mese sulle ultime HISTORY[freq] barre, periodi vuoti a zero."""
    n, start = HISTORY[freq], period_start(today, freq)
    if freq == "D":
        first = start - timedelta(days=n - 1)
    elif freq == "W":
        first = start - timedelta(weeks=n - 1)
    else:
        first = (pd.Timestamp(start) - pd.DateOffset(months=n - 1)).date()
    w = _window(df, first, today)
    keys = w["date"].apply(lambda t: period_start(t.date(), freq))
    sums = w.groupby(keys)["amount"].sum()
    if freq == "M":
        index = [d.date() for d in pd.date_range(first, start, freq="MS")]
    else:
        index = [d.date() for d in pd.date_range(first, start, freq="7D" if freq == "W" else "D")]
    return pd.DataFrame({"period": pd.to_datetime(index), "amount": [float(sums.get(i, 0.0)) for i in index]})


def monthly_balance(df: pd.DataFrame, today: date, months: int = 12) -> pd.DataFrame:
    """Entrate, spese, risparmio e tasso di risparmio (% delle entrate) per mese."""
    first = (pd.Timestamp(today.replace(day=1)) - pd.DateOffset(months=months - 1))
    index = pd.date_range(first, today.replace(day=1), freq="MS")
    w = df[df["date"] >= first]
    piv = (w.assign(m=w["date"].dt.to_period("M").dt.to_timestamp())
           .pivot_table(index="m", columns="kind", values="amount", aggfunc="sum")
           .reindex(index=index, columns=["entrata", "spesa"]).fillna(0.0))
    out = pd.DataFrame({"month": index, "income": piv["entrata"].values, "expense": piv["spesa"].values})
    out["saving"] = out["income"] - out["expense"]
    out["rate"] = (out["saving"] / out["income"].where(out["income"] > 0) * 100).round(1)
    return out


def cumulative_month(df: pd.DataFrame, today: date) -> pd.DataFrame:
    """Spesa cumulata giorno per giorno: mese corrente (fino a oggi) e mese scorso (intero)."""
    start = today.replace(day=1)
    prev_start = (start - timedelta(days=1)).replace(day=1)
    rows = []
    for label, a, b in (("Questo mese", start, today), ("Mese scorso", prev_start, start - timedelta(days=1))):
        days = pd.date_range(a, b, freq="D")
        daily = _window(df, a, b).groupby(df["date"].dt.normalize())["amount"].sum().reindex(days, fill_value=0.0)
        rows.append(pd.DataFrame({"day": days.day, "amount": daily.cumsum().values, "serie": label}))
    return pd.concat(rows, ignore_index=True)
