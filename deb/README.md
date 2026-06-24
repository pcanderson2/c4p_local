# C4P Local — .deb Installer

One-command install of the C4P Social Media Monitor on Ubuntu 22.04 or 24.04.

The installer automatically handles:
- Docker Engine
- NVIDIA drivers and container toolkit (if a GPU is detected)
- All Docker images
- Systemd service (auto-starts on boot)
- Ollama model pull (DeepSeek R1 14B)
- Pre-configured credentials — no manual `.env` editing required

---

## Requirements

- Ubuntu 22.04 LTS or 24.04 LTS (bare metal or VM)
- 16 GB RAM minimum (32 GB recommended)
- 40 GB free disk space minimum
- Internet connection (for Docker image pulls and model download)
- NVIDIA GPU optional — installer detects and configures automatically

---

## Step 1 — Install dependencies

Open a terminal and run:

```bash
sudo apt update && sudo apt install -y curl git
```

---

## Step 2 — Clone this repo

```bash
git clone https://github.com/pcanderson2/c4p-local-deb.git ~/c4p-local-deb
cd ~/c4p-local-deb
```

---

## Step 3 — Build the .deb file

```bash
bash build-deb.sh
```

This produces `c4p-social_1.0_amd64.deb` in the current directory.
Takes about 30 seconds.

---

## Step 4 — Install

```bash
sudo dpkg -i c4p-social_1.0_amd64.deb
```

The installer will:

1. Check and install Docker Engine if missing
2. Detect NVIDIA GPU — install drivers and container toolkit if found
3. Fix file permissions and line endings
4. Copy the pre-configured `.env` to `/opt/c4p-social/.env`
5. Install and enable the `c4p-social` systemd service
6. Build all Docker images (`docker compose up -d --build`)
7. Pull the DeepSeek R1 14B model via Ollama (~9 GB — takes several minutes)

Watch the install log live:

```bash
tail -f /var/log/c4p-social-install.log
```

---

## Step 5 — If a GPU was installed for the first time

If the installer just installed NVIDIA drivers, you must reboot before the GPU is active:

```bash
sudo reboot
```

After reboot, start the stack manually:

```bash
sudo systemctl start c4p-social
```

---

## Step 6 — Verify everything is running

```bash
docker compose -f /opt/c4p-social/docker-compose.yml ps
```

All services should show `running` or `healthy`.

| URL | Service |
|---|---|
| http://localhost:5000 | Postiz content scheduling dashboard |
| http://localhost:11434 | Ollama API |

---

## Managing the stack

```bash
# Start
sudo systemctl start c4p-social

# Stop
sudo systemctl stop c4p-social

# Restart
sudo systemctl restart c4p-social

# View live logs
docker compose -f /opt/c4p-social/docker-compose.yml logs -f

# View logs for a specific service
docker compose -f /opt/c4p-social/docker-compose.yml logs -f analyzer
```

---

## Editing configuration

The pre-configured `.env` is at `/opt/c4p-social/.env`. To make changes:

```bash
sudo nano /opt/c4p-social/.env
sudo systemctl restart c4p-social
```

---

## Uninstalling

```bash
# Remove the package but keep all data
sudo dpkg -r c4p-social

# Remove everything including the systemd service
sudo dpkg --purge c4p-social

# Also delete Docker volumes (all data — irreversible)
docker volume rm c4p-social_postgres_data c4p-social_ollama_data
```

---

## Troubleshooting

**Services show `restarting` in `docker compose ps`:**
```bash
docker compose -f /opt/c4p-social/docker-compose.yml logs <service-name>
```

**Ollama model failed to pull:**
```bash
docker compose -f /opt/c4p-social/docker-compose.yml exec ollama ollama pull deepseek-r1:14b
```

**GPU not detected after install:**
```bash
nvidia-smi   # should show your GPU
# if not, reboot and try again
sudo reboot
```

**Check full install log:**
```bash
cat /var/log/c4p-social-install.log
```

---

## Source code

The full project source is at: https://github.com/pcanderson2/c4p_local
