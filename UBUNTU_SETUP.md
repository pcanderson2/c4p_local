# Ubuntu Setup & Test Guide

Tested on Ubuntu 22.04 LTS and 24.04 LTS on bare metal with a dedicated SSD.

---

## Part 1 — Install Ubuntu

1. Download Ubuntu 22.04 or 24.04 LTS from ubuntu.com
2. Flash to a USB drive with Balena Etcher (free, Windows/Mac/Linux)
3. Boot from the USB, select "Install Ubuntu" on the dedicated SSD
4. Choose **Minimal installation** — you don't need office apps
5. Enable "Install third-party software" (needed for NVIDIA drivers later)
6. Complete install and reboot into Ubuntu

---

## Part 2 — First boot essentials

Open a terminal (Ctrl+Alt+T) and run:

```bash
sudo apt update && sudo apt upgrade -y
sudo apt install -y curl git nano dos2unix net-tools
```

---

## Part 3 — Install Docker Engine

```bash
curl -fsSL https://get.docker.com | sh
sudo usermod -aG docker $USER
newgrp docker
```

Verify Docker is working:

```bash
docker run hello-world
```

You should see "Hello from Docker!" — if so, Docker is ready.

---

## Part 4 — NVIDIA GPU setup (skip if no GPU)

### Check if Ubuntu detected your GPU:

```bash
lspci | grep -i nvidia
```

If your card appears, install drivers:

**Ubuntu 22.04:**
```bash
sudo apt install -y nvidia-driver-535
sudo reboot
```

**Ubuntu 24.04:**
```bash
sudo apt install -y nvidia-driver-550
sudo reboot
```

After reboot, confirm the GPU is working:

```bash
nvidia-smi
```

You should see your GPU model and driver version listed.

### Install NVIDIA Container Toolkit (lets Docker use the GPU):

```bash
curl -fsSL https://nvidia.github.io/libnvidia-container/gpgkey \
  | sudo gpg --dearmor -o /usr/share/keyrings/nvidia-container-toolkit-keyring.gpg

curl -s -L https://nvidia.github.io/libnvidia-container/stable/deb/nvidia-container-toolkit.list \
  | sudo tee /etc/apt/sources.list.d/nvidia-container-toolkit.list

sudo apt update && sudo apt install -y nvidia-container-toolkit
sudo nvidia-ctk runtime configure --runtime=docker
sudo systemctl restart docker
```

Verify Docker can see the GPU:

```bash
docker run --rm --gpus all nvidia/cuda:12.0-base-ubuntu22.04 nvidia-smi
```

---

## Part 5 — Copy project files to Ubuntu

### Option A — USB drive

Plug in the USB drive containing the project folder, then:

```bash
cp -r /media/$USER/*/Fully\ Local ~/c4p-social
```

### Option B — Transfer over your local network from Windows

On Windows, find your IP address:
```powershell
ipconfig
# look for IPv4 Address under your active adapter
```

On Ubuntu:
```bash
sudo apt install -y openssh-server
scp -r "pcaby@WINDOWS-IP:C:/Users/pcaby/Documents/Computers 4 People AI Social Media/Fully Local" ~/c4p-social
```

### Fix Windows line endings:

```bash
find ~/c4p-social -name "*.py" -o -name "*.sh" | xargs dos2unix
```

---

## Part 6 — Configure environment

```bash
cd ~/c4p-social
cp .env.example .env
nano .env
```

For free local testing, set these values:

```
POSTGRES_PASSWORD=changeme_strong_password
POSTIZ_SECRET=anyRandom32CharStringGoesHere12

# Use small free model for testing
LLM_MODEL=phi3:mini

# Local email — no real SMTP needed
SMTP_HOST=mailpit
SMTP_PORT=1025
SMTP_USER=test
SMTP_PASSWORD=test
DIGEST_FROM=digest@c4p.local
DIGEST_TO=team@c4p.local

# Leave Instagram empty for now — test with seeded data first
INSTAGRAM_TARGETS=
GALLERY_DL_TARGETS=
```

