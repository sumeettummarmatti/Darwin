# Deploying SETU to a shared server (Vultr)

SETU runs as **one Docker container** (FastAPI kernel + built React console + SQLite) bound to `127.0.0.1`, behind the server's existing reverse proxy on its own hostname. Nothing belonging to the project already on the server is modified: we add a directory, a container, and one new proxy server block.

> Target: the Vultr server that already runs **SixthSense**. Values below come from the SixthSense deploy kit; items marked *verify* are checked read-only before anything changes.

## 0. What will exist on the server

| Thing | Value |
|---|---|
| Code | `/opt/setu/app` (git clone of the **`deploy`** branch) |
| Persistent data | `/opt/setu/var` (SQLite: record, workflow state, audit chain, mocks) |
| Secrets | `/opt/setu/.env` (mode 600, holds `GROQ_API_KEY` if used) |
| Container | `setu`, image `setu:latest`, restart `unless-stopped` |
| Port | `127.0.0.1:8100` → container `8000` — never exposed publicly |
| Hostname | `setu.139-84-220-87.sslip.io` via the existing reverse proxy, TLS from the same mechanism the other project uses |
| Access | HTTP basic auth at the proxy (the console has no login of its own) |

## 1. Prepare (once)

```bash
ssh root@139.84.220.87
sudo mkdir -p /opt/setu/var && sudo chown -R $USER:$USER /opt/setu
git clone -b deploy https://github.com/sumeettummarmatti/Darwin.git /opt/setu/app
touch /opt/setu/.env && chmod 600 /opt/setu/.env      # add GROQ_API_KEY=… here, or paste it in the console later
```

Check the chosen port is free and Docker is present — and confirm nothing of the other project is touched:

```bash
ss -ltnp | grep -E ':8100\b' || echo "port free"
docker ps --format '{{.Names}}\t{{.Ports}}'         # note the other project's containers; we leave them alone
```

## 2. Build and run

```bash
cd /opt/setu/app
docker build -t setu:latest .
docker run -d --name setu --restart unless-stopped \
  -p 127.0.0.1:8100:8000 \
  -v /opt/setu/var:/app/var \
  -v /opt/setu/.env:/app/.env \
  --memory 512m --cpus 1 \
  setu:latest
curl -s http://127.0.0.1:8100/api/health
```

The first start seeds the synthetic dataset into `/opt/setu/var`. `--memory`/`--cpus` keep SETU from starving the other project.

## 3. Reverse proxy (new server block only)

### nginx (not used on this server — kept for other hosts)

```nginx
# /etc/nginx/sites-available/setu   (new file — the existing site's file is not edited)
server {
    server_name setu.139-84-220-87.sslip.io;
    client_max_body_size 2m;

    auth_basic "SETU demo";
    auth_basic_user_file /etc/nginx/.setu_htpasswd;

    location / {
        proxy_pass http://127.0.0.1:8100;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 120s;          # real-model calls can take a while
    }
    listen 80;
}
```

```bash
sudo htpasswd -c /etc/nginx/.setu_htpasswd judge        # apache2-utils; share the password with the panel only
sudo ln -s /etc/nginx/sites-available/setu /etc/nginx/sites-enabled/setu
sudo nginx -t && sudo systemctl reload nginx            # reload, not restart: the other site stays up
sudo certbot --nginx -d setu.139-84-220-87.sslip.io              # only this hostname
```

### Caddy — what this server uses

```bash
cp /etc/caddy/Caddyfile /etc/caddy/Caddyfile.bak.$(date +%F-%H%M)      # back up first
caddy hash-password                                                    # prints a bcrypt hash for the demo password
```

Append **one new block** (existing SixthSense blocks untouched):

```caddy
setu.139-84-220-87.sslip.io {
    basic_auth {
        judge «bcrypt-hash-from-caddy-hash-password»
    }
    reverse_proxy 127.0.0.1:8100
}
```

```bash
caddy validate --config /etc/caddy/Caddyfile && systemctl reload caddy    # reload, never restart
```

DNS: none needed — `sslip.io` resolves `setu.139-84-220-87.sslip.io` to `139.84.220.87`, and Caddy obtains the certificate automatically.

## 4. Update

The server only ever runs the `deploy` branch. Ship a release by fast-forwarding it from `main` on your machine:

```bash
git checkout deploy && git merge --ff-only main && git push origin deploy && git checkout main
```

Then on the server:

```bash
cd /opt/setu/app && git pull
docker build -t setu:latest .
docker rm -f setu && <the docker run command from step 2>
```

Data in `/opt/setu/var` survives. To start the demo fresh, use **Reset** in the console (or `docker rm -f setu && rm -rf /opt/setu/var/*` and run again).

## 5. Operate

| Task | Command |
|---|---|
| Logs | `docker logs -f setu` |
| Health | `curl -s http://127.0.0.1:8100/api/health` |
| Audit chain intact? | `curl -s http://127.0.0.1:8100/api/audit/verify` |
| Stop / start | `docker stop setu` / `docker start setu` |
| Remove completely | `docker rm -f setu`, delete the `setu.…sslip.io` block from the Caddyfile, `systemctl reload caddy` |

## 6. Safety notes

- **Synthetic data only.** Never load real employee data onto the demo server.
- **Basic auth is required.** The console can reset data, edit policies and the reserved list, and store a model key; without auth anyone with the URL could.
- **Groq key**: paste it in *Guardrails → Model provider* (validated with Groq, written to `/opt/setu/.env`, never displayed), or put it in `/opt/setu/.env` before starting. Without a key SETU runs on the offline simulator.
- The container listens on `127.0.0.1` only; do not add a public port or a firewall rule for it.

## Server facts (Vultr, shared with SixthSense)

| | |
|---|---|
| Host | `139.84.220.87`, Ubuntu (*verify* `lsb_release -a`), SSH `root@139.84.220.87` with the existing key |
| Reverse proxy | Caddy, `/etc/caddy/Caddyfile`, automatic Let's Encrypt — no nginx, no certbot |
| Taken hostnames | `api.139-84-220-87.sslip.io` (:8000), `insight.139-84-220-87.sslip.io` (:8001) |
| SETU hostname | `setu.139-84-220-87.sslip.io` |
| Ports in use (all 127.0.0.1) | 8000, 8001, 8003 (CompreFace), 5433, 5434, 6379, 4222, 8222, 1025, 8025 — **SETU uses 8100** (*verify* free with `ss -ltn`) |
| Docker | apt `docker.io` + `docker-compose-v2` (*verify* `docker --version`) |
| Firewall | Vultr cloud firewall + ufw; 22, 80, 443 open (*verify* `ufw status`). SETU needs no new rule |
| Memory | CompreFace + two Postgres are heavy — *verify* `free -h` before starting SETU (it is capped at 512 MB) |

**Do not touch:** `/opt/sixthsense`, the `sixthsense-*` systemd units, the existing Caddy blocks, SixthSense's compose project. **Never run `docker system prune`** (it could delete SixthSense's images and volumes). SETU uses `docker run --name setu`, not a compose project, so no `compose down` can reach the other app.

### Read-only pre-flight (changes nothing)

```bash
lsb_release -ds; nproc; free -h; df -h /; docker --version
ss -ltn | grep -E ':8100\b' || echo "8100 free"
ufw status | head -20
systemctl is-active sixthsense-core sixthsense-insight sixthsense-worker caddy
```
