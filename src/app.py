import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import pandas as pd
import streamlit as st

from src import db, stats
from src.ui.theme import categorical, chart, hex_color, page_css

LOGO_DIR = Path(__file__).resolve().parent.parent / "assets"
USER = "me"  # ponytail: utente unico finché non arriva il login

st.set_page_config(page_title="Soft Investing", page_icon=str(LOGO_DIR / "logo-mark.svg"), layout="wide")
mode = st.context.theme.type or "dark"
st.logo(str(LOGO_DIR / ("logo-mark.svg" if mode == "dark" else "logo-mark-light.svg")), size="large")
st.html(page_css(mode))


def euro(x: float) -> str:
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def delta(now: float, before: float) -> str | None:
    return None if before == 0 else f"{(now - before) / before * 100:+.0f}% vs periodo prima"


# --- nuovo movimento -------------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### Nuovo movimento")
    kind = st.segmented_control("Tipo", db.KINDS, default="spesa", format_func=str.capitalize) or "spesa"
    with st.form("new", clear_on_submit=True, border=False):
        day = st.date_input("Data", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        amount = st.number_input("Importo (€)", min_value=0.0, step=1.0, format="%.2f")
        category = st.selectbox("Categoria", db.EXPENSE_CATEGORIES if kind == "spesa" else db.INCOME_CATEGORIES)
        method = st.selectbox("Metodo di pagamento" if kind == "spesa" else "Ricevuto con", db.METHODS)
        note = st.text_input("Nota", placeholder="facoltativa")
        if st.form_submit_button("Aggiungi", type="primary", use_container_width=True):
            if amount <= 0:
                st.error("Inserisci un importo maggiore di zero.")
            else:
                db.add(day, kind, amount, category, method, note, user_id=USER)
                st.toast(f"{kind.capitalize()} di {euro(amount)} salvata")

df = db.load(USER)
today = date.today()

st.title("Le tue finanze")
st.caption("Spese, entrate e risparmio. Inserisci i movimenti dalla barra a sinistra.")

if df.empty:
    st.info("Nessun movimento ancora. Aggiungi la prima spesa o entrata dalla barra a sinistra.")
    st.stop()

# --- KPI -------------------------------------------------------------------------------------------
cols = st.columns(3)
for col, (label, freq) in zip(cols, (("Speso oggi", "D"), ("Questa settimana", "W"), ("Questo mese", "M"))):
    now, before = stats.totals(df, today, freq)
    col.metric(label, euro(now), delta(now, before), delta_color="inverse")
month = stats.monthly_balance(df, today, 1).iloc[-1]
cols = st.columns(3)
cols[0].metric("Entrate del mese", euro(month["income"]))
cols[1].metric("Risparmio del mese", euro(month["saving"]),
               None if pd.isna(month["rate"]) else f"{month['rate']:.0f}% delle entrate")
cols[2].metric("Media al giorno nel mese", euro(month["expense"] / today.day))

tab_trend, tab_balance, tab_list = st.tabs(["Spese", "Entrate e risparmio", "Movimenti"])

# --- spese -----------------------------------------------------------------------------------------
with tab_trend:
    label = st.segmented_control("Periodo", list(stats.PERIODS), default="Mese") or "Mese"
    freq = stats.PERIODS[label]
    start = stats.period_start(today, freq)
    accent, muted = hex_color(mode, "accent"), hex_color(mode, "muted")

    hist = stats.history(df, today, freq)
    hist["label"] = hist["period"].dt.strftime({"D": "%d/%m", "W": "%d/%m", "M": "%m/%y"}[freq])
    st.markdown(f"**Andamento delle spese** · ultimi {stats.HISTORY[freq]} "
                f"{ {'D': 'giorni', 'W': 'settimane', 'M': 'mesi'}[freq] }")
    bars = alt.Chart(hist).mark_bar(cornerRadiusTopLeft=6, cornerRadiusTopRight=6, color=accent).encode(
        x=alt.X("label:O", title=None, sort=None, axis=alt.Axis(labelAngle=0, labelOverlap=True)),
        y=alt.Y("amount:Q", title="€"),
        tooltip=[alt.Tooltip("period:T", title="Periodo", format="%d/%m/%Y"),
                 alt.Tooltip("amount:Q", title="Speso €", format=",.2f")])
    avg = alt.Chart(hist).mark_rule(strokeDash=[4, 4], color=muted).encode(y="mean(amount):Q")
    st.altair_chart(chart(bars + avg, mode), use_container_width=True)
    st.caption("Linea tratteggiata: media del periodo.")

    left, right = st.columns(2)
    period_name = {"D": "oggi", "W": "questa settimana", "M": "questo mese"}[freq]
    for col, column, title in ((left, "category", "Per categoria"), (right, "method", "Per metodo di pagamento")):
        with col:
            st.markdown(f"**{title}** · {period_name}")
            br = stats.breakdown(df, start, today, column)
            if br.empty:
                st.caption("Nessuna spesa nel periodo.")
                continue
            if column == "category":
                if len(br) > 7:  # la palette ha 7 colori: oltre le prime 6 categorie si somma in "Altre"
                    br = pd.concat([br.head(6), pd.DataFrame({"category": ["Altre"], "amount": [br["amount"][6:].sum()]})])
                c =alt.Chart(br).mark_arc(innerRadius=70, cornerRadius=4, padAngle=0.01).encode(
                    theta="amount:Q",
                    color=alt.Color("category:N", title=None, sort=br["category"].tolist(), legend=alt.Legend(orient="right"),
                                    scale=alt.Scale(range=categorical(mode))),
                    tooltip=[alt.Tooltip("category:N", title="Categoria"),
                             alt.Tooltip("amount:Q", title="€", format=",.2f")])
            else:
                c = alt.Chart(br).mark_bar(cornerRadiusTopRight=6, cornerRadiusBottomRight=6).encode(
                    y=alt.Y("method:N", title=None, sort="-x",
                             axis=alt.Axis(labelFont="Plus Jakarta Sans", labelFontSize=13, minExtent=80, labelLimit=160)), x=alt.X("amount:Q", title="€"),
                    color=alt.Color("method:N", legend=None, scale=alt.Scale(range=categorical(mode))),
                    tooltip=[alt.Tooltip("method:N", title="Metodo"),
                             alt.Tooltip("amount:Q", title="€", format=",.2f")])
            st.altair_chart(chart(c, mode, 280), use_container_width=True)

    st.markdown("**Questo mese contro il mese scorso** · spesa cumulata giorno per giorno")
    cum = stats.cumulative_month(df, today)
    line = alt.Chart(cum).mark_line(strokeWidth=2.5, interpolate="step-after").encode(
        x=alt.X("day:Q", title="Giorno del mese", scale=alt.Scale(domain=[1, 31])),
        y=alt.Y("amount:Q", title="€"),
        color=alt.Color("serie:N", title=None, scale=alt.Scale(domain=["Questo mese", "Mese scorso"],
                                                               range=[accent, muted])),
        tooltip=[alt.Tooltip("serie:N", title=" "), alt.Tooltip("day:Q", title="Giorno"),
                 alt.Tooltip("amount:Q", title="Cumulato €", format=",.2f")])
    st.altair_chart(chart(line, mode, 280), use_container_width=True)

# --- entrate e risparmio ---------------------------------------------------------------------------
with tab_balance:
    bal = stats.monthly_balance(df, today)
    bal["label"] = bal["month"].dt.strftime("%m/%y")
    long = bal.melt(id_vars=["month", "label"], value_vars=["income", "expense"], var_name="tipo", value_name="amount")
    long["tipo"] = long["tipo"].map({"income": "Entrate", "expense": "Spese"})
    st.markdown("**Entrate e spese per mese** · ultimi 12 mesi")
    grouped = alt.Chart(long).mark_bar(cornerRadiusTopLeft=5, cornerRadiusTopRight=5).encode(
        x=alt.X("label:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
        xOffset="tipo:N", y=alt.Y("amount:Q", title="€"),
        color=alt.Color("tipo:N", title=None, scale=alt.Scale(domain=["Entrate", "Spese"],
                                                              range=[hex_color(mode, "r-gold"), hex_color(mode, "r-stag")])),
        tooltip=[alt.Tooltip("month:T", title="Mese", format="%B %Y"), alt.Tooltip("tipo:N", title=" "),
                 alt.Tooltip("amount:Q", title="€", format=",.2f")])
    st.altair_chart(chart(grouped, mode), use_container_width=True)

    st.markdown("**Tasso di risparmio** · quota delle entrate che resta a fine mese")
    rate = alt.Chart(bal.dropna(subset=["rate"])).mark_line(point=True, strokeWidth=2.5,
                                                            color=hex_color(mode, "accent")).encode(
        x=alt.X("label:O", title=None, sort=None, axis=alt.Axis(labelAngle=0)),
        y=alt.Y("rate:Q", title="%"),
        tooltip=[alt.Tooltip("month:T", title="Mese", format="%B %Y"), alt.Tooltip("rate:Q", title="Risparmio %"),
                 alt.Tooltip("saving:Q", title="Risparmio €", format=",.2f")])
    zero = alt.Chart(pd.DataFrame({"y": [0]})).mark_rule(color=hex_color(mode, "muted")).encode(y="y:Q")
    st.altair_chart(chart(rate + zero, mode, 260), use_container_width=True)

# --- movimenti -------------------------------------------------------------------------------------
with tab_list:
    f1, f2, f3 = st.columns(3)
    kinds = f1.multiselect("Tipo", db.KINDS, default=db.KINDS, format_func=str.capitalize)
    cats = f2.multiselect("Categoria", sorted(df["category"].unique()), placeholder="Tutte")
    meths = f3.multiselect("Metodo", sorted(df["method"].unique()), placeholder="Tutti")
    view = df[df["kind"].isin(kinds)]
    if cats:
        view = view[view["category"].isin(cats)]
    if meths:
        view = view[view["method"].isin(meths)]
    view = view.assign(elimina=False)
    edited = st.data_editor(
        view, hide_index=True, use_container_width=True, disabled=[c for c in view.columns if c != "elimina"],
        column_order=["elimina", "date", "kind", "amount", "category", "method", "note"],
        column_config={"date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                       "kind": "Tipo", "amount": st.column_config.NumberColumn("Importo €", format="%.2f"),
                       "category": "Categoria", "method": "Metodo", "note": "Nota",
                       "elimina": st.column_config.CheckboxColumn("Elimina")})
    to_delete = edited.loc[edited["elimina"], "id"].tolist()
    if st.button(f"Elimina {len(to_delete)} movimenti selezionati", disabled=not to_delete):
        db.delete(to_delete, user_id=USER)
        st.rerun()
