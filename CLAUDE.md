# money-tracker

Dashboard delle finanze personali: spese giornaliere, settimanali e mensili, entrate e tasso di risparmio, con grafici. Tab Mese, Settimana e Giorno con i movimenti del periodo: bottone "Aggiungi movimento" (finestra `st.dialog`, anche metodo di pagamento) e spunta + bottone per eliminarli. Secondo software del brand Soft Investing (identità visiva: `../../concepts/brand-soft-investing.md`). Online su Streamlit Community Cloud con login Google (solo un'email ammessa) e dati su Neon Postgres; in locale senza secrets resta SQLite senza login.

## Stack
Python 3.12, Streamlit (`st.connection("sql")`, `st.login`), SQLAlchemy, Postgres su Neon online / SQLite in locale (`data/money.db`, fuori da git), pandas, Altair.

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
- Ogni query filtra per `user_id` (`USER` in `app.py`): `"me"` in locale, l'email Google online.
- Database scelto dai secrets: `[connections.sql] url` presente = Postgres, assente = SQLite locale. Tabella creata da `db._create` al primo accesso. I test usano il parametro `url` con un SQLite temporaneo.
- Login fail-closed: con il DB online ma senza `[auth]` l'app si ferma invece di aprirsi a tutti.
- Il confronto col periodo precedente è a pari giorni trascorsi (`stats.previous_window`), non sul periodo intero.
- Categorie e metodi di pagamento sono costanti in cima a `src/db.py`.
- UI: colori solo dai token in `src/ui/theme.py` (copia di quelli di macro-cycle-tracker) e `.streamlit/config.toml`; grafici passano da `theme.chart`.
- Dati finanziari reali mai su GitHub: `data/` è in `.gitignore`.

## Messa online (Streamlit Community Cloud)
Credenziali e chiavi le inserisce l'utente, mai Claude. Deploy e push solo su sua conferma.

1. **Neon**: crea progetto gratuito su neon.tech, copia la connection string (Dashboard → Connect). Diventa `postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require` (aggiungere `+psycopg2` dopo `postgresql`).
2. **Client OAuth Google**: Google Cloud Console → APIs & Services → OAuth consent screen (External, utente di test = la propria email) → Credentials → Create OAuth client ID, tipo Web application. Authorized redirect URI: `https://<nome-app>.streamlit.app/oauth2callback` (per provare in locale anche `http://localhost:8510/oauth2callback`). Copia client ID e secret.
3. **Secrets**: in locale `code/money-tracker/.streamlit/secrets.toml` (gitignored, letto quando si lancia da `code/money-tracker` come fa `launch.json`); su Community Cloud incollare lo stesso testo in App settings → Secrets.
   ```toml
   allowed_email = "tua@gmail.com"

   [connections.sql]
   url = "postgresql+psycopg2://USER:PASSWORD@HOST/DBNAME?sslmode=require"

   [auth]
   redirect_uri = "https://<nome-app>.streamlit.app/oauth2callback"
   cookie_secret = "stringa casuale lunga"  # python -c "import secrets; print(secrets.token_hex(32))"
   client_id = "....apps.googleusercontent.com"
   client_secret = "..."
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```
4. **Community Cloud**: New app dal repo GitHub, branch `master`, main file `code/money-tracker/src/app.py`. Prima del deploy verificare che Cloud trovi `requirements.txt` e `.streamlit/config.toml`: li cerca nella cartella del main file (`src/`) e nella root del repo, non in `code/money-tracker/`.
5. I movimenti locali (`user_id = "me"`) non migrano da soli: online si parte vuoti.