Save and exit: Ctrl+X → Y → Enter

### If you have no NVIDIA GPU — remove the GPU block from docker-compose.yml:

```bash
nano ~/c4p-social/docker-compose.yml
```

Find and delete these lines under the `ollama` service:

```yaml
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

Save and exit.

### Add Mailpit for local email testing:

```bash
nano ~/c4p-social/docker-compose.yml
```

Add this under `services:` (same indentation level as `postgres:`):

```yaml
  mailpit:
    image: axllent/mailpit
    restart: unless-stopped
    networks: [c4p_net]
    ports:
      - "8025:8025"
      - "1025:1025"
```

Save and exit.

---

## Part 7 — Build and start infrastructure

```bash
cd ~/c4p-social

# Build images and start core services
docker compose up -d --build postgres ollama mailpit

# Watch the logs — ready when postgres shows "database system is ready"
docker compose logs -f postgres
```

Press Ctrl+C to stop watching logs.

---

## Part 8 — Pull the AI model

```bash
docker compose up ollama-init
```

This pulls `phi3:mini` (~2.3 GB). Watch the progress bar. When it shows "Model ready" and exits, continue.

Verify the model loaded:

```bash
curl http://localhost:11434/api/tags
```

You should see `phi3:mini` in the JSON response.

---

## Part 9 — Verify the database

```bash
docker compose exec postgres psql -U c4p -d c4p_social -c "\dt"
```

Expected output — four tables:

```
 Schema |     Name      | Type  | Owner
--------+---------------+-------+-------
 public | content_queue | table | c4p
 public | digest_log    | table | c4p
 public | post_analysis | table | c4p
 public | scraped_posts | table | c4p
```

---

## Part 10 — Test the analyzer (no scraper needed)

Seed a fake post directly into the database:

```bash
docker compose exec postgres psql -U c4p -d c4p_social -c "
INSERT INTO scraped_posts (platform, source_account, post_url, caption, hashtags)
VALUES (
  'test', 'seed',
  'https://example.com/post-1',
  'Rural students are losing ground. Lack of broadband is a barrier to equal opportunity in education.',
  ARRAY['digitalequity','broadband','education']
);"
```

Start the analyzer and watch it process the post:

```bash
docker compose up -d analyzer
docker compose logs -f analyzer
```

Wait for a line like `Saved analysis post_id=1 score=8.5` then press Ctrl+C.

Confirm the result in the database:

```bash
docker compose exec postgres psql -U c4p -d c4p_social -c "
SELECT
  pa.trend_score,
  pa.audit_status,
  pa.ai_flagged,
  pa.visual_hooks,
  pa.suggested_content
FROM post_analysis pa LIMIT 1;"
```

Check that:
- `ai_flagged` = `t` (always true)
- `audit_status` = `pending`
- `trend_score` has a value
- `suggested_content` has text

---

## Part 11 — Test the email digest

Start the digest service:

```bash
docker compose up -d digest
```

Trigger it immediately without waiting for the cron schedule:

```bash
docker compose exec digest python -c "from digest import run_digest; run_digest()"
```

Open the local email inbox in your browser:

```
http://localhost:8025
```

You should see a "C4P Trend Digest" email with the trend card from the seeded post.

---

## Part 12 — Start the full stack

```bash
docker compose up -d
```

Check all services are running:

```bash
docker compose ps
```

Every service should show `running` or `healthy`. If any shows `restarting`, check its logs:

```bash
docker compose logs <service-name>
```

Open the Postiz scheduling dashboard:

```
http://localhost:5000
```

Create an account on first visit to access the dashboard.

---

## Part 13 — Approve AI-generated content

All AI output requires human approval before it can be scheduled. Run this to review pending items:

```bash
docker compose exec postgres psql -U c4p -d c4p_social -c "
SELECT pa.id, sp.source_account, pa.trend_score, pa.audit_status,
       left(pa.suggested_content, 80) AS content_preview
