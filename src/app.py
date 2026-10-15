import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import altair as alt
import numpy as np
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
# Con [auth] nei secrets: login Google; entra solo allowed_email, o chiunque con allowed_email = "*"
# (ognuno vede solo i suoi movimenti, user_id = email). Senza secrets: uso locale, utente "me".
if db.secret("auth"):
    if not st.user.is_logged_in:
        st.title("Le tue finanze")
        st.button("Accedi con Google", type="primary", on_click=st.login)
        st.stop()
    allowed = (db.secret("allowed_email") or "").strip().lower()
    email = (st.user.email or "").strip().lower()
    if not email or not allowed or (allowed != "*" and email != allowed):
        st.error("Questo account non ha accesso.")
        st.button("Esci", on_click=st.logout)
        st.stop()
    USER = email
    st.sidebar.caption(st.user.email)
    st.sidebar.button("Esci", on_click=st.logout)
elif db.remote() and not db.secret("private_app"):  # DB online senza login: dati esposti a chiunque, meglio fermarsi
    st.error("Manca la sezione [auth] nei secrets: login obbligatorio con il database online.")
    st.stop()
else:  # locale, o app privata su Community Cloud (private_app = true: l'accesso lo filtra Streamlit)
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


def checked_table(view: pd.DataFrame, key: str, order: list[str], config: dict, delete, noun: str, empty: str):
    """Tabella con spunta Elimina e bottone per cancellare le righe spuntate (delete riceve gli id)."""
    if view.empty:
        st.caption(empty)
        return
    edited = st.data_editor(
        view.assign(elimina=False), hide_index=True, use_container_width=True,
        key=f"{key}_{st.session_state.get('version', 0)}",
        disabled=[c for c in view.columns if c != "elimina"], column_order=["elimina", *order],
        column_config={**config, "elimina": st.column_config.CheckboxColumn("Elimina")})
    to_delete = edited.loc[edited["elimina"], "id"].tolist()
    if st.button(f"Elimina {len(to_delete)} selezionati", key=f"del_{key}", disabled=not to_delete):
        delete(to_delete, user_id=USER)
        st.session_state.toast = f"{len(to_delete)} {noun} eliminat{'e' if noun == 'operazioni' else 'i'}"
        bump()
        st.rerun()


def movement_table(view: pd.DataFrame, key: str):
    checked_table(view, key, ["date", "kind", "amount", "category", "method", "note"],
                  {"date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                   "kind": "Tipo", "amount": st.column_config.NumberColumn("Importo €", format="%.2f"),
                   "category": "Categoria", "method": "Metodo", "note": "Nota"}, db.delete, "movimenti",
                  "Nessun movimento nel periodo.")


if msg := st.session_state.pop("toast", None):
    st.toast(msg)

# --- libertà finanziaria ---------------------------------------------------------------------------
def years_text(y: float) -> str:
    return "oltre 50 anni" if y == float("inf") else "già ora" if y == 0 else f"{y:.0f} {'anno' if y == 1 else 'anni'}"


