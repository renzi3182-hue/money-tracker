# Money Tracker su Vercel

La versione web: pagina statica (`public/index.html`) servita dalla CDN di Vercel, API Python (`api/index.py`) come Vercel Function, dati sullo stesso database Neon dell'app Streamlit. Si apre subito, senza la schermata "app addormentata". Il login è una password unica.

L'app Streamlit resta accesa finché non hai controllato che questa funzioni. Leggono e scrivono gli stessi dati.

## 1. Codice su GitHub

Vercel prende il codice dal repo `renzi3182-hue/money-tracker`, lo stesso dell'app Streamlit. Dal monorepo, dopo il commit:

```bash
git subtree split --prefix=code/money-tracker -b money-tracker-deploy
git push money-tracker money-tracker-deploy:main
```

L'app Streamlit continua a funzionare: ora le sue dipendenze stanno in `src/requirements.txt`, e Community Cloud cerca quel file prima di quello alla radice.

## 2. Progetto su Vercel

1. Su vercel.com: **Add New → Project** e importa `renzi3182-hue/money-tracker`.
2. Framework Preset: **Other**. Root Directory: lasciala vuota (la radice del repo). Non toccare build e output: li imposta `vercel.json`.
3. Prima di premere Deploy apri **Environment Variables** e aggiungi:

| Nome | Valore |
| --- | --- |
| `DATABASE_URL` | La connection string di Neon, la stessa dei Secrets di Streamlit (`[connections.sql] url`). |
| `APP_PASSWORD` | Una password lunga, almeno 16 caratteri. Salvala nel tuo password manager. |
| `SESSION_SECRET` | Una stringa casuale: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `USER_ID` | `me`. Se su Streamlit avevi attivato il login Google, usa la tua email: è lo `user_id` dei dati su Neon. |

4. Premi **Deploy**. Dopo un minuto circa Vercel mostra l'indirizzo, tipo `money-tracker-xxx.vercel.app`.

Senza `APP_PASSWORD` o `SESSION_SECRET` l'app non fa entrare nessuno: lo fa apposta, così i dati non restano mai aperti.

## 3. Controllo

1. Apri l'indirizzo ed entra con la password.
2. Controlla che movimenti e investimenti siano gli stessi dell'app Streamlit.
3. Sul telefono: Safari → Condividi → **Aggiungi alla schermata Home**. Si apre come un'app.

Se la pagina dice "Errore del server", apri su Vercel **Deployments → l'ultimo → Logs** per vedere l'errore.

## 4. Spegnere Streamlit

Quando sei sicuro: su share.streamlit.io elimina l'app money-tracker. I dati restano su Neon.

## Aggiornare

Ogni push su `main` del repo `money-tracker` rifà il deploy da solo. Cambiare `APP_PASSWORD` su Vercel (poi Redeploy) chiude tutte le sessioni aperte.

## In locale

Dal monorepo, senza variabili d'ambiente (SQLite locale in `data/money.db`, nessun login):

```bash
.venv/bin/uvicorn api.index:app --app-dir code/money-tracker --port 8520
```

Poi apri http://localhost:8520. In Claude è la configurazione `money-tracker-web` di `.claude/launch.json`.
