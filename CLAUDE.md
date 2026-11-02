# money-tracker

Dashboard delle finanze personali: spese giornaliere, settimanali e mensili, entrate e tasso di risparmio, con grafici. Tab Mese, Settimana e Giorno con i movimenti del periodo: bottone "Aggiungi movimento" (finestra `st.dialog`, anche metodo di pagamento) e spunta + bottone per eliminarli. Sezione "Investimenti" (scelta in alto): Portafoglio (operazioni di acquisto/vendita, prezzi attuali aggiornati a mano, costo medio ponderato come la banca: `stats.ledger`), Ribilanciatore (versamento diviso solo tra gli strumenti sotto il peso obiettivo: `stats.rebalance`), Zainetto fiscale (minusvalenze per 4 anni, i guadagni degli ETF non le usano, titoli di Stato al 48,08%: `stats.tax_bag`), Libertà finanziaria (FIRE: obiettivo = spese annue / 3,5%, Monte Carlo a rendimenti reali netti per profilo `stats.FIRE_PROFILES`; capitale dal portafoglio, risparmio e spese dai mesi chiusi), Interesse composto (semplice contro composto con versamenti, tassa e inflazione: `stats.interest_schedule`, arrivato da macro-cycle-tracker il 25/10/2026). Tabelle `instruments` (tipo, prezzo, peso obiettivo) e `operations`. Card "Il tuo saldo" in cima (solo web): Liquidità e Investimenti separati, totale sotto. Liquidità = saldo totale (contanti e conto insieme, mai separati: scelta dell'utente del 02/11/2026) inserito a mano a una data (tabella `accounts`, `PUT /api/start`) + entrate − spese − acquisti + vendite dal giorno dopo (`stats.cash`); Investimenti = valore ai prezzi attuali dal `ledger`. Grafici dei periodi con legenda in HTML sopra (`legend()`), categoria come classifica a barre (`rank()`). Nella versione web niente metodo di pagamento (stessa scelta del 02/11/2026): la colonna `method` resta nel DB e i nuovi movimenti la salvano vuota, andamento giornaliero sugli ultimi 14 giorni. Media in `public/` generati con fal.ai e approvati dall'utente il 02/11/2026: `onde-saldo.mp4` (Nano Banana Pro + Kling 2.5 Turbo Std, 5 s montati avanti e indietro) dietro la card saldo, `glass-icon.mp4` copiato dal sito nell'header, `vuoto.webp` e `caricamento.webp` per gli stati vuoti. Video solo sul tema scuro, fermi con movimento ridotto. Login ad account sulla versione web (02/11/2026): ognuno si registra con email e password e vede solo i suoi dati, così l'utente può farla usare agli amici. Secondo software del brand Soft Investing (identità visiva: `../../brand/brand-soft-investing.md`). Online su Streamlit Community Cloud, pubblica senza login (`private_app = true`, protezione = solo il link, scelta dell'utente) con dati su Neon Postgres; login Google opzionale (`[auth]`: una sola email, o chiunque con `allowed_email = "*"`, ognuno coi suoi dati); in locale senza secrets resta SQLite senza login.

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
Anteprima: configurazioni `money-tracker-web` (porta 8520, dati locali veri), `money-tracker-web-test` (porta 8521, copia del DB nello scratchpad con login; il proprietario `OWNER_EMAIL=io@prova.test` si registra con la password `prova-locale-solo-test`, gli altri con email e password inventate) e `money-tracker` (Streamlit, porta 8510) in `.claude/launch.json`. Per provare aggiunte ed eliminazioni usare `-test`, mai il DB locale vero.

## Convenzioni
- Accesso al DB solo da `src/db.py`; calcoli solo in `src/stats.py` (funzioni pure, testate in `tests/test_stats.py`); `src/app.py` e `public/index.html` solo interfaccia; `api/index.py` solo validazione, login e JSON (testata in `tests/test_api.py`).
- Ogni query filtra per `user_id`: `USER` in `app.py` (`"me"` o l'email Google); su Vercel il `data_id` dell'account (tabella `users`): l'email, o `USER_ID` (default `"me"`) per il proprietario. Gli handler di `api/index.py` lo ricevono come secondo argomento da `@api`.
- Database scelto da `DATABASE_URL` (su Streamlit la imposta `app.py` dai secrets `[connections.sql] url`); assente = SQLite locale. `db.py` non importa Streamlit. Tabelle create da `db._create` al primo accesso. I test usano il parametro `url` con un SQLite temporaneo.
- Login fail-closed: con il DB online ma senza `[auth]` (Streamlit) o senza `SESSION_SECRET` di almeno 32 caratteri (Vercel) nessuno entra.
- Login Vercel ad account: `POST /api/register` e `/api/login` con email, password e `remember`. Password almeno 8 caratteri, hash PBKDF2 (`HASH_ROUNDS`) in `users`. Registrazione aperta a chiunque abbia il link. Cookie `mt_session` = id + scadenza + HMAC con `SESSION_SECRET` sull'hash della password (cambiarla, o cambiare il segreto, chiude le sessioni). "Ricordami" = cookie di 90 giorni, senza = cookie di sessione scaduto comunque dopo 12 ore. 5 password sbagliate di fila chiudono l'account 15 minuti.
- Proprietario: l'email in `OWNER_EMAIL` si registra solo con la vecchia `APP_PASSWORD` e ottiene `data_id = USER_ID`, cioè i dati già su Neon. Dopo la registrazione `APP_PASSWORD` non serve più.
- Il confronto col periodo precedente è a pari giorni trascorsi (`stats.previous_window`), non sul periodo intero.
- Categorie e metodi di pagamento sono costanti in cima a `src/db.py`.
- UI: colori solo dai token in `src/ui/theme.py` (copia di quelli di macro-cycle-tracker) e `.streamlit/config.toml`; grafici passano da `theme.chart`. Nella versione web gli stessi token sono variabili CSS in cima a `public/index.html`, i grafici passano da `chart()`.
- Dati finanziari reali mai su GitHub: `data/` è in `.gitignore`.

## Messa online su Vercel
Tutorial per l'utente: [DEPLOY-VERCEL.md](DEPLOY-VERCEL.md). Progetto Vercel dal repo `renzi3182-hue/money-tracker` (stesso subtree push di sotto), Framework Other, config in `vercel.json` (output `public/`, rewrite `/api/*` → `api/index.py`). Variabili: `DATABASE_URL`, `SESSION_SECRET`, `OWNER_EMAIL`, `APP_PASSWORD` (solo per la registrazione del proprietario), `USER_ID`, inserite dall'utente. `.vercelignore` esclude `data/` per i deploy da CLI.

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