FROM post_analysis pa
JOIN scraped_posts sp ON sp.id = pa.post_id
WHERE pa.audit_status = 'pending'
ORDER BY pa.trend_score DESC;"
```

Approve or reject each item by ID:

```bash
# Approve:
docker compose exec postgres psql -U c4p -d c4p_social -c "
UPDATE post_analysis
SET audit_status = 'approved', audit_note = 'Reviewed by [your name]'
WHERE id = 1;"

# Reject:
docker compose exec postgres psql -U c4p -d c4p_social -c "
UPDATE post_analysis
SET audit_status = 'rejected', audit_note = 'Off-brand'
WHERE id = 1;"
```

---

## Part 14 — Switch to real targets (after testing passes)

Edit `.env`:

```bash
nano ~/c4p-social/.env
```

Update these values:

```
# Real Instagram accounts (public only)
INSTAGRAM_TARGETS=natgeo,nasa

# Real YouTube channel
GALLERY_DL_TARGETS=https://www.youtube.com/@veritasium

# Upgrade to DeepSeek R1 if you have 16+ GB RAM or a GPU
LLM_MODEL=deepseek-r1:14b

# Real SMTP for email digest
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your@gmail.com
SMTP_PASSWORD=your_gmail_app_password
DIGEST_FROM=your@gmail.com
DIGEST_TO=team@computers4people.org
```

Restart affected services:

```bash
docker compose up -d --force-recreate scraper analyzer digest
```

---

## Part 15 — Run unit tests with Sonar coverage

### Install test dependencies:

```bash
cd ~/c4p-social
pip install -r tests/requirements-test.txt
```

### Run all tests and generate Sonar reports:

```bash
pytest
```

This produces:
- `coverage.xml` — line coverage report consumed by SonarQube
- `test-results.xml` — JUnit XML report consumed by SonarQube

### Run a specific test file:

```bash
pytest tests/test_analyzer.py -v
pytest tests/test_scraper.py -v
pytest tests/test_digest.py -v
```

### Upload to SonarCloud (free for public/private repos):

1. Sign in at sonarcloud.io with your GitHub account
2. Import `pcanderson2/c4p_local`
3. Get your project token from SonarCloud → Project Settings → Analysis Method
4. Run the scanner:

```bash
docker run --rm \
  -e SONAR_TOKEN=your_sonarcloud_token \
  -v "$(pwd):/usr/src" \
  sonarsource/sonar-scanner-cli
```

SonarCloud will read `sonar-project.properties` and upload `coverage.xml` and `test-results.xml` automatically.

### Run locally with SonarQube (fully self-hosted):

```bash
docker run -d --name sonarqube -p 9000:9000 sonarqube:community
# wait ~60 seconds for startup, then open http://localhost:9000
# default login: admin / admin (change on first login)

# then scan the project:
docker run --rm \
  -e SONAR_TOKEN=your_local_token \
  -e SONAR_HOST_URL=http://host-gateway:9000 \
  --add-host=host-gateway:host-gateway \
  -v "$(pwd):/usr/src" \
  sonarsource/sonar-scanner-cli
```

---

## Useful commands

```bash
# View live logs for any service
docker compose logs -f <service>     # scraper | analyzer | digest | postgres | ollama

# Restart a single service
docker compose restart <service>

# Stop everything (keeps data)
docker compose down

# Stop and delete all data (destructive)
docker compose down -v

# Check disk usage
docker system df

# Free up unused images
docker system prune
```

---

## Minimum hardware requirements

| Component | Minimum | Recommended |
|---|---|---|
| RAM | 8 GB | 16 GB |
| Disk (SSD) | 40 GB free | 80 GB free |
| GPU | None (CPU works) | NVIDIA 8 GB VRAM |
| Model | phi3:mini (CPU) | deepseek-r1:14b (GPU) |