def fire_tab(capital0: float):
    st.markdown("**Quando potrai vivere dei tuoi investimenti?**")
    st.caption("Libertà finanziaria (FIRE) = avere abbastanza soldi investiti da pagare le tue spese con i loro "
               "rendimenti, senza dover lavorare. Il capitale parte dal valore del tuo portafoglio, risparmio e spese "
               "dalla media dei tuoi ultimi 12 mesi chiusi: puoi cambiarli.")
    saving0, expense0 = stats.fire_defaults(df, today)
    c1, c2, c3 = st.columns(3)
    capital = c1.number_input("Quanto hai già investito (€)", min_value=0.0, value=float(round(capital0)), step=1000.0, format="%.0f")
    saving = c2.number_input("Quanto investi al mese (€)", min_value=0.0, value=float(max(round(saving0), 0)),
                             step=50.0, format="%.0f")
    expense = c3.number_input("Di quanto vivresti all'anno (€)", min_value=0.0, value=float(round(expense0)),
                              step=500.0, format="%.0f", help="Spese annue di oggi: i calcoli sono già al netto dell'inflazione.")
    profile = st.segmented_control("Come investi", list(stats.FIRE_PROFILES), default="Bilanciato", required=True,
                                   help="Prudente: soprattutto obbligazioni. Bilanciato: metà azioni. Aggressivo: quasi solo azioni.")
    target = round(expense / stats.WITHDRAWAL_RATE, -3)
    if expense <= 0:
        st.info("Inserisci di quanto vivresti all'anno.")
    else:
        mu, sigma = stats.FIRE_PROFILES[profile]
        paths = stats.fire_paths(capital, saving, mu, sigma)
        yrs = stats.years_to_target(paths, target)
        p10, p50, p90 = np.percentile(yrs, [10, 50, 90], method="lower")  # "lower": con inf l'interpolazione darebbe nan
        faster = np.percentile(stats.years_to_target(stats.fire_paths(capital, saving + 100, mu, sigma), target), 50, method="lower")
        m = st.columns(3)
        m[0].metric("Ti servono (€)", f"{target / 1000:,.0f} mila".replace(",", "."),
                    help=f"Spese annue / {stats.WITHDRAWAL_RATE:.1%}".replace(".", ","))
        m[1].metric("Ci arrivi in (caso medio)", years_text(p50), help="Metà delle simulazioni ci arriva prima, metà dopo.")
        m[2].metric("Con 100 € in più al mese", years_text(faster),
                    None if faster == float("inf") or p50 == float("inf") else f"{faster - p50:+.0f} anni", delta_color="inverse")
        rate = f"{stats.WITHDRAWAL_RATE:.1%}".replace(".", ",")
        st.markdown(f"Nel caso **fortunato** ci arrivi in **{years_text(p10)}**, in quello **sfortunato** in "
                    f"**{years_text(p90)}**. Con {euro(target).replace(',00', '')} investiti puoi prelevare ogni anno il "
                    f"{rate} ({euro(expense).replace(',00', '')}) e storicamente il capitale dura anche per 40-50 anni.")
        band = pd.DataFrame({"anno": range(stats.FIRE_YEARS + 1), **{k: np.percentile(paths, q, axis=0)
                                                                     for k, q in (("basso", 10), ("medio", 50), ("alto", 90))}})
        band = band[band["anno"] <= min(stats.FIRE_YEARS, (p90 if p90 != float("inf") else stats.FIRE_YEARS) + 5)]
        x = alt.X("anno:Q", title="Anni da oggi")
        area = alt.Chart(band).mark_area(opacity=0.25, color=accent).encode(
            x=x, y=alt.Y("basso:Q", title="Patrimonio € (di oggi)"), y2="alto:Q",
            tooltip=[alt.Tooltip("anno:Q", title="Anno"), alt.Tooltip("basso:Q", title="Sfortunato €", format=",.0f"),
                     alt.Tooltip("medio:Q", title="Medio €", format=",.0f"), alt.Tooltip("alto:Q", title="Fortunato €", format=",.0f")])
        mid = alt.Chart(band).mark_line(strokeWidth=2.5, color=accent).encode(x=x, y="medio:Q")
        goal = alt.Chart(pd.DataFrame({"y": [target]})).mark_rule(strokeDash=[6, 4], color=hex_color(mode, "r-gold")).encode(y="y:Q")
        st.markdown("**Come cresce il patrimonio** · linea = caso medio, fascia = dal caso sfortunato al fortunato, "
                    "tratteggio = obiettivo")
        st.altair_chart(chart(area + mid + goal, mode), use_container_width=True)
    st.caption(f"{stats.FIRE_RUNS} simulazioni di futuri possibili, con anni buoni e cattivi a caso. Rendimento dopo "
               "inflazione, costi e tasse: Prudente 2%, Bilanciato 3,5%, Aggressivo 5% l'anno in media. Sono ipotesi, "
               "non previsioni, e non è consulenza finanziaria.")

# --- investimenti ----------------------------------------------------------------------------------
NEW = "＋ Nuovo strumento"


@st.dialog("Nuova operazione")
def new_operation(pos: pd.DataFrame, names: list[str]):
    side = st.segmented_control("Tipo", db.SIDES, default="acquisto", format_func=str.capitalize) or "acquisto"
    choices = names + [NEW] if side == "acquisto" else pos["name"].tolist()
    if not choices:
        st.info("Non hai strumenti da vendere.")
        return
    pick = st.selectbox("Strumento", choices)
    with st.form("new_op", border=False):
        kind = None
        if pick == NEW:
            name = st.text_input("Nome o ticker", placeholder="es. VWCE")
            kind = st.selectbox("Tipo di strumento", db.ASSET_KINDS,
                                help="Serve per le tasse: i guadagni degli ETF non recuperano le minusvalenze.")
        else:
            name = pick
        day = st.date_input("Data", value=date.today(), max_value=date.today(), format="DD/MM/YYYY")
        qty = st.number_input("Quote", min_value=0.0, step=1.0, format="%.4f")
        price = st.number_input("Prezzo per quota (€)", min_value=0.0, step=1.0, format="%.4f")
        fees = st.number_input("Commissioni (€)", min_value=0.0, step=1.0, format="%.2f")
        if st.form_submit_button("Salva", type="primary", use_container_width=True):
            held = pos.set_index("name")["quantity"].get(name, 0.0)
            if not name.strip() or (pick == NEW and name.strip() in names):
                st.error("Scrivi un nome nuovo per lo strumento.")
            elif qty <= 0 or price <= 0:
                st.error("Quote e prezzo devono essere maggiori di zero.")
            elif side == "vendita" and qty > held + 1e-9:
                st.error(f"Ne hai solo {held:g} quote.")
            else:
                db.add_operation(day, name, side, qty, price, fees, kind, user_id=USER)
                st.session_state.toast = f"{side.capitalize()} di {name.strip()} salvato"
                bump()
                st.rerun()


