# Deploying Solar Advisor

Solar Advisor ships as a Docker Compose stack — three services (a read-only MQTT
**collector**, a FastAPI **api**, and an nginx-served **web** SPA) plus one named
volume for the SQLite database. That means it runs on **any Docker host**. This guide
covers Proxmox VE (the most common self-host target) but the *Deploy the stack*
section applies to any host running Docker.

> The host only needs to reach your **SolarAssistant / MQTT broker** on the LAN. The
> app is strictly read-only against the inverter — it never publishes to MQTT.

## TL;DR

1. Get a Docker host on the same LAN as your broker (LXC or VM — see below).
2. Clone the repo, create `backend/.env`, `docker compose up -d --build`.
3. Open `http://<host>:8080`.

---

## Proxmox: pick a Docker host

### Option A — Debian LXC with Docker (lightest, recommended)

A small unprivileged LXC is plenty for this stack.

**Easiest:** use the community **Proxmox VE Helper-Scripts**
(<https://community-scripts.github.io/ProxmoxVE/>) — their **Docker** entry runs a
single command on the Proxmox *host* shell and provisions a Debian LXC with Docker
and Compose already installed. Then jump to *Deploy the stack*.

**Manual alternative** (no third-party script):

1. Create a **Debian 12** LXC: ~2 vCPU, 1–2 GB RAM, 8 GB disk. Unprivileged is fine.
2. Enable container nesting so Docker can run — on the Proxmox host:
   ```bash
   # for container ID 123
   pct set 123 -features nesting=1,keyctl=1
   ```
   (or *Container → Options → Features → Nesting*), then start it.
3. Inside the container, install Docker:
   ```bash
   apt update && apt install -y curl
   curl -fsSL https://get.docker.com | sh
   ```

### Option B — Debian VM with Docker (most robust)

If you'd rather avoid LXC/Docker nesting quirks, create a **Debian 12 VM**
(~2 vCPU, 2 GB RAM, 10 GB disk), then install Docker the same way:
`curl -fsSL https://get.docker.com | sh`.

> **Give the LXC/VM a static IP** (or a DHCP reservation). The dashboard URL then
> stays stable — important when you embed it in Home Assistant.

---

## Deploy the stack (any Docker host)

```bash
git clone https://github.com/<your-account>/solar-advisor.git
cd solar-advisor/backend

cp .env.example .env
# Edit .env — at minimum set SA_MQTT_HOST (your broker) and ANTHROPIC_API_KEY.
# Not using the Explain panel? Set SA_EXPLAIN_ENABLED=false and leave any
# placeholder for ANTHROPIC_API_KEY (compose requires the variable to be set).

docker compose up -d --build
```

Then open:

| What | URL |
| --- | --- |
| Dashboard (SPA) | `http://<host>:8080` |
| API | `http://<host>:8000` |
| Home Assistant tile strip | `http://<host>:8080/?embed=tiles` |

The full environment-variable reference is in the [README](../README.md); the
defaults live in `backend/.env.example`.

---

## Operating it

- **Update to a new version:**
  ```bash
  cd solar-advisor && git pull
  cd backend && docker compose up -d --build
  ```
- **Data & backups:** telemetry and logged purchases live in the `sa_data` Docker
  volume (mounted at `/data`, SQLite). Back it up with:
  ```bash
  docker run --rm -v backend_sa_data:/data -v "$PWD":/backup alpine \
    tar czf /backup/solar-advisor-data.tgz -C /data .
  ```
  (The volume is named `<project>_sa_data`; confirm with `docker volume ls`.)
- **Autostart:** set the LXC/VM to start on boot. The services already use
  `restart: unless-stopped`, so they come back after a reboot or crash.
- **Logs:** `docker compose logs -f` (add a service name, e.g. `collector`, to scope).

---

## Notes

- This is a LAN appliance with **no built-in authentication** — keep it on a trusted
  network, or put it behind an authenticating reverse proxy if you expose it.
- nginx serves `index.html` with `no-cache` and content-hashed assets as immutable,
  so a redeploy is picked up immediately by already-loaded browsers/kiosks.
