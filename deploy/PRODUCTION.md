# Production runbook

Smart Docs runs on the same Hetzner box as 3m4 (`46.225.62.18`) and is served by 3m4's Caddy. One compose project, four containers: `db`, `api`, `worker`, `ollama`.

## Sizing

The local tier needs RAM for the models. `qwen2.5:3b` takes about 2.5 GB, `nomic-embed-text` about 0.5 GB, both on CPU.

| Server | RAM | Fits |
| --- | --- | --- |
| CX22 (current, also runs 3m4) | 4 GB | `LOCAL_MODEL=qwen2.5:0.5b` only, and it is tight |
| CX32 | 8 GB | `qwen2.5:1.5b` comfortably, `qwen2.5:3b` with swap |
| CX42 | 16 GB | `qwen2.5:3b` as decided in SD-005 |

Resizing in the Hetzner console takes about a minute of downtime. A GPU is not needed: summaries run in the worker, one at a time, and a 3b model answers in 10 to 30 s on 4 vCPUs.

## First-time setup

1. Clone and configure.
   ```sh
   ssh root@46.225.62.18
   git clone https://github.com/Devace-93/smart-docs.git /opt/smart-docs
   cd /opt/smart-docs && cp .env.example .env && $EDITOR .env
   ```
   Set `PUBLIC_BASE_URL=https://smart-docs.3m4.net`, fresh `SECRET_KEY`, `IP_HASH_SALT`, `FERNET_KEY` and `POSTGRES_PASSWORD` (mirror it in `DATABASE_URL`). Pick `LOCAL_MODEL` from the sizing table. Set `HOSTED_ENABLED=true` and `HOSTED_API_KEY` only when the DeepSeek account exists.
2. Start.
   ```sh
   docker compose -f docker-compose.yml -f deploy/docker-compose.prod.yml --profile local up -d --build
   docker compose logs -f ollama-pull   # wait for both models
   ```
3. Caddy: append `deploy/Caddyfile.snippet` to `/opt/3m4/deploy/Caddyfile.prod`, then from `/opt/3m4/deploy`:
   ```sh
   docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --force-recreate caddy
   ```
4. DNS (Bluehost): an A record `smart-docs` pointing at `46.225.62.18`. Caddy issues the certificate once the name resolves.
5. First account: open `https://smart-docs.3m4.net/signup`, or `docker compose exec api sd create-user you@example.com --handle you`.
6. Seed the decision log as the first public project:
   ```sh
   docker compose exec api sd seed docs/decisions --handle enrique --project smart-docs-decisions --name "Smart Docs decisions" --public
   ```

## Deploy on push

`.github/workflows/deploy.yml` runs the same `up -d --build` over SSH on every push to `main` once the repository has the secrets `DEPLOY_HOST` and `DEPLOY_SSH_KEY` and the variable `DEPLOY_ENABLED=true`. The 3m4 repo uses the same key.

## Backups

`deploy/backup.sh` dumps Postgres to `/var/backups/smart-docs/`. Cron: `20 3 * * * /opt/smart-docs/deploy/backup.sh`.