def save_button(edited: pd.DataFrame, before: pd.DataFrame, column: str, key: str, label: str):
    changed = edited[edited[column] != before[column]]
    if st.button(label, key=key, disabled=changed.empty):
        db.update_instruments(changed[["name", column]], user_id=USER)
        st.session_state.toast = "Salvato"
        bump()
        st.rerun()


def investments():
    ops, ins = db.load_investments(USER)
    pos, sales = stats.ledger(ops, ins)
    tab_pf, tab_reb, tab_bag, tab_free = st.tabs(["Portafoglio", "Ribilanciatore", "Zainetto fiscale",
                                                  "Libertà finanziaria"])
    version = st.session_state.get("version", 0)

    with tab_pf:
        value, cost = pos["value"].sum(), pos["cost"].sum()
        m = st.columns(3)
        m[0].metric("Valore attuale", euro(value))
        m[1].metric("Investito", euro(cost), help="Quanto hai pagato le quote che hai ancora, commissioni comprese.")
        m[2].metric("Guadagno non realizzato", euro(value - cost),
                    f"{(value - cost) / cost * 100:+.1f}%".replace(".", ",") if cost else None)
        if st.button("＋ Aggiungi operazione", type="primary"):
            new_operation(pos, ins["name"].tolist())
        if not pos.empty:
            st.markdown("**Posizioni** · aggiorna a mano il prezzo attuale (lo trovi sul sito del tuo broker)")
            cols = ["name", "kind", "quantity", "avg_price", "price", "value", "gain", "gain_pct"]
            edited = st.data_editor(
                pos[cols], hide_index=True, use_container_width=True, key=f"pos_{version}",
                disabled=[c for c in cols if c != "price"],
                column_config={"name": "Strumento", "kind": "Tipo",
                               "quantity": st.column_config.NumberColumn("Quote", format="%g"),
                               "avg_price": st.column_config.NumberColumn("Prezzo medio €", format="%.2f"),
                               "price": st.column_config.NumberColumn("Prezzo attuale €", format="%.2f", min_value=0.0001),
                               "value": st.column_config.NumberColumn("Valore €", format="%.2f"),
                               "gain": st.column_config.NumberColumn("Guadagno €", format="%+.2f"),
                               "gain_pct": st.column_config.NumberColumn("Guadagno %", format="%+.1f")})
            save_button(edited, pos[cols], "price", "save_prices", "Salva prezzi")
        st.markdown("**Operazioni**")
        checked_table(ops, "tbl_ops", ["date", "name", "side", "quantity", "price", "fees"],
                      {"date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"), "name": "Strumento",
                       "side": "Tipo", "quantity": st.column_config.NumberColumn("Quote", format="%g"),
                       "price": st.column_config.NumberColumn("Prezzo €", format="%.2f"),
                       "fees": st.column_config.NumberColumn("Commissioni €", format="%.2f")},
                      db.delete_operations, "operazioni", "Nessuna operazione. Aggiungi il tuo primo acquisto.")

    with tab_reb:
        st.markdown("**Dove mettere il versamento di questo mese**")
        st.caption("Scegli quanto pesa ogni strumento nel portafoglio ideale. Il ribilanciatore divide il versamento "
                   "solo tra gli strumenti sotto il loro peso: così ti riavvicini all'obiettivo senza vendere, quindi "
                   "senza pagare tasse né commissioni di vendita.")
        if ins.empty:
            st.info("Aggiungi prima un'operazione nel Portafoglio.")
        else:
            reb = ins[["name", "price", "target"]].merge(pos[["name", "value"]], on="name", how="left").fillna({"value": 0.0})
            edited = st.data_editor(
                reb[["name", "target"]], hide_index=True, use_container_width=True, key=f"target_{version}",
                disabled=["name"], column_config={
                    "name": "Strumento",
                    "target": st.column_config.NumberColumn("Peso obiettivo %", min_value=0, max_value=100, step=1, format="%g")})
            save_button(edited, reb[["name", "target"]], "target", "save_targets", "Salva pesi")
            total = edited["target"].sum()
            cash = st.number_input("Quanto versi questo mese (€)", min_value=0.0, step=50.0, format="%.0f",
                                   value=float(max(round(stats.fire_defaults(df, today)[0]), 0)) or 500.0)
            if total <= 0:
                st.info("Dai un peso obiettivo ad almeno uno strumento.")
            else:
                if abs(total - 100) > 0.01:
                    st.warning(f"I pesi sommano a {total:g}%: li riporto a 100 in proporzione.")
                buy = stats.rebalance(reb["value"], edited["target"], cash)
                after = reb["value"] + buy
                out = pd.DataFrame({
                    "Strumento": reb["name"], "Peso obiettivo %": edited["target"] / total * 100,
                    "Peso oggi %": reb["value"] / reb["value"].sum() * 100 if reb["value"].sum() else 0.0,
                    "Compra €": buy, "Quote circa": buy / reb["price"],
                    "Peso dopo %": after / after.sum() * 100 if after.sum() else 0.0})
                st.dataframe(out, hide_index=True, use_container_width=True, column_config={
                    c: st.column_config.NumberColumn(format="%.1f") for c in out.columns if "%" in c} | {
                    "Compra €": st.column_config.NumberColumn(format="%.2f"),
                    "Quote circa": st.column_config.NumberColumn(format="%.2f")})
                st.caption("Quote circa = importo / prezzo attuale: arrotonda in base a quello che il broker permette.")

    with tab_bag:
        year = today.year
        bag, taxed = stats.tax_bag(sales, year)
        st.markdown("**Zainetto fiscale** · le perdite che puoi ancora recuperare")
        st.caption("Quando vendi in perdita nasce una minusvalenza: per 4 anni (fino al 31/12 del quarto anno dopo) "
                   "riduce le tasse sui guadagni futuri. Attenzione: i guadagni degli ETF non la usano, quelli di "
                   "azioni, ETC e obbligazioni sì. I titoli di Stato contano al 48% perché tassati al 12,5%.")
        m = st.columns(3)
        m[0].metric("Minusvalenze da usare", euro(bag["residual"].sum()))
        expiring = bag.loc[bag["expires"] == year, "residual"].sum()
        m[1].metric(f"Scadono a fine {year}", euro(expiring))
        m[2].metric(f"Tasse stimate {year}", euro(taxed.loc[taxed["date"].dt.year == year, "tax"].sum()),
                    help="Sui guadagni realizzati quest'anno, dopo lo zainetto. Le calcola la banca in regime "
                         "amministrato: qui servono per controllare e decidere.")
        if expiring > 0:
            usable = pos[(pos["kind"] != "ETF") & (pos["gain"] > 0)]
            if usable.empty:
                st.info(f"Hai {euro(expiring)} di minusvalenze che scadono a fine anno, ma nessuna posizione non-ETF in "
                        "guadagno con cui usarle.")
            else:
                st.warning(f"Hai {euro(expiring)} di minusvalenze che scadono a fine anno. Vendendo in guadagno "
                           f"{', '.join(usable['name'])} (e ricomprando, se vuoi tenerli) le recuperi invece di perderle.")
        if not bag.empty:
            st.dataframe(bag, hide_index=True, use_container_width=True, column_config={
                "year": st.column_config.NumberColumn("Nata nel", format="%d"),
                "expires": st.column_config.NumberColumn("Scade il 31/12 del", format="%d"),
                "amount": st.column_config.NumberColumn("Importo €", format="%.2f"),
                "residual": st.column_config.NumberColumn("Ancora da usare €", format="%.2f")})
        if not taxed.empty:
            st.markdown("**Vendite** · guadagno realizzato e tasse stimate")
            st.dataframe(taxed.sort_values("date", ascending=False), hide_index=True, use_container_width=True,
                         column_config={"date": st.column_config.DateColumn("Data", format="DD/MM/YYYY"),
                                        "name": "Strumento", "kind": "Tipo",
                                        "gain": st.column_config.NumberColumn("Guadagno €", format="%+.2f"),
                                        "tax": st.column_config.NumberColumn("Tasse €", format="%.2f")})
        st.caption("Stima: costo medio come la banca, commissioni incluse; non considera dividendi e cedole né la parte "
                   "di titoli di Stato dentro gli ETF. Non è consulenza fiscale.")

    with tab_free:
        fire_tab(pos["value"].sum())


df = db.load(USER)
today = date.today()

st.title("Le tue finanze")
section = st.segmented_control("Sezione", ["Spese ed entrate", "Investimenti"], default="Spese ed entrate",
                               required=True, label_visibility="collapsed")
accent, muted = hex_color(mode, "accent"), hex_color(mode, "muted")
if section == "Investimenti":
    investments()
    st.stop()
st.caption("Spese, entrate e risparmio del mese, della settimana e di oggi.")

if df.empty:
    st.info("Nessun movimento ancora. Aggiungi la prima spesa o entrata.")
    add_button("add_empty")
    st.stop()

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
                c = alt.Chart(br).mark_arc(innerRadius=70, cornerRadius=4, padAngle=0.01).encode(
                    theta="amount:Q",
                    color=alt.Color("category:N", title=None, sort=br["category"].tolist(), legend=alt.Legend(orient="bottom", columns=2),
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
