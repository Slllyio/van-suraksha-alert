#!/usr/bin/env bash
# One-time setup of a fresh Ubuntu 22.04/24.04 server (2 vCPU, 8 GB RAM, 40 GB disk is enough; pick a Mumbai region:
# FSI's portal and Bhuvan are Indian government sites and may refuse foreign addresses).
#   curl -fsSL <raw url of this file> -o install.sh && sudo bash install.sh
# It asks for nothing: the secrets go into /srv/fire/field-system/deploy/.env, which you fill in by hand afterwards.
set -euo pipefail
REPO="${FIRE_REPO:-git@github.com:Slllyio/van-suraksha-alert.git}"
ROOT=/srv/fire
[ "$(id -u)" = 0 ] || { echo "run with sudo"; exit 1; }

# 1. Docker + git-lfs
if ! command -v docker >/dev/null; then curl -fsSL https://get.docker.com | sh; fi
apt-get install -y -qq git git-lfs >/dev/null
git lfs install --system >/dev/null

# 2. read-only deploy key for the private repo (add the printed public key at GitHub: repo Settings > Deploy keys, no write)
if [ ! -f /root/.ssh/fire_deploy ]; then
  mkdir -p /root/.ssh && ssh-keygen -q -t ed25519 -N "" -f /root/.ssh/fire_deploy -C "fire-server"
  printf 'Host github.com\n  IdentityFile /root/.ssh/fire_deploy\n  StrictHostKeyChecking accept-new\n' >> /root/.ssh/config
  echo; echo "=== Add this deploy key at https://github.com/Slllyio/van-suraksha-alert/settings/keys/new (leave 'write' unticked) ==="
  cat /root/.ssh/fire_deploy.pub; echo "=== then run this script again ==="; exit 0
fi

# 3. code + data
if [ ! -d "$ROOT/.git" ]; then git clone "$REPO" "$ROOT"; else git -C "$ROOT" pull --ff-only; fi
git -C "$ROOT" lfs pull
F="$ROOT/field-system"
# state that the server owns from now on (a later git pull never touches it): seeded once from the repo
mkdir -p "$F/var"
[ -d "$F/pc_models/cloud_series" ] || cp -r "$F/seed/cloud_series" "$F/pc_models/cloud_series"
[ -d "$F/var/lf/r22" ] || { mkdir -p "$F/var/lf"; cp -r "$F/seed/lf/r22" "$F/var/lf/r22"; }   # big-fire watch caches
mkdir -p "$ROOT/ratapani/mp_grid/dryness"

# 4. config
D="$F/deploy"
if [ ! -f "$D/.env" ]; then
  cp "$D/env.example" "$D/.env"
  ip=$(curl -fsS https://api.ipify.org || true)
  site="$(echo "$ip" | tr . -).sslip.io"
  sed -i "s|^SITE=.*|SITE=$site|" "$D/.env"
  key=$(openssl rand -hex 32)
  sed -i "s|^FS_SERVICE_KEYS=.*|FS_SERVICE_KEYS=$key|; s|^FS_SERVICE_KEY=.*|FS_SERVICE_KEY=$key|" "$D/.env"
  chmod 600 "$D/.env"
  echo; echo "Created $D/.env (site $site, a fresh service key). Edit it to add EARTHDATA_TOKEN (and the webhook, CDSE if used), then run: cd $D && docker compose up -d --build"
  exit 0
fi

# 5. start
cd "$D" && docker compose up -d --build
echo "Up. Open https://$(grep ^SITE= .env | cut -d= -f2) once the certificate is issued (a minute). Logs: docker compose logs -f"
