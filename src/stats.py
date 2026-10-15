"""Calcoli sui movimenti: funzioni pure su DataFrame (colonne date, kind, amount, category, method)."""
from datetime import date, timedelta

import numpy as np
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


# --- libertà finanziaria (FIRE) ---------------------------------------------------------------------
# Rendimento reale (dopo l'inflazione) netto di costi e tasse, e volatilità annua, per profilo. Ordini di grandezza
# storici: azionario globale ~5% reale, obbligazioni ~1-2%; tolti ~0,3% di costi ETF e l'effetto del 26% sui guadagni.
# ponytail: rendimenti annui normali e indipendenti, nessuna crisi lunga; bootstrap su serie storiche se serve più realismo
FIRE_PROFILES = {"Prudente": (0.02, 0.06), "Bilanciato": (0.035, 0.10), "Aggressivo": (0.05, 0.15)}
WITHDRAWAL_RATE = 0.035  # quota prelevabile ogni anno senza esaurire il capitale su orizzonti lunghi (sotto il 4% USA)
FIRE_YEARS, FIRE_RUNS, FIRE_SEED = 50, 2000, 0


def fire_defaults(df: pd.DataFrame, today: date) -> tuple[float, float]:
    """Risparmio medio mensile e spesa annua dai mesi chiusi degli ultimi 12 con almeno un movimento."""
    if df.empty:
        return 0.0, 0.0
    bal = monthly_balance(df, today, 13).iloc[:-1]  # il mese in corso è incompleto
    bal = bal[(bal["income"] > 0) | (bal["expense"] > 0)]
    if bal.empty:
        return 0.0, 0.0
    return float(bal["saving"].mean()), float(bal["expense"].mean() * 12)


def fire_paths(start: float, monthly_saving: float, mu: float, sigma: float,
               years: int = FIRE_YEARS, runs: int = FIRE_RUNS, seed: int = FIRE_SEED) -> np.ndarray:
    """Patrimonio reale a inizio di ogni anno (runs x years+1): rendimento casuale, poi si aggiunge il risparmio dell'anno."""
    r = np.random.default_rng(seed).normal(mu, sigma, size=(runs, years))
    w = np.empty((runs, years + 1))
    w[:, 0] = start
    for t in range(years):
        w[:, t + 1] = w[:, t] * (1 + r[:, t]) + monthly_saving * 12
    return w


def years_to_target(paths: np.ndarray, target: float) -> np.ndarray:
    """Per ogni simulazione il primo anno con patrimonio >= target, inf se non ci arriva."""
    hit = paths >= target
    return np.where(hit.any(axis=1), hit.argmax(axis=1), np.inf)


# --- investimenti ----------------------------------------------------------------------------------
TAX_RATE = 0.26
GOV_SHARE = 12.5 / 26  # titoli di Stato: guadagni e perdite contano al 48,08% (tassati al 12,5% invece del 26%)
BAG_YEARS = 4  # una minusvalenza si usa fino al 31/12 del quarto anno dopo quello in cui nasce


def ledger(ops: pd.DataFrame, ins: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Costo medio ponderato (come la banca in regime amministrato). Commissioni d'acquisto nel costo, di vendita
    tolte dall'incasso. Ritorna (posizioni con quote > 0, vendite con guadagno realizzato in €)."""
    kinds = dict(zip(ins["name"], ins["kind"]))
    held: dict[str, list[float]] = {}  # nome -> [quote, costo totale]
    sales = []
    for o in ops.sort_values(["date", "id"]).itertuples():
        q, cost = held.setdefault(o.name, [0.0, 0.0])
        if o.side == "acquisto":
            held[o.name] = [q + o.quantity, cost + o.quantity * o.price + o.fees]
        else:
            avg = cost / q if q > 0 else 0.0
            sales.append({"date": o.date, "name": o.name, "kind": kinds.get(o.name, "ETF"),
                          "gain": o.quantity * (o.price - avg) - o.fees})
            held[o.name] = [q - o.quantity, cost - avg * o.quantity]
    pos = pd.DataFrame([(n, q, c) for n, (q, c) in held.items() if q > 1e-9], columns=["name", "quantity", "cost"])
    pos = pos.merge(ins, on="name")
    pos["avg_price"] = pos["cost"] / pos["quantity"]
    pos["value"] = pos["quantity"] * pos["price"]
    pos["gain"] = pos["value"] - pos["cost"]
    pos["gain_pct"] = pos["gain"] / pos["cost"] * 100
    sales = pd.DataFrame(sales, columns=["date", "name", "kind", "gain"])
    return pos, sales.astype({"date": "datetime64[ns]", "gain": float})  # tipi giusti anche senza vendite


def tax_bag(sales: pd.DataFrame, year: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Zainetto fiscale. Le perdite (anche di ETF) diventano minusvalenze; i guadagni di azioni, ETC e obbligazioni
    le consumano dalla più vecchia ancora valida, quelli di ETF no (redditi di capitale). Ritorna (minusvalenze ancora
    utilizzabili in `year`: anno, scadenza, importo iniziale, residuo; vendite con la tassa stimata)."""
    bag = []  # [anno, importo, residuo]
    taxes = []
    for s in sales.sort_values("date").itertuples():
        y = s.date.year
        base = s.gain * (GOV_SHARE if s.kind == "Titolo di Stato" else 1)
        if base < 0:
            bag.append([y, -base, -base])
            base = 0.0
        elif s.kind != "ETF":
            for m in bag:
                if m[0] + BAG_YEARS >= y and m[0] <= y:
                    used = min(m[2], base)
                    m[2] -= used
                    base -= used
        taxes.append(base * TAX_RATE)
    out = pd.DataFrame([(a, a + BAG_YEARS, b, r) for a, b, r in bag if r > 0.005 and a + BAG_YEARS >= year],
                       columns=["year", "expires", "amount", "residual"])
    return out, sales.assign(tax=taxes)


def rebalance(values: pd.Series, targets: pd.Series, cash: float) -> pd.Series:
    """Ribilanciamento solo comprando: divide `cash` tra gli strumenti sotto il peso obiettivo (targets in %),
    in proporzione a quanto mancano per tornare al peso dopo il versamento."""
    gap = (targets / targets.sum() * (values.sum() + cash) - values).clip(lower=0)
    return gap * 0 if cash <= 0 or gap.sum() == 0 else gap * cash / gap.sum()
