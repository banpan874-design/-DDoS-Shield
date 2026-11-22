# DDoS Shield & Remote Control

A lightweight website monitoring dashboard designed to run locally in Android Termux. Add a public HTTPS website and the monitor begins checking it automatically.

## Current capabilities

- Local FastAPI web dashboard
- Admin bearer-token authentication
- Add and remove monitored website URLs
- Automatic checks immediately after adding and then on a configurable interval
- HTTP status, response latency, last-check time, and recent status-change events
- SQLite storage
- Rejects non-HTTPS URLs and hostnames resolving to non-public IP addresses
- No arbitrary shell execution or remote command endpoint

The repository currently implements **availability monitoring**, not full DDoS detection or mitigation. A successful HTTP check does not prove that a site is free from attack.

## Requirements

- Android with Termux
- Python 3
- Internet access for checking public websites

## Install in Termux

Run each command separately:

1. Update packages:

```bash
pkg update && pkg upgrade -y
```

2. Install Python:

```bash
pkg install python -y
```

3. Clone this repository:

```bash
git clone https://github.com/banpan874-design/-DDoS-Shield.git
```

4. Enter the project:

```bash
cd -- -DDoS-Shield
```

5. Create a virtual environment:

```bash
python -m venv .venv
```

6. Activate it:

```bash
source .venv/bin/activate
```

7. Install dependencies:

```bash
pip install -r requirements.txt
```

8. Create your local environment file:

```bash
cp .env.example .env
```

9. Generate a strong admin token:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

10. Open the environment file:

```bash
nano .env
```

Set `SHIELD_ADMIN_TOKEN` to the generated value. Keep `SHIELD_HOST=127.0.0.1` so the dashboard is not exposed to your local network by default. Save with Ctrl+O, Enter, then Ctrl+X.

11. Start the dashboard:

```bash
uvicorn app:app --host 127.0.0.1 --port 8787
```

12. Open this address in your Android browser:

`http://127.0.0.1:8787`

13. Paste the admin token into the dashboard and select **Connect**. The initial target `https://example.com` is added automatically when the database is first created.

## Configuration

Edit `.env`:

| Variable | Default | Purpose |
|---|---|---|
| SHIELD_HOST | 127.0.0.1 | Bind address; keep local by default |
| SHIELD_PORT | 8787 | Dashboard port |
| SHIELD_DB | shield.db | SQLite database file |
| SHIELD_ADMIN_TOKEN | required secret | API access token |
| SHIELD_MONITOR_INTERVAL | 60 | Check interval in seconds; minimum 30 |

## API

All endpoints except health require the header:

`Authorization: Bearer YOUR_ADMIN_TOKEN`

- `GET /api/health` — health endpoint
- `GET /api/summary` — monitored sites and recent events
- `POST /api/sites` — add a site; monitoring starts immediately
- `POST /api/sites/{id}/check` — run an immediate check
- `DELETE /api/sites/{id}` — remove a site

## Important security and DDoS limitations

This application runs on your Android device. It cannot absorb or filter large volumetric attacks against a remote website. Real DDoS mitigation must happen upstream, using a provider such as a CDN, WAF, reverse proxy, or hosting-provider protection.

The current version does not inspect server traffic logs, block attacking IP addresses, change firewall rules, or remotely administer hosting servers. Those features require explicit integrations, least-privilege credentials, audit logging, and careful authorization.

Only add websites you own or are explicitly authorized to monitor. Monitoring frequency is intentionally limited to at least 30 seconds. Keep the dashboard bound to localhost unless you have properly secured remote access.

## Troubleshooting

- If port 8787 is busy, stop the previous server with Ctrl+C or choose another `SHIELD_PORT` in `.env`.
- If the dashboard says Unauthorized, verify the token in `.env` and restart the server.
- If a domain is rejected, confirm it uses HTTPS and resolves only to public IP addresses.
- Keep the Termux session and server process running for continuous monitoring.

## Roadmap

- CDN/WAF provider integrations
- Inbound traffic and server-log analysis
- Configurable alert destinations
- Per-site monitoring policies and reports
- Secure, audited remote administration through provider APIs

---
Built for authorized website monitoring and defensive security learning.
