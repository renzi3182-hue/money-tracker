# Mettere online money-tracker

Streamlit Community Cloud (gratis) + database Neon Postgres (gratis). Per ora senza login nell'app: l'app è **privata** su Community Cloud, la vede solo chi è invitato (accesso con Google gestito da Streamlit). Il login con `st.login` arriva dopo.

Tempo: circa 20 minuti. Credenziali e password le inserisci solo tu.

## Perché un repo separato
Il monorepo `soft-investing` contiene note personali e altri progetti: Community Cloud non deve vederlo. Come per macro-cycle-tracker, l'app vive in un repo a sé, con `code/money-tracker` come radice. Così `requirements.txt` e `.streamlit/config.toml` stanno nella root del repo, dove Community Cloud li cerca.

A differenza di macro-cycle-tracker il repo è **privato**: un repo privato produce un'app privata. Community Cloud gratis concede una sola app privata alla volta; macro-cycle-tracker è pubblica, quindi il posto è libero.

## 1. Database su Neon
1. Vai su https://neon.tech e registrati (va bene "Continue with Google").
2. Crea un progetto: nome `money-tracker`, Postgres ultima versione. Regione: **AWS US East (N. Virginia)**, la più vicina ai server di Community Cloud (che sono negli USA): ogni pagina fa una query, così è più veloce. Se preferisci i dati in Europa scegli Frankfurt, l'app sarà un po' più lenta.
3. Nella dashboard del progetto premi **Connect**, lascia database `neondb` e ruolo predefinito, copia la connection string. Ha questa forma:
   `postgresql://neondb_owner:PASSWORD@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require`
4. Tienila da parte, non incollarla in chat né in file che finiscono su GitHub. La tabella la crea l'app da sola al primo avvio.

Nota: il piano gratuito "addormenta" il database dopo 5 minuti senza uso. Il primo caricamento dopo una pausa impiega un secondo in più, poi va normale.

## 2. Repo GitHub privato
Dalla root del monorepo (`soft-investing`), in Git Bash o PowerShell:

```bash
gh repo create renzi3182-hue/money-tracker --private
```

```bash
git remote add money-tracker https://github.com/renzi3182-hue/money-tracker.git
```

```bash
git subtree split --prefix=code/money-tracker -b money-tracker-deploy
```

```bash
git push money-tracker money-tracker-deploy:main
```

`subtree split` prende solo la cartella `code/money-tracker` (con la sua storia) e la mette in un branch dove è la radice. `data/` e `secrets.toml` sono in `.gitignore`: nessun dato reale finisce su GitHub.

**Aggiornare l'app in futuro** (dopo un commit su `master` del monorepo): rifai gli ultimi due comandi. Community Cloud fa redeploy da solo a ogni push su `main`.

## 3. App su Community Cloud
1. Vai su https://share.streamlit.io e accedi con GitHub (lo stesso account `renzi3182-hue` di macro-cycle-tracker).
2. Se è la prima app da un repo privato, Streamlit chiede di autorizzare l'accesso ai repo privati: accetta (Settings → Linked accounts → GitHub, se non compare da solo).
3. **Create app** → "Deploy a public app from GitHub" / "Yup, I have an app":
   - Repository: `renzi3182-hue/money-tracker`
   - Branch: `main`
   - Main file path: `src/app.py`
   - App URL: per esempio `softinvesting-money` → `https://softinvesting-money.streamlit.app`
4. **Advanced settings**:
   - Python version: **3.12**
   - Secrets: incolla questo, con la tua connection string di Neon al posto di quella finta:
     ```toml
     private_app = true

     [connections.sql]
     url = "postgresql://neondb_owner:PASSWORD@ep-xxxx.us-east-1.aws.neon.tech/neondb?sslmode=require&channel_binding=require"
     ```
5. **Deploy**. Il primo avvio installa le dipendenze, 2-3 minuti.

`private_app = true` dice all'app che può partire senza il proprio login perché la protezione la fa Streamlit. Senza quella riga, con il database online, l'app si ferma apposta.

## 4. Controlla che sia davvero privata
1. Nella pagina dell'app: **Share** (in alto a destra) o App settings → **Sharing**.
2. Deve dire "Only specific people can view this app". Se dice "This app is public", cambialo in privato **prima** di inserire dati.
3. Prova: apri l'URL in una finestra in incognito. Deve chiederti di accedere, non mostrarti la dashboard.
4. Per usarla dal telefono: accedi con lo stesso account. Per farla vedere a qualcun altro: Share → invita la sua email.

## 5. Primo uso
- L'app parte vuota: i movimenti locali (`data/money.db`) non vengono copiati online.
- Aggiungi un movimento, ricarica la pagina, poi da share.streamlit.io fai **Reboot app** (menu ⋮ → Reboot): il movimento deve esserci ancora. Se c'è, i dati stanno su Neon e non si perdono più.
- Sulla dashboard Neon, in **Tables**, vedi la tabella `movements` con le righe.

## Se qualcosa va storto
- **"Manca la sezione [auth] nei secrets"**: manca `private_app = true` nei Secrets (App settings → Secrets, poi salva: l'app si riavvia).
- **`OperationalError` / `password authentication failed`**: connection string copiata male. Rigenerala da Neon (Connect) e reincollala.
- **`ModuleNotFoundError`**: controlla che il repo abbia `requirements.txt` nella root (lo ha, se il push del passo 2 è andato).
- **Errori dopo un aggiornamento**: menu ⋮ → **Reboot app**. Community Cloud a volte tiene in memoria i moduli vecchi.
- **Log**: in basso a destra nell'app, "Manage app", mostra l'output del server.

## Dopo: login nell'app
Quando aggiungiamo `st.login` (sezione `[auth]` e `allowed_email` nei Secrets, passi in `CLAUDE.md`), l'utente dei dati cambia da `"me"` alla tua email. Per non perdere i movimenti già inseriti, nel SQL Editor di Neon:

```sql
UPDATE movements SET user_id = 'tua@gmail.com' WHERE user_id = 'me';
```
