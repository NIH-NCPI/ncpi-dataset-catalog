# PRD: NLP Concept Search API

**Issue:** #178
**Status:** Draft
**Author:** Dave Rogers
**Date:** 2026-02-16

## Problem

The NCPI Dataset Catalog is a static Next.js site deployed to S3/CloudFront with no server runtime. The concept search pipeline (3-agent LLM system: extract, resolve, structure) runs locally via CLI only. We need an HTTP API so the frontend can send natural-language queries and receive structured results with matching studies.

## Solution

A FastAPI service that wraps the existing concept search pipeline and exposes it via a simple REST API. The service preloads the ConceptIndex at startup, accepts natural-language queries, runs the full pipeline, performs deterministic study lookup, and returns structured JSON.

## API Design

### `POST /search`

Runs the full pipeline on a natural-language query and returns matching studies.

**Request:**

```json
{ "query": "studies with blood pressure and diabetes" }
```

**Response:**

```json
{
  "query": {
    "mentions": [
      {
        "facet": "measurement",
        "originalText": "blood pressure",
        "values": ["Systolic Blood Pressure", "Diastolic Blood Pressure"],
        "exclude": false
      }
    ],
    "message": null
  },
  "studies": [
    {
      "dbGapId": "phs000007",
      "title": "Framingham Heart Study",
      "focus": "Cardiovascular",
      "platforms": ["BDC"],
      "dataTypes": ["WGS"],
      "studyDesigns": ["Longitudinal Cohort"],
      "consentCodes": ["HMB-MDS"],
      "participantCount": 14428
    }
  ],
  "totalStudies": 42,
  "message": null,
  "timing": {
    "pipelineMs": 2800,
    "lookupMs": 12,
    "totalMs": 2812
  }
}
```

### `GET /health`

Returns service health and index statistics.

```json
{
  "status": "ok",
  "indexStats": {
    "measurement": 12187,
    "focus": 345,
    "consentCode": 892,
    "dataType": 12,
    "platform": 4,
    "studyDesign": 8
  }
}
```

## Response Schema

- All field names use **camelCase** to match the existing catalog JSON and frontend TypeScript types
- `StudySummary` is a lean projection of the full study object (strips `description`, `publications`, etc.)
- `timing` reports wall-clock milliseconds for the LLM pipeline and the deterministic index lookup separately
- `message` carries clarification text when the query is vague or partially unresolved (null on clean success)

## Latency Expectations

- **Pipeline:** ~3-5 seconds per query (dominated by Anthropic API round-trips: extract + 1-N resolve + structure)
- **Index lookup:** <50ms (in-memory intersection)
- **Index preload:** ~5 seconds at startup (111MB JSON)
- **Health check:** <10ms

## Deployment Architecture

### Overview

```
[Browser] --HTTPS--> [App Runner (auto TLS)] ---> [uvicorn + FastAPI]
                                                        |
                                                  [ConceptIndex in memory]
                                                        |
                                                  [Anthropic API]
```

### Why App Runner

| Criteria | App Runner | ECS Fargate | EC2 | Lambda |
|---|---|---|---|---|
| Monthly cost | ~$2.60 | ~$23 (needs ALB) | ~$6 | ~$0 |
| Cold start | None (warm) | 20-60s from zero | None | 2-5s (index load) |
| Burst handling | Auto-scales | Slow to scale | Single instance | Excellent |
| HTTPS | Built-in, auto-managed | Needs ALB ($16/mo) | DIY | Built-in |
| Terraform complexity | ~50 lines | High | Medium | Medium + Mangum wrapper |

App Runner keeps one provisioned instance warm (no cold starts), provides auto-managed HTTPS, auto-scales for bursts, and costs ~$2.60/mo at idle. No ALB, no TLS cert management, no code changes needed.

### Environments

| | **Dev** | **Prod** |
|---|---|---|
| AWS account | Clever Canary (`excira` profile) | NCPI prod (`ncpi-prod-deployer` profile) |
| Frontend | `g78-ncpi-data.humancellatlas.dev` (S3/CloudFront) | `bhy-ncpi-data.org` (S3/CloudFront) |
| API service | App Runner in same account | App Runner in same account |
| CORS origins | Dev CloudFront domain + `localhost:3000` | Prod CloudFront domain |

### Infrastructure (Terraform)

Uses the existing [findable-tf](https://github.com/clevercanary/findable-tf) infrastructure repo with a new generic `app-runner/` module. Environment-specific config lives in [findable-tf-variables](https://github.com/clevercanary/findable-tf-variables).

**Repos and issues:**
- `findable-tf` — [#116](https://github.com/clevercanary/findable-tf/issues/116): Generic App Runner module
- `findable-tf-variables` — [#21](https://github.com/clevercanary/findable-tf-variables/issues/21): NCPI search API tfvars

**Resources created per App Runner service:**
- **ECR repository** — stores the Docker image
- **App Runner service** — pulls from ECR, runs the container
  - Configurable CPU/memory (default 0.25 vCPU / 0.5 GB)
  - Auto-scaling: min 1 / max configurable instances, concurrency-based
  - Configurable health check path
  - Environment variables and secrets (from Secrets Manager)
- **IAM access role** — allows App Runner to pull from ECR
- **IAM instance role** — allows container to read from Secrets Manager
- **Auto-scaling configuration** — concurrency-based scaling

**Zero disruption to existing stacks:**
- New `app_runner_services` variable defaults to `[]` — existing stacks ignore it
- Static-site resources (CloudFront, S3, etc.) wrapped in conditionals via `enable_static_site` local
- `moved` blocks handle state address changes transparently for existing stacks
- Existing `terraform plan` shows zero changes

**Module structure in findable-tf:**
```
findable-tf/
  app-runner/            # NEW — generic App Runner module
    main.tf              # ECR + App Runner service + auto-scaling
    iam.tf               # Access role + instance role
    variables.tf         # All configurable inputs
    outputs.tf           # Service URL, ARN
  main.tf                # Updated — conditional static-site + App Runner module
  variables.tf           # Updated — app_runner_services variable added
```

**Variable files in findable-tf-variables:**
```
findable-tf-variables/
  cc-excira/
    ncpi-data-dev/              # Existing — static site (unchanged)
    ncpi-data-prod/             # Existing — static site (unchanged)
    ncpi-search-api-dev/        # NEW — App Runner for dev
      terraform.tfvars
    ncpi-search-api-prod/       # NEW — App Runner for prod
      terraform.tfvars
```

### Data File Strategy

Data files (~111MB total) need to be available to the container at runtime. Options:

1. **Bake into Docker image** (simplest) — rebuild and redeploy image when catalog data updates. Works well since catalog rebuilds are infrequent.
2. **S3 download at startup** — container downloads files from S3 on boot. Adds ~5-10s to startup but decouples data updates from image deploys.

Recommendation: **Bake into the image** for Phase 1. The catalog rebuilds infrequently and a simple CI pipeline can rebuild the image when data changes.

### CI/CD Pipeline

1. Push to `main` (or tag) triggers build
2. Build Docker image with current data files baked in
3. Push image to ECR
4. App Runner auto-deploys from ECR (via image tag update or auto-deployment)

## Open Questions (Phase 2)

- **Authentication:** API key or JWT for frontend-to-API auth
- **Rate limiting:** Per-IP or per-key throttling to manage Anthropic API costs
- **Streaming:** SSE for progressive results (show mentions as they resolve)
- **Caching:** Cache pipeline results for identical queries to reduce LLM calls
- **Custom domain:** Route API through a subdomain (e.g., `api.ncpi-data.org`) instead of the App Runner default URL
