---
title: v2 API Envelope Contract
tags: [api, contract]
---

# Envelope Contract

Every `2xx` response from `/api/v2/*` is:

```json
{
  "data": <payload>,
  "meta": { ... },
  "links": { "self": "...", "next": "..." }
}
```

Every non-`2xx` is:

```json
{
  "error": {
    "code": "invalid_date",
    "message": "date must be YYYY-MM-DD",
    "details": [ { "field": "...", "message": "...", "code": "..." } ]
  }
}
```

## Status code semantics

| Code | Use |
|---|---|
| 200 | Read success |
| 201 | Create success — includes `Location:` header |
| 204 | Update/delete success, no body |
| 400 | Malformed request (invalid JSON, bad param shape) |
| 404 | Resource not found |
| 422 | Validation failed (request shape OK, semantics bad) |
| 429 | Rate-limited (not enforced yet) |
| 500 | Server error |

## Pagination

Cursor-based. See [[Pagination Cookbook]].

## Related

- [[Endpoint Reference]]
- [[Error Handling]]
- [[06-Swarm-Reports/OpenAPI Audit]]
- Home: [[INDEX]]
