# Hosting the field system on one server

Everything runs on one small Linux server: the app (guards' phones, officials' pages, eNetra's `/api/v1`), the
evening 2-day list at 17:15 IST, the big-fire watch list, and HTTPS. It was rehearsed from a fresh clone of this
repository with only the shipped files visible (server up, `POST /api/v1/daily_scores` and `big_watch_scores` accepted,
lists read back). Not rehearsed here: the Docker build itself, HTTPS, the NASA token path (there is no Docker or token in the
cloud session).

## What you need (your accounts)
1. **A server.** Ubuntu 22.04/24.04, 2-4 vCPU, 16 GB RAM, 40 GB disk, in **Mumbai** (the evening run peaked at 6.2 GB and took 7 min here, so 8 GB is the floor and 16 GB leaves room for the app and the HLS read; FSI's portal and Bhuvan are Indian
   government sites and may refuse foreign addresses). Any provider; AWS Lightsail Mumbai is the simplest.
2. **A read-only deploy key** for this repository (the installer prints it; you paste it at Settings > Deploy keys, write unticked).
3. **A NASA Earthdata token** (urs.earthdata.nasa.gov > Generate Token), typed into `deploy/.env` on the server by hand.
   The cloud session had it injected by a proxy; a server does not. Without it HLS and MODIS go stale after about 20 days and
   the evening list says so.

## Steps
```
curl -fsSL https://raw.githubusercontent.com/Slllyio/van-suraksha-alert/main/field-system/deploy/install.sh -o install.sh   # private repo: copy the file over with scp instead
sudo bash install.sh        # 1st run: installs Docker, prints the deploy key. Add it at GitHub, run again.
sudo bash install.sh        # 2nd run: clones, seeds the state, writes deploy/.env (site name + a new service key)
nano /srv/fire/field-system/deploy/.env     # add EARTHDATA_TOKEN (and the webhook later)
sudo bash install.sh        # 3rd run: docker compose up
```
The site name defaults to `<ip-with-dashes>.sslip.io`, which gets a real HTTPS certificate with no domain purchase
(phones need HTTPS for GPS and camera). Use your own domain by editing `SITE` in `.env`.
`FS_SERVICE_KEYS` in `.env` is the key eNetra sends as `X-Api-Key`; read it on the server, never paste it in chat.

## Daily running
- `docker compose logs -f runner` shows the evening run; `scripts/cloud_daily.sh` retries until 19:15 IST.
- `GET /api/v1/health` (with the key) says whether fire feeds are fresh and whether tonight's lists arrived (checks from 19:45 IST).
- Update the code: `git -C /srv/fire pull && docker compose restart`. State (`field-system/var`, `pc_models/cloud_series`, `var/lf`) is outside git.
- Containers restart themselves (`restart: unless-stopped`); the app refuses to start on a failed migration, which then shows in the logs.

## Left for later
- The weekly scar check (`FS_SCAR_LIVE`) is off on the server: it needs the burn-scar pipeline's inputs (877 MB) moved too.
- Before the 2027 season: `make_static_season.py` (needs the 2026 AlphaEarth map), `scar_hist_2027.npz` for the big-fire list, the calibration refit.
