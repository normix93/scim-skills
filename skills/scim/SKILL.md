---
name: scim
description: SCIM 2.0 (RFC 7643 schema, RFC 7644 protocol) reference and checker — User, Group and Enterprise User attributes with their characteristics (mutability, returned, uniqueness, caseExact), filters (operators, precedence, [ ] value filters, ABNF), PATCH (add/remove/replace, paths), pagination and sorting, bulk, /.search, ETags, discovery endpoints, error responses and scimType. Use when someone builds or debugs a SCIM client or server, writes a filter or PATCH body, maps an IAM connector (Entra ID, Okta, SailPoint, midPoint, ...) to a SCIM app, or asks why a SCIM request fails.
---

# SCIM 2.0

SCIM is two RFCs: **7643** defines the data (schemas, attributes and their characteristics, the User/Group
resources, the Enterprise User extension, discovery resources) and **7644** defines the HTTP protocol (endpoints,
filters, PATCH, bulk, paging, errors). Everything below cites the section to read for the full rule:
`https://www.rfc-editor.org/rfc/rfc7643#section-N` / `rfc7644#section-N`.

## How to answer

1. **Attribute questions** (does User have X, is it multi-valued, can a client write it, is it returned):
   `references/schemas.md` — generated from the RFC's own schema definitions, with the corrections listed in
   `references/rfc-issues.md` applied.
2. **Request/response shape, status codes, paging, ETags, bulk, discovery**: `references/protocol.md`.
3. **Filters**: `references/filters.md`. **PATCH**: `references/patch.md`. **Errors**: `references/errors.md`.
4. **"Works with provider A, fails with B"**: `references/interop.md` — places where the RFC is loose or
   contradicts itself, and what a robust client or server does.
5. **Before handing over any JSON, filter or path, run the checker** (below) and fix every ERROR.
6. Say when something is optional in SCIM (filter, sort, PATCH, bulk, ETags, changePassword are all optional
   features advertised in `/ServiceProviderConfig`): a provider may legitimately return 501 or ignore it.

## Rules that prevent most SCIM bugs

1. Every resource and message carries `schemas` (an array of URNs). Extension attributes live inside an object
   keyed by the extension URN, and that URN must also be in `schemas`.
2. Attribute names and filter operators are **case-insensitive**; attribute *values* follow `caseExact`.
3. `id` and `meta` are set by the server (readOnly). Send your key as `externalId` or `userName`.
4. `password` is writeOnly and never returned.
5. Filter strings are **JSON strings in double quotes**; booleans and null are bare lowercase literals:
   `active eq true`, `userName eq "bjensen"`.
6. Paging is **1-based**: `startIndex=1`. `totalResults` is the count of all matches; `itemsPerPage` is the size
   of this page.
7. PATCH has only `add`, `remove`, `replace`; `remove` always needs a `path`; there are **no array indexes**
   (`emails[0]` is invalid) — select values with a filter: `emails[type eq "work"].value`.
8. Error bodies: `schemas` = `urn:ietf:params:scim:api:messages:2.0:Error`, `status` as a **string** ("400"),
   optional `scimType` (only defined for 400) and `detail`.
9. Content type is `application/scim+json`.

## Checker

`scripts/scim_check.py` (Python 3, standard library):

```bash
python3 scripts/scim_check.py body.json [--mode request|response]
python3 scripts/scim_check.py --filter 'emails[type eq "work"].value co "@example.com"' --resource User
python3 scripts/scim_check.py --path 'members[value eq "2819c223"]' --resource Group
```

It recognizes User, Group (+ Enterprise User), ListResponse, SearchRequest, PatchOp, BulkRequest, BulkResponse,
Error, ServiceProviderConfig, ResourceType and Schema by their `schemas`, and reports: missing required
attributes, wrong JSON types (e.g. `"active": "true"`), single vs multi-valued mistakes, more than one
`primary`, extension attributes at the top level or extension URN missing from `schemas`, bad dateTime/base64,
readOnly attributes sent by a client, writeOnly attributes returned by a server, filter syntax per the ABNF with
hints for SQL/JS habits (`==`, `&&`, `LIKE`, single quotes), filters on unknown attributes, `gt`/`lt` on
booleans, PATCH paths with indexes, PATCH ops on readOnly attributes, paging values, bulk rules, error bodies.
Non-canonical values and unknown sub-attributes are warnings (providers extend them).

## References

| File | Use for |
|---|---|
| `references/schemas.md` | GENERATED: every attribute of User, Group, Enterprise User, ServiceProviderConfig, ResourceType, Schema with type and characteristics |
| `references/protocol.md` | endpoints and methods, create/get/query/replace/delete, `/.search`, attributes/excludedAttributes, sorting, paging, ETags and versions, bulk, `/Me`, discovery |
| `references/filters.md` | operators, precedence, value filters, the ABNF, examples, mistakes |
| `references/patch.md` | add/remove/replace semantics, path forms, recipes (group membership, primary email, extension attributes) |
| `references/errors.md` | status codes and `scimType` values, which to return when |
| `references/interop.md` | where implementations differ and how to be robust |
| `references/rfc-issues.md` | contradictions and wrong examples found in RFC 7643/7644, with errata IDs |
