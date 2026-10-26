# money-tracker

Dashboard delle finanze personali: spese giornaliere, settimanali e mensili, entrate e tasso di risparmio, con grafici. Tab Mese, Settimana e Giorno con i movimenti del periodo: bottone "Aggiungi movimento" (finestra `st.dialog`, anche metodo di pagamento) e spunta + bottone per eliminarli. Sezione "Investimenti" (scelta in alto): Portafoglio (operazioni di acquisto/vendita, prezzi attuali aggiornati a mano, costo medio ponderato come la banca: `stats.ledger`), Ribilanciatore (versamento diviso solo tra gli strumenti sotto il peso obiettivo: `stats.rebalance`), Zainetto fiscale (minusvalenze per 4 anni, i guadagni degli ETF non le usano, titoli di Stato al 48,08%: `stats.tax_bag`), Libertà finanziaria (FIRE: obiettivo = spese annue / 3,5%, Monte Carlo a rendimenti reali netti per profilo `stats.FIRE_PROFILES`; capitale dal portafoglio, risparmio e spese dai mesi chiusi), Interesse composto (semplice contro composto con versamenti, tassa e inflazione: `stats.interest_schedule`, arrivato da macro-cycle-tracker il 25/10/2026). Tabelle `instruments` (tipo, prezzo, peso obiettivo) e `operations`. Prossimo passo deciso dall'utente il 15/10/2026: login. Secondo software del brand Soft Investing (identità visiva: `../../concepts/brand-soft-investing.md`). Online su Streamlit Community Cloud, pubblica senza login (`private_app = true`, protezione = solo il link, scelta dell'utente) con dati su Neon Postgres; login Google opzionale (`[auth]`: una sola email, o chiunque con `allowed_email = "*"`, ognuno coi suoi dati); in locale senza secrets resta SQLite senza login.

In migrazione da Streamlit a Vercel (deciso dall'utente il 26/10/2026: Streamlit Community Cloud addormenta l'app e va riattivata a ogni apertura). Versione web: `public/index.html` (HTML/JS, Chart.js) + `api/index.py` (Starlette, Vercel Function), stessi `db.py` e `stats.py`, stesso Neon. L'app Streamlit resta finché l'utente non ha verificato quella su Vercel.

## Stack
Python 3.12, SQLAlchemy, Postgres su Neon online / SQLite in locale (`data/money.db`, fuori da git), pandas.
- Web (Vercel): Starlette in `api/index.py`, pagina statica `public/index.html` con Chart.js da CDN (con SRI). Dipendenze in `requirements.txt` alla radice.
- Streamlit: `src/app.py`, Altair, `st.login`. Dipendenze in `src/requirements.txt` (Community Cloud lo cerca prima della radice).

## Comandi
Da root del monorepo (il venv `.venv` sta lì):
```bash
.venv/bin/pip install -r code/money-tracker/requirements.txt -r code/money-tracker/src/requirements.txt
.venv/bin/python -m pytest code/money-tracker/tests/
.venv/bin/uvicorn api.index:app --app-dir code/money-tracker --port 8520   # web, SQLite locale senza login
.venv/bin/streamlit run code/money-tracker/src/app.py
```
Anteprima: configurazioni `money-tracker-web` (porta 8520, dati locali veri), `money-tracker-web-test` (porta 8521, copia del DB nello scratchpad con login, password `prova`) e `money-tracker` (Streamlit, porta 8510) in `.claude/launch.json`. Per provare aggiunte ed eliminazioni usare `-test`, mai il DB locale vero.

## Convenzioni
- Accesso al DB solo da `src/db.py`; calcoli solo in `src/stats.py` (funzioni pure, testate in `tests/test_stats.py`); `src/app.py` e `public/index.html` solo interfaccia; `api/index.py` solo validazione, login e JSON (testata in `tests/test_api.py`).
- Ogni query filtra per `user_id`: `USER` in `app.py` (`"me"` o l'email Google), variabile `USER_ID` su Vercel (default `"me"`).
- Database scelto da `DATABASE_URL` (su Streamlit la imposta `app.py` dai secrets `[connections.sql] url`); assente = SQLite locale. `db.py` non importa Streamlit. Tabelle create da `db._create` al primo accesso. I test usano il parametro `url` con un SQLite temporaneo.
- Login fail-closed: con il DB online ma senza `[auth]` (Streamlit) o senza `APP_PASSWORD`/`SESSION_SECRET` (Vercel) nessuno entra.
- Login Vercel: password unica, cookie `mt_session` = scadenza + HMAC con chiave da `SESSION_SECRET` e `APP_PASSWORD` (cambiare password chiude le sessioni). Nessun limite ai tentativi oltre 1 s di attesa: password lunga obbligatoria.
- Il confronto col periodo precedente è a pari giorni trascorsi (`stats.previous_window`), non sul periodo intero.
- Categorie e metodi di pagamento sono costanti in cima a `src/db.py`.
- UI: colori solo dai token in `src/ui/theme.py` (copia di quelli di macro-cycle-tracker) e `.streamlit/config.toml`; grafici passano da `theme.chart`. Nella versione web gli stessi token sono variabili CSS in cima a `public/index.html`, i grafici passano da `chart()`.
- Dati finanziari reali mai su GitHub: `data/` è in `.gitignore`.

## Messa online su Vercel
Tutorial per l'utente: [DEPLOY-VERCEL.md](DEPLOY-VERCEL.md). Progetto Vercel dal repo `renzi3182-hue/money-tracker` (stesso subtree push di sotto), Framework Other, config in `vercel.json` (output `public/`, rewrite `/api/*` → `api/index.py`). Variabili: `DATABASE_URL`, `APP_PASSWORD`, `SESSION_SECRET`, `USER_ID`, inserite dall'utente. `.vercelignore` esclude `data/` per i deploy da CLI.

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
