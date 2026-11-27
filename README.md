# ClearAir Home

Live demo: <add after deploy>

ClearAir Home is a household air-quality planning tool for people navigating high particulate pollution and winter smog in Indian cities.

## Chosen vertical and persona

- **Vertical:** household air-quality and exposure-reduction planning.
- **Primary persona:** a Kolkata household with young children, biomass cooking, a constrained budget, and a severe AQI reading (for example, AQI 380). The plan is also usable by adults, older people, commuters, and people who report health factors.

## Problem statement

An AQI reading is difficult to translate into practical household decisions. Generic advice such as “stay indoors” does not account for who lives in the home, how people commute, what fuel they cook with, or what they can afford. ClearAir Home turns a user-provided or detected AQI into an organized set of daily routine, indoor air, and household swap suggestions.

## Approach and decision logic

The application uses the **rule engine first and Gemini second**. `app/rules.py` builds a complete, deterministic baseline plan from validated inputs. It applies Indian CPCB AQI bands and explicit rules for respirator guidance, vulnerable household members, reported health factors, cooking fuel, commute, and budget. The rule engine works without network access or an API key.

When configured, Gemini can personalize the explanation around the user’s context. It is not the source of the AQI band or action decisions: output validation requires the baseline actions and band to remain unchanged. If the key is missing, Gemini errors, or its response fails validation, the app returns the baseline plan and sets `used_ai` to `false`.

## How it works

1. The user enters a location, AQI (0–500), household type, optional health factors, commute mode, cooking fuel, and budget. AQI can also be selected from a preset.
2. The browser sends the form to `POST /api/plan`. The API validates the request with Pydantic.
3. The rule engine creates a baseline plan with routine, indoor, and swap sections.
4. If Gemini is configured, the personalization layer receives the baseline and context as data. It may rewrite explanations while preserving action text, AQI band, and section item counts.
5. The API returns the plan as JSON. The browser renders user and model content as text and moves focus to the results.
6. Optional AQI detection can look up a place or use browser-provided coordinates. The backend requests Open-Meteo data and converts PM2.5/PM10 using Indian AQI breakpoints. Manual AQI entry remains available if detection fails.

## Architecture summary

- `app/main.py`: FastAPI routes, request validation integration, security headers, request-size checks, and in-memory rate limiting.
- `app/schemas.py`: Pydantic request and response models.
- `app/rules.py`: deterministic plan and AQI-band logic.
- `app/llm.py`: Gemini prompt construction, response validation, and fallback.
- `app/aqi_provider.py`: Open-Meteo geocoding/air-quality calls, CPCB interpolation, coordinate handling, and in-memory cache.
- `static/`: HTML, CSS, and JavaScript frontend.
- `docs/ARCHITECTURE.md`: request-flow diagram and prompt-flow details.

## Assumptions

- AQI entered by the user is on the Indian AQI scale from 0 to 500.
- Open-Meteo values are modelled estimates and can differ from local monitoring stations. Users can enter or edit AQI manually.
- Household, commute, cooking, budget, and health-factor answers are self-reported.
- The rule engine is a practical decision aid; it does not assess an individual’s exposure or health status.
- Gemini is optional. Without `GEMINI_API_KEY`, deterministic plans remain available.

## Setup and run

Requires Python 3.12 or later.

```bash
python -m venv .venv
# macOS/Linux:
source .venv/bin/activate
# Windows PowerShell:
# .venv\Scripts\Activate.ps1

python -m pip install -r requirements.txt
```

To enable Gemini locally, copy `.env.example` to `.env` and set `GEMINI_API_KEY` there. Do not commit `.env`. Without a key the app uses the deterministic fallback.

```bash
uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Open <http://127.0.0.1:8000>. The health endpoint is <http://127.0.0.1:8000/healthz>.

## Tests and quality checks

Install development dependencies and run the suite:

```bash
python -m pip install -r requirements-dev.txt
python -m pytest -v
```

Run selected groups or quality checks with the Makefile:

```bash
make test-fast
make test-all
make lint
make type-check
make coverage
```

Browser tests require Playwright and its Chromium browser. See [docs/TESTING.md](docs/TESTING.md) for installation and test-group details. Tests must mock Gemini and Open-Meteo; they should not require real API credentials or network services.

## Deploy to Render

ClearAir Home includes a declarative [render.yaml](render.yaml) Blueprint configured for Render's Docker runtime in the Singapore region (closest to users in South Asia).

### Step-by-Step Deployment

1. **Push to GitHub**: Ensure all changes are committed and pushed to your public GitHub repository on branch `main`.
2. **Open Render Dashboard**: Go to [dashboard.render.com](https://dashboard.render.com) and click **New +** > **Blueprint** (or **Web Service**).
3. **Connect Repository**: Select and authorize your `clearair-home` repository.
4. **Confirm Blueprint**: Render reads `render.yaml` automatically, creating the `clearair-home` web service with the `free` plan and `singapore` region.
5. **Set Environment Variables**: When prompted in the dashboard, enter your `GEMINI_API_KEY` (configured with `sync: false`, never committed). If you omit the key, the service starts safely in deterministic fallback mode.
6. **Wait for Deployment**: Render builds the Docker image and performs the `/healthz` health check.
7. **Verify Live Service**: Run the smoke test script against your live Render URL:
   ```bash
   python scripts/smoke_remote.py https://clearair-home.onrender.com
   ```

### Local Docker Testing

You can build and test the production Docker image locally before deploying:

```bash
# 1. Build the Docker container image
docker build -t clearair-home .

