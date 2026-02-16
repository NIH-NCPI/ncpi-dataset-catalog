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

```
[Browser] --HTTPS--> [CloudFront/ALB] --HTTP--> [Docker container: uvicorn + FastAPI]
                                                        |
                                                  [ConceptIndex in memory]
                                                        |
                                                  [Anthropic API]
```

- Single Docker container running uvicorn with the FastAPI app
- Data files (LLM concepts, catalog studies, hierarchy JSON) mounted as read-only volumes
- `ANTHROPIC_API_KEY` provided via environment variable
- Sits behind a load balancer (ALB or CloudFront origin) with HTTPS termination

## Open Questions (Phase 2)

- **Authentication:** API key or JWT for frontend-to-API auth
- **Rate limiting:** Per-IP or per-key throttling to manage Anthropic API costs
- **Streaming:** SSE for progressive results (show mentions as they resolve)
- **Caching:** Cache pipeline results for identical queries to reduce LLM calls
- **Horizontal scaling:** Multiple container instances behind ALB (index is read-only, stateless)
