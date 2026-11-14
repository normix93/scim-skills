# SCIM errors (RFC 7644 section 3.12)

```json
{ "schemas": ["urn:ietf:params:scim:api:messages:2.0:Error"],
  "status": "400", "scimType": "invalidFilter", "detail": "Operator 'like' is not supported" }
```

`status` is the HTTP status **as a JSON string**. `scimType` is defined only for 400. `detail` is free text.

## Status codes (Table 8, paraphrased)

| Status | When |
|---|---|
| 307 / 308 | repeat the request at another location (temporary / permanent) |
| 400 | malformed request, schema violation, bad filter or path (add a `scimType`) |
| 401 | missing or invalid credentials |
| 403 | authenticated but not allowed |
| 404 | resource or endpoint does not exist |
| 409 | version conflict, or duplicate resource on create |
| 412 | `If-Match` version is stale |
| 413 | bulk request over `maxOperations` / `maxPayloadSize` |
| 500 | server error |
| 501 | feature not implemented (PATCH, bulk, sort, `/Me` ...) |

Successful codes used by SCIM: 200 (read, query, replace, patch with body), 201 (create), 204 (delete, patch without
body), 304 (not modified with `If-None-Match`).

## scimType values for 400 (Table 9, paraphrased)

| scimType | Use when |
|---|---|
| `invalidFilter` | filter syntax wrong, or attribute/operator combination unsupported (also for PATCH path filters) |
| `tooMany` | the filter would return more than the server is willing to process |
| `uniqueness` | a value must be unique and is taken (create, replace, patch) |
| `mutability` | the change conflicts with readOnly/immutable |
| `invalidSyntax` | body structure invalid (create, replace, search, bulk) |
| `invalidPath` | PATCH `path` malformed |
| `noTarget` | PATCH `path` matched nothing |
| `invalidValue` | value missing or of the wrong type for the attribute or operation |
| `invalidVers` | SCIM version not supported |
| `sensitive` | personal data in the request URI (use POST `/.search`) |

Note: section 3.3 requires a duplicate on create to return **409 Conflict** with `scimType: uniqueness`, while
Table 9 lists scimType values under 400. Both 409 and 400 with `uniqueness` are seen in practice: clients should
handle both, servers should follow section 3.3 (409).

Check an error body: `python3 scripts/scim_check.py error.json`.
