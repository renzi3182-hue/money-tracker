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

st.set_page_config(page_title="Soft Investing", page_icon=str(LOGO_DIR / "logo-mark.svg"), layout="wide")
mode = st.context.theme.type or "dark"
st.logo(str(LOGO_DIR / ("logo-mark.svg" if mode == "dark" else "logo-mark-light.svg")), size="large")
st.html(page_css(mode))

# --- accesso ---------------------------------------------------------------------------------------
# Con [auth] nei secrets: login Google e solo allowed_email entra. Senza secrets: uso locale, utente "me".
if db.secret("auth"):
    if not st.user.is_logged_in:
        st.title("Le tue finanze")
        st.button("Accedi con Google", type="primary", on_click=st.login)
        st.stop()
    allowed = (db.secret("allowed_email") or "").strip().lower()
    if not allowed or (st.user.email or "").lower() != allowed:
        st.error("Questo account non ha accesso.")
        st.button("Esci", on_click=st.logout)
        st.stop()
    USER = allowed
    st.sidebar.caption(st.user.email)
    st.sidebar.button("Esci", on_click=st.logout)
elif db.remote():  # DB online senza login: dati esposti a chiunque, meglio fermarsi
    st.error("Manca la sezione [auth] nei secrets: login obbligatorio con il database online.")
    st.stop()
else:
    USER = "me"


def euro(x: float) -> str:
    return f"€ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def delta(now: float, before: float) -> str | None:
    return None if before == 0 else f"{(now - before) / before * 100:+.0f}% vs periodo prima"


def bump():
    """Cambia la chiave delle tabelle: dopo un'aggiunta o un'eliminazione le spunte non finiscono sulla riga sbagliata."""
    st.session_state.version = st.session_state.get("version", 0) + 1


# --- nuovo movimento -------------------------------------------------------------------------------
@st.dialog("Nuovo movimento")
def new_movement():
    kind = st.segmented_control("Tipo", db.KINDS, default="spesa", format_func=str.capitalize) or "spesa"
    with st.form("new", border=False):
        day = st.date_input("Data", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        amount = st.number_input("Importo (€)", min_value=0.0, step=1.0, format="%.2f")
        category = st.selectbox("Categoria", db.EXPENSE_CATEGORIES if kind == "spesa" else db.INCOME_CATEGORIES)
        method = st.selectbox("Metodo di pagamento" if kind == "spesa" else "Ricevuto con", db.METHODS)
        note = st.text_input("Nota", placeholder="facoltativa")
        if st.form_submit_button("Salva", type="primary", use_container_width=True):
            if amount <= 0:
                st.error("Inserisci un importo maggiore di zero.")
            else:
                db.add(day, kind, amount, category, method, note, user_id=USER)
                st.session_state.toast = f"{kind.capitalize()} di {euro(amount)} salvata"
                bump()
                st.rerun()


def add_button(key: str):
    if st.button("＋ Aggiungi movimento", key=key, type="primary"):
        new_movement()


def movement_table(view: pd.DataFrame, key: str):
    """Movimenti con spunta Elimina e bottone per cancellare quelli spuntati."""
    if view.empty:
        st.caption("Nessun movimento nel periodo.")
        return
    edited = st.data_editor(
        view.assign(elimina=False), hide_index=True, use_container_width=True,
        key=f"{key}_{st.session_state.get('version', 0)}",
        disabled=[c for c in view.columns if c != "elimina"],
        column_order=["elimina", "date", "kind", "amount", "category", "method", "note"],
        column_config={"date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                       "kind": "Tipo", "amount": st.column_config.NumberColumn("Importo €", format="%.2f"),
                       "category": "Categoria", "method": "Metodo", "note": "Nota",
                       "elimina": st.column_config.CheckboxColumn("Elimina")})
    to_delete = edited.loc[edited["elimina"], "id"].tolist()
    if st.button(f"Elimina {len(to_delete)} selezionati", key=f"del_{key}", disabled=not to_delete):
        db.delete(to_delete, user_id=USER)
        st.session_state.toast = f"{len(to_delete)} movimenti eliminati"
        bump()
        st.rerun()


if msg := st.session_state.pop("toast", None):
    st.toast(msg)

df = db.load(USER)
today = date.today()

st.title("Le tue finanze")
st.caption("Spese, entrate e risparmio del mese, della settimana e di oggi.")

if df.empty:
    st.info("Nessun movimento ancora. Aggiungi la prima spesa o entrata.")
    add_button("add_empty")
    st.stop()

accent, muted = hex_color(mode, "accent"), hex_color(mode, "muted")
NAMES = {"D": "oggi", "W": "questa settimana", "M": "questo mese"}
tab_m, tab_w, tab_d, tab_balance, tab_list = st.tabs(
    ["Mese", "Settimana", "Giorno", "Entrate e risparmio", "Tutti i movimenti"])

# --- mese / settimana / giorno ---------------------------------------------------------------------
def period_tab(freq: str):
    start = stats.period_start(today, freq)
    spent, before = stats.totals(df, today, freq)
    income = stats.total(df, start, today, "entrata")
    cols = st.columns(3)
    cols[0].metric(f"Speso {NAMES[freq]}", euro(spent), delta(spent, before), delta_color="inverse")
    cols[1].metric("Entrate", euro(income))
    cols[2].metric("Saldo", euro(income - spent),
                   f"{(income - spent) / income * 100:.0f}% delle entrate" if income else None)

    st.markdown(f"**Movimenti di {NAMES[freq]}**")
    add_button(f"add_{freq}")
    movement_table(df[df["date"].dt.date >= start], f"tbl_{freq}")

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
    for col, column, title in ((left, "category", "Per categoria"), (right, "method", "Per metodo di pagamento")):
        with col:
            st.markdown(f"**{title}** · {NAMES[freq]}")
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

    if freq == "M":
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


for tab, freq in ((tab_m, "M"), (tab_w, "W"), (tab_d, "D")):
    with tab:
        period_tab(freq)

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
    add_button("add_all")
    movement_table(view, "tbl_all")
