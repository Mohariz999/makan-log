# 🍜 Makan Log

A small web app for rating Singapore hawker dishes: log what you ate, filter by hawker centre and price,
and see which stalls rate highest. It has a server-rendered UI, a JSON API, and a tested CI/CD pipeline
that deploys to Google Cloud Run on every push to `main`.

**Live demo:** https://makan-log-544562288445.asia-southeast1.run.app
(it scales to zero when idle, so the first request can take around 10 seconds)

## Features

- Browse dishes, filter by hawker centre and maximum price, and sort by rating, price or newest
- A leaderboard of stalls ranked by average rating, computed in SQL with `GROUP BY` and `AVG`
- An add-dish form with server-side validation and CSRF protection
- A read-only JSON API that takes the same filters, with JSON error responses
- Constraints enforced in the database as well as the app: ratings 1–5, non-negative prices, unique stalls per centre

## Tech stack

| Layer | Local | Production |
|---|---|---|
| App | Flask 3, SQLAlchemy, Jinja, Bootstrap 5 | same |
| Web server | `python app.py` (Flask dev server) | Gunicorn in a Docker container on Cloud Run |
| Database | SQLite (`instance/makan.db`) | PostgreSQL (Neon), via psycopg 3 |
| Schema | Flask-Migrate (Alembic) migrations in `migrations/` | same, applied on container start |
| Secrets | `.env` (not in git) | Google Secret Manager |
| CI/CD | `pytest` | Cloud Build: test → build → push to Artifact Registry → deploy |

```
git push ──▶ Cloud Build ──▶ pytest ──▶ docker build ──▶ Artifact Registry ──▶ Cloud Run ──▶ PostgreSQL
                              (a failing test stops the deploy)                  (secrets from Secret Manager)
```

## API

| Endpoint | Description |
|---|---|
| `GET /api/dishes` | Dishes as JSON. Optional `centre`, `max_price`, `sort=rating\|price\|newest` (up to 200) |
| `GET /api/stalls/top` | Top 5 stalls by average rating, with dish counts |
| `GET /health` | Health check |

```bash
curl "https://makan-log-544562288445.asia-southeast1.run.app/api/dishes?max_price=5&sort=price"
```

Invalid input returns a JSON error, for example `400 {"error": "Bad Request", "message": "max_price must be a number."}`.

## Project layout

```
app.py            app factory, models (Stall 1─* Dish), queries, routes, `flask seed` command
seed.py           random starter data (made-up stalls at real hawker centres)
migrations/       Alembic migrations
templates/        Jinja templates (Bootstrap 5)
tests/            pytest suite, run against in-memory SQLite
Dockerfile        production image (non-root user, Gunicorn)
cloudbuild.yaml   CI/CD pipeline
```

## Run locally

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
flask --app app db upgrade     # create tables
flask --app app seed           # 12 random starter dishes (only if the table is empty)
python app.py                  # http://127.0.0.1:8080
python -m pytest               # tests
```

After changing a model, run `flask --app app db migrate -m "describe change"`, then `flask --app app db upgrade`.

## Deploy to Google Cloud (one-time setup)

Project: `new-app-512010`, region `asia-southeast1`.

### 1. Free PostgreSQL

Create a free project at [neon.tech](https://neon.tech) (choose the Singapore region if offered) and copy
its connection string, `postgresql://…?sslmode=require`. Keep it private.

### 2. Cloud Shell

Open [console.cloud.google.com](https://console.cloud.google.com), select the project, and click the
**Cloud Shell** terminal icon (top right). It already has `gcloud` and is signed in. Run:

```bash
gcloud config set project new-app-512010
gcloud services enable run.googleapis.com cloudbuild.googleapis.com \
  artifactregistry.googleapis.com secretmanager.googleapis.com

# Docker image repository
gcloud artifacts repositories create makan-repo \
  --repository-format=docker --location=asia-southeast1

# Secrets (paste your Neon URL between the quotes)
printf '%s' 'postgresql://PASTE-YOUR-NEON-URL' | gcloud secrets create makan-database-url --data-file=-
openssl rand -hex 32 | tr -d '\n' | gcloud secrets create makan-secret-key --data-file=-

# Service accounts: one for Cloud Build to deploy with, plus Cloud Run's runtime account
PROJECT_NUMBER=$(gcloud projects describe new-app-512010 --format='value(projectNumber)')
RUNTIME_SA=${PROJECT_NUMBER}-compute@developer.gserviceaccount.com
gcloud iam service-accounts create makan-deployer --display-name="Makan Log deployer"
DEPLOYER=makan-deployer@new-app-512010.iam.gserviceaccount.com
for role in roles/run.admin roles/artifactregistry.writer roles/logging.logWriter; do
  gcloud projects add-iam-policy-binding new-app-512010 --member=serviceAccount:$DEPLOYER --role=$role
done
gcloud iam service-accounts add-iam-policy-binding $RUNTIME_SA \
  --member=serviceAccount:$DEPLOYER --role=roles/iam.serviceAccountUser
for secret in makan-database-url makan-secret-key; do
  gcloud secrets add-iam-policy-binding $secret \
    --member=serviceAccount:$RUNTIME_SA --role=roles/secretmanager.secretAccessor
done
```

### 3. Connect GitHub and create the trigger

In the console: **Cloud Build → Triggers → Connect repository**. Choose GitHub, install the
Cloud Build GitHub app on the `makan-log` repo only, then **Create trigger**:

- Region: `asia-southeast1`
- Event: push to branch `^main$`
- Configuration: Cloud Build configuration file, `cloudbuild.yaml`
- Service account: `makan-deployer@new-app-512010.iam.gserviceaccount.com`

From then on every `git push` to `main` runs **test → build → push → deploy**. Failing tests stop the
pipeline before anything is deployed. The service URL appears under **Cloud Run → makan-log**.

## Design notes

- The demo is public (`--allow-unauthenticated`), so anyone with the link can add dishes.
- `--max-instances=1` keeps it inside the free database's connection limit and stops two containers
  running migrations at once.
- The pipeline tags images with `$SHORT_SHA`, which only exists for trigger builds. For a manual run, use
  `gcloud builds submit --substitutions=SHORT_SHA=manual1`.

## Licence

MIT. See [LICENSE](LICENSE).
