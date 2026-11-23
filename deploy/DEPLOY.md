# Van Suraksha — Server Deployment Guide

## Oracle Cloud Free Tier Setup (10 minutes)

### Step 1: Create Oracle Cloud Account

1. Go to: https://signup.cloud.oracle.com/
2. Choose **Home Region: India South (Hyderabad)** or **India West (Mumbai)**
3. Complete signup (needs credit card for verification — you will NOT be charged)
4. Wait for account activation email (usually 2-5 minutes)

### Step 2: Create Free VM

1. Log in to Oracle Cloud Console: https://cloud.oracle.com/
2. Click **"Create a VM Instance"** (on dashboard)
3. Configure:
   - **Name**: `vansuraksha`
   - **Image**: Ubuntu 22.04 (default)
   - **Shape**: Click "Change Shape" → **Ampere** → **VM.Standard.A1.Flex**
     - OCPUs: **2** (free tier allows up to 4)
     - Memory: **12 GB** (free tier allows up to 24)
   - **Networking**: Keep defaults (creates VCN automatically)
   - **SSH Key**: Click "Generate key pair" → **Download both keys**
     - Save the private key as `vansuraksha-key.pem`
   - **Boot Volume**: 50 GB (free tier default)
4. Click **"Create"**
5. Wait 2-3 minutes for the VM to be provisioned
6. Note the **Public IP Address** shown on the instance page

### Step 3: Open Firewall Ports

1. On the instance page, click the **Subnet** link
2. Click the **Security List** (Default Security List)
3. Click **"Add Ingress Rules"**
4. Add these rules one by one:

| Source CIDR | Port | Description |
|-------------|------|-------------|
| 0.0.0.0/0 | 80 | Portal Dashboard |
| 0.0.0.0/0 | 8501 | Streamlit Dashboard |
| 0.0.0.0/0 | 8000 | API |

### Step 4: Connect to VM

```bash
# From your laptop (Windows PowerShell or Git Bash)
chmod 400 vansuraksha-key.pem
ssh -i vansuraksha-key.pem ubuntu@<YOUR_PUBLIC_IP>
```

### Step 5: Install Docker on VM

```bash
# Run these commands on the VM
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2 git
sudo systemctl enable docker
sudo usermod -aG docker ubuntu
# Log out and back in for group change
exit
```

Then SSH back in:
```bash
ssh -i vansuraksha-key.pem ubuntu@<YOUR_PUBLIC_IP>
```

### Step 6: Deploy Van Suraksha

```bash
# Clone the repo (or upload via scp)
git clone https://github.com/<your-username>/FIRE.git
cd FIRE

# Create .env file
cat > .env << 'EOF'
FIRMS_MAP_KEY=<your FIRMS map key>
GEE_PROJECT=van-suraksha-alert
EOF

# Build and start
docker compose -f deploy/docker-compose.server.yml up -d --build

# Check logs
docker logs vansuraksha -f
```

### Step 7: Verify

Open in browser:
- **Portal Dashboard**: `http://<YOUR_PUBLIC_IP>/`
- **Streamlit Dashboard**: `http://<YOUR_PUBLIC_IP>:8501`

### Step 8: Run First Alert

```bash
# SSH into the container and run manually
docker exec vansuraksha python scripts/daily_fire_alert.py
```

## Alternative: Upload Without Git

If the repo is not on GitHub, upload directly:

```bash
# From your laptop (in E:\FIRE directory)
# Create a tar of essential files
tar -czf vansuraksha.tar.gz \
  deploy/ src/ scripts/ dashboard/ models/ignition/ \
  data/aoi/ data_lake/fire_detections/ data_lake/fire_weather/ \
  data_lake/alerts/ data_lake/land_cover/ \
  config.yaml .env

# Upload to server
scp -i vansuraksha-key.pem vansuraksha.tar.gz ubuntu@<YOUR_PUBLIC_IP>:~/

# On the server
ssh -i vansuraksha-key.pem ubuntu@<YOUR_PUBLIC_IP>
mkdir -p FIRE && cd FIRE
tar -xzf ~/vansuraksha.tar.gz

# Build and start
docker compose -f deploy/docker-compose.server.yml up -d --build
```

## Daily Operations

The system automatically runs at **06:00 AM IST** every day. To check:

```bash
# View today's alert
docker exec vansuraksha cat data_lake/alerts/latest_alert.json

# View cron logs
docker exec vansuraksha tail -50 logs/cron.log

# Run manually
docker exec vansuraksha python scripts/daily_fire_alert.py

# Restart
docker compose -f deploy/docker-compose.server.yml restart

# Update code
cd FIRE && git pull
docker compose -f deploy/docker-compose.server.yml up -d --build
```

## Costs

| Resource | Cost |
|----------|------|
| VM (2 OCPU, 12 GB ARM) | **Free forever** |
| 50 GB boot volume | **Free forever** |
| 10 TB/month outbound | **Free forever** |
| Public IP | **Free forever** |
| **Total** | **Rs 0/month** |
