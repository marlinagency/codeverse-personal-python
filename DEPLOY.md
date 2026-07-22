# Deploying the Public Demo (AMD Developer Cloud)

One droplet runs the whole stack 24/7: nginx-served frontend, FastAPI
backend, Postgres, and Docker-sandboxed code execution. Theme generation
calls Fireworks (`glm-5p2`). Every visitor automatically gets their own
isolated anonymous account (`CODEVERSE_PUBLIC_DEMO=1`).

## 1. Create the droplet (AMD console — you)

- AMD Developer Cloud → create a basic CPU droplet (no GPU needed for the
  site), Ubuntu 22.04/24.04, 4 GB+ RAM recommended.
- Note the public IP; make sure port 80 is open in its firewall settings.

## 2. On the droplet (SSH)

```bash
# docker + compose
curl -fsSL https://get.docker.com | sh

# code
git clone <YOUR_GITHUB_REPO_URL> codeverse && cd codeverse

# config — create .env at the repo root:
cat > .env <<'EOF'
CODEVERSE_ENVIRONMENT=production
CODEVERSE_LLM_PROVIDER=fireworks
CODEVERSE_FIREWORKS_API_KEY=<your fw_ key>
CODEVERSE_FIREWORKS_MODEL=accounts/fireworks/models/glm-5p2
CODEVERSE_PUBLIC_DEMO=1
CODEVERSE_JWT_SECRET=<any long random string>
EOF

# sandbox runtime images (user code runs in these sibling containers)
docker build -t codeverse-python-runtime:3.12 docker/runtimes/python
docker build -t codeverse-sql-runtime:16 docker/runtimes/sql

# the stack
docker compose up -d --build
```

## 3. Verify

- `http://<IP>/` → app loads
- `http://<IP>/health` → `{"status":"ok"}`
- Create a theme end to end; open the same URL in a private window and
  confirm the theme list is EMPTY there (visitor isolation works).

## Notes

- **Frontend prerequisite:** every remaining hardcoded `http://localhost:8000`
  in `frontend/src` must go through `lib/api.ts` (`VITE_API_BASE_URL`); the
  production build uses relative URLs proxied by nginx. Hardcoded ones will
  break on the public site.
- Postgres data persists in the `codeverse-pgdata` volume; `docker compose
  down` keeps it, `down -v` wipes it.
- The backend applies Alembic migrations automatically before it starts.
  PostgreSQL and FastAPI stay private inside Compose; only nginx port 80 is
  published to the internet.
- **Fail-closed execution:** with `CODEVERSE_ENVIRONMENT=production` (or
  `CODEVERSE_PUBLIC_DEMO=1`), if the Docker sandbox is ever unreachable the
  code-execution endpoints return **503** instead of running user code
  unsandboxed on the host. Keep the sandbox runtime images built (step above)
  and the Docker daemon healthy, or execution will be unavailable by design.
- Update flow: `git pull && docker compose up -d --build`.
- Rough cost: a small CPU droplet runs weeks on the $100 credit; visitor
  theme generations cost ~1-2 Fireworks cents each.
