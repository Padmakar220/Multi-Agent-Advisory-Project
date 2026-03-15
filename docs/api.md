# API Documentation

## Overview

The Multi-Agent Advisory AI System exposes a REST API via Amazon API Gateway. All endpoints require Cognito JWT authentication.

**Base URL:** `https://{api-id}.execute-api.{region}.amazonaws.com/{stage}`

**Authentication:** Bearer token (Cognito User Pool JWT)
```
Authorization: Bearer <id_token>
```

---

## Endpoints

### POST /analyze

Trigger a portfolio analysis workflow.

**Request:**
```json
{
  "portfolio_id": "portfolio-123",
  "analysis_type": "comprehensive"
}
```

**Response 200:**
```json
{
  "execution_arn": "arn:aws:states:...",
  "session_id": "sess-uuid",
  "status": "RUNNING"
}
```

---

### POST /rebalance

Trigger a portfolio rebalancing workflow.

**Request:**
```json
{
  "portfolio_id": "portfolio-123",
  "target_allocation": {
    "equities": 0.60,
    "bonds": 0.30,
    "cash": 0.10
  },
  "constraints": {
    "risk_tolerance": "moderate",
    "excluded_securities": ["XYZ"]
  }
}
```

**Response 200:**
```json
{
  "execution_arn": "arn:aws:states:...",
  "session_id": "sess-uuid",
  "status": "RUNNING"
}
```

---

### POST /optimize-tax

Trigger a tax-loss harvesting workflow.

**Request:**
```json
{
  "portfolio_id": "portfolio-123",
  "tax_year": 2025
}
```

**Response 200:**
```json
{
  "execution_arn": "arn:aws:states:...",
  "session_id": "sess-uuid",
  "status": "RUNNING"
}
```

---

### POST /approval

Submit approval or rejection for a pending trade plan.

**Request:**
```json
{
  "task_token": "step-functions-task-token",
  "decision": "approved",
  "feedback": "Looks good"
}
```

`decision` values: `approved` | `rejected` | `cancelled`

**Response 200:**
```json
{ "status": "ok" }
```

---

## Error Codes

| HTTP Status | Code | Description |
|-------------|------|-------------|
| 400 | VALIDATION_ERROR | Missing or invalid request fields |
| 401 | UNAUTHORIZED | Missing or invalid JWT token |
| 403 | FORBIDDEN | Insufficient permissions |
| 429 | RATE_LIMITED | Exceeded 100 req/sec per user |
| 500 | SYSTEM_ERROR | Internal server error |
| 503 | SERVICE_UNAVAILABLE | Downstream service unavailable |

---

## Rate Limiting

- 100 requests/second per user
- Burst limit: 200 requests
- Requests exceeding limits receive HTTP 429
