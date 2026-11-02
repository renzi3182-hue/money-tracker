# Money Tracker su Vercel

La versione web: pagina statica (`public/index.html`) servita dalla CDN di Vercel, API Python (`api/index.py`) come Vercel Function, dati sullo stesso database Neon dell'app Streamlit. Si apre subito, senza la schermata "app addormentata". Il login è ad account: ognuno si registra con email e password e vede solo i suoi dati.

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
| `OWNER_EMAIL` | La tua email: registrandoti con questa ritrovi i dati già su Neon. |
| `APP_PASSWORD` | La password con cui registri il tuo account la prima volta (solo per `OWNER_EMAIL`). Dopo puoi toglierla. |
| `SESSION_SECRET` | Una stringa casuale: `python3 -c "import secrets; print(secrets.token_hex(32))"` |
| `USER_ID` | `me`. Se su Streamlit avevi attivato il login Google, usa la tua email: è lo `user_id` dei dati su Neon. |

4. Premi **Deploy**. Dopo un minuto circa Vercel mostra l'indirizzo, tipo `money-tracker-xxx.vercel.app`.

Senza `SESSION_SECRET` (almeno 32 caratteri) l'app non fa entrare nessuno: lo fa apposta, così i dati non restano mai aperti.

## 3. Controllo

1. Apri l'indirizzo, scegli **Registrati** e crea il tuo account con `OWNER_EMAIL` e `APP_PASSWORD`.
2. Controlla che movimenti e investimenti siano gli stessi dell'app Streamlit.
3. Sul telefono: Safari → Condividi → **Aggiungi alla schermata Home**. Si apre come un'app.

Se la pagina dice "Errore del server", apri su Vercel **Deployments → l'ultimo → Logs** per vedere l'errore.

## 4. Spegnere Streamlit

Quando sei sicuro: su share.streamlit.io elimina l'app money-tracker. I dati restano su Neon.

## Passare al login con account (amici)

Da novembre 2026 ognuno ha il suo account. I tuoi dati restano tuoi: li ritrovi registrandoti con la tua email e la password unica di prima.

1. Su Vercel, **Settings → Environment Variables**:
   - aggiungi `OWNER_EMAIL` = la tua email;
   - controlla che `SESSION_SECRET` sia lunga almeno 32 caratteri (quella fatta col comando sopra lo è);
   - lascia `APP_PASSWORD` e `USER_ID` come sono.
2. Fai il push del codice (sezione 1). Vercel rifà il deploy.
3. Apri l'app, scegli **Registrati**, scrivi la tua email e come password la tua `APP_PASSWORD`. Entri e vedi i tuoi dati. Fallo prima di mandare il link agli amici.
4. Da qui la tua password è quella. Puoi togliere `APP_PASSWORD` da Vercel.
5. Manda il link agli amici: scelgono **Registrati**, email e una password di almeno 8 caratteri. Partono da zero e vedono solo i loro dati.

"Ricordami" (spuntato di default) tiene dentro per 90 giorni su quel dispositivo. Senza la spunta si esce chiudendo il browser.

Nota: chiunque abbia il link può creare un account. Le password non si possono recuperare: se un amico la dimentica, va cancellata la sua riga dalla tabella `users` su Neon e si registra di nuovo (i suoi dati restano, legati all'email).

## Aggiornare

Ogni push su `main` del repo `money-tracker` rifà il deploy da solo. Cambiare `SESSION_SECRET` su Vercel (poi Redeploy) chiude tutte le sessioni aperte.

## In locale

Dal monorepo, senza variabili d'ambiente (SQLite locale in `data/money.db`, nessun login):

```bash
.venv/bin/uvicorn api.index:app --app-dir code/money-tracker --port 8520
```

Poi apri http://localhost:8520. In Claude è la configurazione `money-tracker-web` di `.claude/launch.json`.