# 2. Run container locally (listening on port 10000)
docker run -d -p 10000:10000 -e PORT=10000 --name clearair-test clearair-home

# 3. Run the smoke test against the local container
python scripts/smoke_remote.py http://localhost:10000

# 4. Stop and clean up container
docker stop clearair-test && docker rm clearair-test
```

### Troubleshooting

- **Port binding error**: Render assigns a dynamic port via the `$PORT` environment variable. The Dockerfile binds uvicorn to `0.0.0.0:${PORT:-10000}`. Binding to a hardcoded port or `127.0.0.1` will cause Render port detection to fail.
- **Health check failing**: Render polls `/healthz` to verify deployment health. Ensure the container starts within the timeout and returns HTTP 200 `{"status": "ok"}`.
- **Missing env var**: If `GEMINI_API_KEY` is not provided, the app continues to operate normally in deterministic baseline mode (`used_ai: false`). To enable AI personalization, add the key in Render Dashboard > Environment.
- **Cold start on Free Tier**: Render free-tier services spin down after 15 minutes of inactivity. The first incoming request triggers a container restart that can take 30–60 seconds. The frontend displays an active wake-up notice ("Waking up the server, this can take up to a minute..."). This is a hosting tier limit, not an application bug.
- **CSP blocking requests**: The Content Security Policy (`default-src 'self'`) strictly restricts scripts, stylesheets, and connects to the same origin. External CDNs, unlisted fonts, and third-party trackers are rejected.
- **Rate limiter seeing one IP**: Behind Render's reverse proxy, requests arrive from internal proxy addresses. Uvicorn must be started with `--proxy-headers --forwarded-allow-ips="*"` so the ASGI rate limiter receives each user's real client IP from `X-Forwarded-For`.

## Deployment to Google Cloud Run

Build the container and push it to Artifact Registry, then deploy that image. Create a Secret Manager secret named `gemini-api-key` and grant the Cloud Run service account `roles/secretmanager.secretAccessor` on that secret. Upload the Gemini key as a secret version from a local file kept outside this repository; do not pass the key as a build argument or environment variable during image build.

```bash
PROJECT_ID="YOUR_PROJECT_ID"
REGION="asia-south1"
SERVICE="clearair-home"
REPOSITORY="clearair-home"
SERVICE_ACCOUNT="clearair-run"
IMAGE="$REGION-docker.pkg.dev/$PROJECT_ID/$REPOSITORY/$SERVICE:1"

gcloud config set project "$PROJECT_ID"
gcloud services enable run.googleapis.com artifactregistry.googleapis.com cloudbuild.googleapis.com secretmanager.googleapis.com
gcloud artifacts repositories create "$REPOSITORY" --repository-format=docker --location="$REGION"
gcloud iam service-accounts create "$SERVICE_ACCOUNT" --display-name="ClearAir Home Cloud Run"
gcloud secrets create gemini-api-key --replication-policy=automatic
gcloud secrets versions add gemini-api-key --data-file="/secure/path/gemini-api-key.txt"
gcloud secrets add-iam-policy-binding gemini-api-key \
  --member="serviceAccount:$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --role="roles/secretmanager.secretAccessor"

gcloud builds submit --tag "$IMAGE" .
gcloud run deploy "$SERVICE" \
  --image "$IMAGE" \
  --region "$REGION" \
  --platform managed \
  --allow-unauthenticated \
  --service-account="$SERVICE_ACCOUNT@$PROJECT_ID.iam.gserviceaccount.com" \
  --set-secrets="GEMINI_API_KEY=gemini-api-key:1" \
  --port 8080
```

Replace the project ID, region, and secret-file path before running. Keep the key file outside the repository and remove it after upload. The image runs as a non-root user and listens on Cloud Run’s `PORT`. For a private service, omit `--allow-unauthenticated`. See the [Cloud Run secret configuration guide](https://cloud.google.com/run/docs/configuring/services/secrets) for secret access and rotation details.

## Accessibility and security

- The interface uses semantic landmarks, visible form labels, keyboard-operable controls, focus management, live announcements, reduced-motion styling, and print styles.
- AQI category text accompanies visual indicators; color is not the only signal.
- Dynamic values are inserted as text rather than HTML.
- The API validates inputs and applies a content security policy and other security headers, a request body-size limit, and a per-IP rate limit.
- Browser geolocation is requested only after the user activates the location control. Coordinates are rounded before lookup.
- Gemini keys belong in environment configuration for local development or Secret Manager for deployment, never in source control or the container image.

## Limitations

Detected AQI values are model estimates, and plan impacts are approximate estimates based on stated assumptions. Recommendations are general educational guidance, **not medical advice, diagnosis, or treatment**. The app cannot verify the user’s local conditions, product performance, or individual health needs. For health concerns, follow advice from qualified healthcare professionals and local public-health authorities.
