# SCIM protocol (RFC 7644)

Summarized in our own words; read the cited sections for the normative text.
Base URL examples use `https://example.com/scim/v2`.

## Endpoints and methods (section 3.2)

| Endpoint | Methods | Notes |
|---|---|---|
| `/Users`, `/Groups` (and any resource type's `endpoint`) | GET (query), POST (create) | `/.search` under them accepts POST queries |
| `/Users/{id}`, `/Groups/{id}` | GET, PUT (replace), PATCH (modify), DELETE | |
| `/Me` | as for the authenticated user's resource | optional alias (3.11); 501 if unsupported |
| `/ServiceProviderConfig` | GET | which optional features the server supports (section 4) |
| `/ResourceTypes`, `/ResourceTypes/{name}` | GET | resource types, endpoints, schema extensions |
| `/Schemas`, `/Schemas/{urn}` | GET | attribute definitions the server really uses |
| `/Bulk` | POST | optional (3.7) |
| `/.search` (at the root) | POST | query across resource types |

Media type: `application/scim+json` (section 8.1). A URL version prefix such as `/v2` is a convention, not a
requirement (3.13).

## Create — POST (3.3)

- Body: the resource with `schemas`; no `id`, no `meta` (server-assigned).
- Success: **201 Created**, the full created resource, `Location` header = `meta.location`, `ETag` if versioning.
- Duplicate (e.g. `userName` with `uniqueness: server`): **409** with `scimType: uniqueness`.

## Read and query — GET (3.4)

- `GET /Users/{id}` → 200 + resource, 404 if unknown.
- `GET /Users?filter=...&startIndex=1&count=100&sortBy=userName&sortOrder=ascending&attributes=userName,emails`
  → 200 + `ListResponse` (`totalResults`, `Resources`, `startIndex`, `itemsPerPage`).
- No matches is **200** with `totalResults: 0`, not 404.
- `filter` and `sortBy` are optional features; a server that does not support them answers 501 or ignores them,
  as `/ServiceProviderConfig` advertises (`filter.supported`, `sort.supported`).
- Too many results: 400 `scimType: tooMany` (server's choice).
- `attributes` returns only the listed attributes plus those with `returned: always` (such as `id`);
  `excludedAttributes` removes attributes with `returned: default` (3.4.2.5, 3.9). Attributes with `returned: never`
  (`password`) are never returned, even when listed in `attributes`.
- Personal data should not go in URLs: use `POST /.search` for filters with personal values (7.5.2, scimType
  `sensitive`).

### Paging (3.4.2.4)

- `startIndex` is **1-based** (values < 1 are treated as 1); `count` is the page size the client wants (0 = return
  only `totalResults`; negative values are treated as 0); the server may return fewer, never more.
- `totalResults` = all matches; `itemsPerPage` = resources in this response.
- Index paging is not a snapshot: results may shift between pages if data changes.

### Sorting (3.4.2.3)

`sortBy` = one attribute path; `sortOrder` = `ascending` (default) or `descending`. Multi-valued attributes sort by
their primary value or as the server defines.

### POST /.search (3.4.3)

Body `{"schemas": ["urn:ietf:params:scim:api:messages:2.0:SearchRequest"], "filter": "...", "attributes": [...],
"startIndex": 1, "count": 100}` → 200 + ListResponse. `attributes`/`excludedAttributes` are arrays here (comma lists
in GET).

## Replace — PUT (3.5.1)

- Replaces the whole resource as the client sends it; attributes the client omits may be cleared (readWrite) —
  servers keep readOnly and may keep immutable values.
- Sending a different value for an immutable attribute: 400 `scimType: mutability`.
- Success: 200 + resource.

## Modify — PATCH (3.5.2)

See `patch.md`. Success: 200 + resource, or 204 No Content (200 is mandatory if the request had `attributes`).
PATCH is atomic: if one operation fails, nothing is applied.

## Delete (3.6)

`DELETE /Users/{id}` → **204 No Content**; later GETs return 404.

## Versions and ETags (3.14)

If `/ServiceProviderConfig` says `etag.supported: true`, resources carry `meta.version` (a weak ETag such as
`W/"3694e05e9dff591"`) and responses carry `ETag`. Clients send `If-Match` on PUT/PATCH/DELETE: a stale version
returns **412 Precondition Failed**. `If-None-Match` on GET returns **304** when unchanged.

## Bulk (3.7)

- `POST /Bulk` with `BulkRequest`: `Operations` each with `method` (POST/PUT/PATCH/DELETE), `path`, `bulkId`
  (required for POST), `version` (optional), `data` (for POST/PUT/PATCH); optional `failOnErrors` (stop after N
  errors).
- Later operations can reference resources created earlier in the same request as `bulkId:<id>`; servers must
  resolve circular references or fail them (3.7.1, 3.7.2).
- Example: create a user and a group containing it in one request.

```json
{ "schemas": ["urn:ietf:params:scim:api:messages:2.0:BulkRequest"],
  "failOnErrors": 1,
  "Operations": [
    { "method": "POST", "path": "/Users", "bulkId": "u1",
      "data": { "schemas": ["urn:ietf:params:scim:schemas:core:2.0:User"], "userName": "alice@example.com" } },
    { "method": "POST", "path": "/Groups", "bulkId": "g1",
      "data": { "schemas": ["urn:ietf:params:scim:schemas:core:2.0:Group"], "displayName": "Tour Guides",
                "members": [ { "value": "bulkId:u1" } ] } },
    { "method": "PATCH", "path": "/Users/bulkId:u1",
      "data": { "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
                "Operations": [ { "op": "replace", "path": "active", "value": true } ] } } ] }
```

  `bulkId:<id>` can appear in `data` values and in `path` (3.7.2).
- Response: `BulkResponse` with one result per operation: `method`, `bulkId`, `location`, `version`, `status`
  (HTTP status as a string), `response` (error body when it failed).
- Limits come from `/ServiceProviderConfig` (`bulk.maxOperations`, `bulk.maxPayloadSize`); exceeding them returns
  413.

## Discovery (RFC 7644 section 4, RFC 7643 sections 5–7)

| Resource | Tells you |
|---|---|
| `ServiceProviderConfig` | `patch`, `bulk` (+limits), `filter` (+`maxResults`), `changePassword`, `sort`, `etag` support; `authenticationSchemes` |
| `ResourceType` | `name`, `endpoint`, base `schema`, `schemaExtensions` (each with `required`) |
| `Schema` | the attribute definitions the server actually implements (may differ from RFC 7643) |

Read them before assuming a feature: they are how a client adapts to a provider.

## Authentication (section 2)

SCIM does not define authentication; it uses HTTP (OAuth 2.0 bearer tokens, Basic, mutual TLS ...). The schemes a
server accepts are listed in `ServiceProviderConfig.authenticationSchemes`. 401 = missing/invalid credentials,
403 = authenticated but not allowed.
