# money-tracker

Dashboard delle finanze personali: spese giornaliere, settimanali e mensili, entrate e tasso di risparmio, con grafici. Tab Mese, Settimana e Giorno con i movimenti del periodo: bottone "Aggiungi movimento" (finestra `st.dialog`, anche metodo di pagamento) e spunta + bottone per eliminarli. Sezione "Investimenti" (scelta in alto): Portafoglio (operazioni di acquisto/vendita, prezzi attuali aggiornati a mano, costo medio ponderato come la banca: `stats.ledger`), Ribilanciatore (versamento diviso solo tra gli strumenti sotto il peso obiettivo: `stats.rebalance`), Zainetto fiscale (minusvalenze per 4 anni, i guadagni degli ETF non le usano, titoli di Stato al 48,08%: `stats.tax_bag`), Libertà finanziaria (FIRE: obiettivo = spese annue / 3,5%, Monte Carlo a rendimenti reali netti per profilo `stats.FIRE_PROFILES`; capitale dal portafoglio, risparmio e spese dai mesi chiusi), Interesse composto (semplice contro composto con versamenti, tassa e inflazione: `stats.interest_schedule`, arrivato da macro-cycle-tracker il 25/10/2026). Tabelle `instruments` (tipo, prezzo, peso obiettivo) e `operations`. Prossimo passo deciso dall'utente il 15/10/2026: login. Secondo software del brand Soft Investing (identità visiva: `../../concepts/brand-soft-investing.md`). Online su Streamlit Community Cloud, pubblica senza login (`private_app = true`, protezione = solo il link, scelta dell'utente) con dati su Neon Postgres; login Google opzionale (`[auth]`: una sola email, o chiunque con `allowed_email = "*"`, ognuno coi suoi dati); in locale senza secrets resta SQLite senza login.

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

Tutorial passo passo per l'utente: [DEPLOY.md](DEPLOY.md). In breve:
- Repo separato `renzi3182-hue/money-tracker` (remote `money-tracker` del monorepo), radice = questa cartella. Aggiornamento: `git subtree split --prefix=code/money-tracker -b money-tracker-deploy` e `git push money-tracker money-tracker-deploy:main`. Repo privato = app privata su Community Cloud; per l'app pubblica senza login (scelta dell'utente: solo lui ha il link) repo e app pubblici, passi in DEPLOY.md.
- Community Cloud: main file `src/app.py`, Python 3.12. Working directory = root del repo, `config.toml` deve stare in `.streamlit/` alla root: col repo separato è già così.
- Fase 1, senza login nell'app: Secrets con `private_app = true` e `[connections.sql] url` (connection string Neon con `postgresql+psycopg2://`: con `postgresql://` SQLAlchemy 2.1 cerca `psycopg` 3, non installato). Protezione = sharing privato di Community Cloud.
- Fase 2, login Google: aggiungere ai Secrets `allowed_email` e `[auth]`, poi su Neon `UPDATE movements SET user_id = '<email>' WHERE user_id = 'me'`. Client OAuth: Google Cloud Console → OAuth consent screen (External, utente di test = la propria email) → Credentials → OAuth client ID, Web application, redirect URI `https://<nome-app>.streamlit.app/oauth2callback` (in locale `http://localhost:8510/oauth2callback`).
   ```toml
   allowed_email = "tua@gmail.com"

   [connections.sql]
   url = "postgresql+psycopg2://USER:PASSWORD@HOST/neondb?sslmode=require"

   [auth]
   redirect_uri = "https://<nome-app>.streamlit.app/oauth2callback"
   cookie_secret = "stringa casuale lunga"  # python -c "import secrets; print(secrets.token_hex(32))"
   client_id = "....apps.googleusercontent.com"
   client_secret = "..."
   server_metadata_url = "https://accounts.google.com/.well-known/openid-configuration"
   ```
