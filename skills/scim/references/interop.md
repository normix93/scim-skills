# Interoperability: where SCIM implementations differ

SCIM leaves much optional and has a few internal contradictions (`rfc-issues.md`). These are the places where a
client that works with one provider breaks with another. The advice is generic: always confirm with the
provider's `/ServiceProviderConfig`, `/ResourceTypes`, `/Schemas` and documentation.

## For clients (an IAM tool provisioning into an app)

| Topic | Be robust by |
|---|---|
| Discovery | reading `/ServiceProviderConfig` first; do not send PATCH, bulk, sort or filters the server says it lacks |
| Matching existing users | filtering on `userName eq "..."` or `externalId eq "..."` (both quoted) before creating; handle 409 `uniqueness` |
| Extension attributes | sending them inside the extension URN object and listing the URN in `schemas`; in filters use the full URN path |
| Group membership | PATCH `add` / `remove` with `members[value eq "..."]`, never `replace` on `members` unless you mean "set exactly" |
| Large groups | fetching groups with `excludedAttributes=members` and paging; servers may cap or omit `members` |
| PATCH response | accepting both 200 with a body and 204 without |
| Booleans and numbers | sending JSON types (`true`, not `"true"`); tolerating servers that return strings |
| Case | treating attribute names as case-insensitive when reading responses |
| Paging | starting at 1, stopping when `startIndex + itemsPerPage > totalResults` or a page is empty; totals may change between pages |
| Errors | reading `status` as a string or a number; handling missing `scimType` |
| Deletes | treating 404 on DELETE as "already gone" when reconciling |

## For servers (an app exposing SCIM)

| Topic | Do |
|---|---|
| Unknown filter operators/attributes | return 400 `invalidFilter`, not 500 |
| `startIndex` < 1, negative `count` | treat as 1 and 0 (RFC 7644 Table 6) |
| PATCH `op` casing, `value` on remove | accept case variations and say what you do with `value` on `remove`; many clients send them |
| Path-less PATCH | support `{"op":"replace","value":{...}}` — common from IAM clients |
| `schemas` on returned resources | always include it, even with `attributes=` |
| Duplicates | 409 with `scimType: uniqueness` (RFC 7644 3.3) |
| ETags | if `etag.supported`, return `ETag` and honour `If-Match` (412 on mismatch) |
| `/Schemas` | describe what you really store (custom attributes, required flags), not a copy of RFC 7643 |
| Personal data in URLs | support `POST /.search` |

## Mapping to IAM products

- An IAM "account" = SCIM `User`; "entitlement"/"group" = SCIM `Group` membership; "account ID" usually = SCIM
  `id`, "native identity"/"name" = `userName`.
- Disable/enable = PATCH `active`. Delete = DELETE (or deactivate, by policy).
- Delta aggregation has no standard SCIM equivalent: filter on `meta.lastModified gt "<last run>"` if the server
  supports filtering on it.
