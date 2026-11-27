# Prompt Log Template

Use this file to record prompts and decisions for this project. The project history below is intentionally blank; add only entries you personally supplied or verified.

## Tools used and why

| Tool | Why it was used |
| --- | --- |
| Render Blueprint (`render.yaml`) | Infrastructure-as-code for zero-config Docker deployments with health checks and secret management. |
| Uvicorn ProxyHeaders | Ensures proper client IP extraction behind Render's reverse proxy for per-IP rate limiting. |
| Python standard library smoke test | Portable, dependency-free verification for post-deployment health and security validation. |

## How prompts evolved

_Add notes about how your prompts changed during the work._

## What GenAI handled vs what the human designed

| GenAI handled | Human designed or decided |
| --- | --- |
|  |  |

## Prompts

Paste your prompts into the table. Leave entries blank until you are ready to record them.

| Date / sequence | Prompt (paste verbatim) | Goal or context | Result / decision |
| --- | --- | --- | --- |
| 2026-11-26 | Prepare clearair-home for deployment on Render using the existing Dockerfile. Do not change application behaviour. Keep everything on the single main branch and the repo under 10 MB. Never put secrets in the repo. | Deploy to Render with Docker runtime, blueprint configuration, cold-start handling, and remote smoke tests. | Render selected for free-tier Docker support, native HTTPS (required for geolocation), Singapore region proximity to South Asia, and declarative `render.yaml` infrastructure-as-code. Dockerfile and rate limiter updated for Render reverse proxy; smoke script created. |
