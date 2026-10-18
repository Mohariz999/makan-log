# 🍜 Makan Log

Rate hawker dishes: add what you ate, filter by hawker centre and price, and see the top-rated stalls.
Built with Flask and SQLAlchemy on PostgreSQL, and deployed to Google Cloud Run through a
Cloud Build → Artifact Registry pipeline.

| Layer | Local | Production |
|---|---|---|
| Web server | `flask run` / `python app.py` | Gunicorn in a Docker container on Cloud Run |
| Database | SQLite (`instance/makan.db`) | PostgreSQL on a free host (e.g. Neon) |
| Schema | Flask-Migrate (Alembic) migrations in `migrations/` | same, applied on container start |
| Secrets | `.env` (not in git) | Secret Manager |

## Pages and API

- `/`: dishes with filters (`centre`, `max_price`, `sort=rating|price|newest`) and a top-stalls leaderboard
- `/dishes/new`: add a dish (CSRF-protected form)
- `GET /api/dishes`: same filters, JSON
- `GET /api/stalls/top`: stalls ranked by average rating (SQL `GROUP BY` + `AVG`)
- `/health`

## Run locally

```zsh
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
flask --app app db upgrade     # create tables
flask --app app seed           # 12 random starter dishes (only if empty)
python app.py                  # http://127.0.0.1:8080
python -m pytest               # tests
```

After changing a model: `flask --app app db migrate -m "describe change"` then `flask --app app db upgrade`.

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

## Notes

- The app is public (`--allow-unauthenticated`) and anyone with the link can add dishes. Don't put
  anything personal in it.
- `--max-instances=1` keeps it inside the free database's connection limit and stops two containers
  running migrations at once.
- The pipeline tags images with `$SHORT_SHA`, which only exists for trigger builds. For a manual run, use
  `gcloud builds submit --substitutions=SHORT_SHA=manual1`.
