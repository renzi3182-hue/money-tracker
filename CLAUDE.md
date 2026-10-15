# money-tracker

Dashboard delle finanze personali: spese giornaliere, settimanali e mensili, entrate e tasso di risparmio, con grafici. Movimenti inseriti a mano dalla barra laterale (anche il metodo di pagamento). Secondo software del brand Soft Investing (identità visiva: `../../concepts/brand-soft-investing.md`). Login previsto più avanti.

## Stack
Python 3.12, Streamlit, SQLite (`data/money.db`, fuori da git), pandas, Altair.

## Comandi
Da root del monorepo (il venv `.venv` sta lì):
```bash
.venv/Scripts/pip install -r code/money-tracker/requirements.txt
.venv/Scripts/python -m pytest code/money-tracker/tests/
.venv/Scripts/streamlit run code/money-tracker/src/app.py
```
Anteprima: configurazione `money-tracker` in `.claude/launch.json` (porta 8510).

## Convenzioni
- Accesso al DB solo da `src/db.py`; calcoli solo in `src/stats.py` (funzioni pure, testate in `tests/test_stats.py`); `src/app.py` solo interfaccia.
- Ogni query filtra per `user_id`: oggi è sempre `"me"` (`USER` in `app.py`), col login diventa l'utente autenticato. Per il deploy servirà un DB esterno (SQLite su Streamlit Cloud si azzera a ogni riavvio).
- Il confronto col periodo precedente è a pari giorni trascorsi (`stats.previous_window`), non sul periodo intero.
- Categorie e metodi di pagamento sono costanti in cima a `src/db.py`.
- UI: colori solo dai token in `src/ui/theme.py` (copia di quelli di macro-cycle-tracker) e `.streamlit/config.toml`; grafici passano da `theme.chart`.
- Dati finanziari reali mai su GitHub: `data/` è in `.gitignore`.
