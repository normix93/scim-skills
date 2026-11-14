# Contradictions and wrong examples in RFC 7643 / 7644

Found by running `scripts/scim_check.py` over every JSON example and filter in the two RFCs, and by comparing the
machine-readable schemas (RFC 7643 section 8.7) with the prose. Errata status checked on
<https://www.rfc-editor.org/errata/rfc7643> and <https://www.rfc-editor.org/errata/rfc7644> (2026-11-14): all the
technical errata below are "Reported", none "Verified".

## Schema vs prose (corrected in this skill's data, prose wins)

| Where | Schema in 8.7 says | Prose says | Erratum |
|---|---|---|---|
| Group `displayName` | `required: false` | REQUIRED (RFC 7643 4.2) | 5368 |
| ResourceType `schemaExtensions` | single-valued, required | "a list", OPTIONAL (RFC 7643 6) | — |
| Schema `attributes.referenceTypes` (and in sub-attributes) | single-valued | a list of resource types (RFC 7643 7) | 5607 |

Other reported errata on 8.7 that do not change validation: complex attributes carrying `uniqueness` (6004),
`preferredLanguage`/`locale` wording (6007), missing `schemas` on the schema representations (5999).

## Examples that break the RFC's own rules

| Where | Problem | Erratum |
|---|---|---|
| RFC 7644 3.4.2, filter `(meta.resourceType eq User) or (meta.resourceType eq Group)` | string values not quoted; the ABNF requires JSON strings | none found |
| RFC 7644 3.7.2, `GET /v2/Groups?filter=displayName sw 'Group'` | single-quoted string | none found |
| RFC 7644 3.4.2.2, `emails co "example.com"` and similar | compares a complex attribute directly, while the same section requires a fully qualified sub-attribute | — (servers usually read it as `emails.value`) |
| RFC 7644 3.7.2, bulk response | `"status": {"code": "201"}`, while 3.7.3 and the definition use `"status": "201"` | none found |
| RFC 7644 3.7.3, bulk PATCH operation | `"data": {[ ... ]}` is not valid JSON and lacks `schemas`/`Operations` | 5050 |
| RFC 7644 3.5.2, Figure 8 | `members[...].displayName`: neither 8.7.1 nor the default sub-attributes of RFC 7643 2.4 (`type`, `primary`, `display`, `value`, `$ref`) define `displayName` for members; `display` is the defined name | — |
| RFC 7644 section 4, Figure 9 | `itemsPerPage: 10` on a page with 2 resources | 6010 |
| RFC 7644 3.4.2, partial-attribute list example | resources returned without `schemas` (allowed in practice for `attributes=` results; the checker warns) | — |
| RFC 7643 8.5 / RFC 7644 4 | some implementations use `/ServiceProviderConfigs` (plural); the RFC uses the singular | 4979, 4978 (reported, not accepted) |

## Grammar

- Erratum 4690 (reported by the RFC's editor): the ABNF lets value filters nest (`a[b[c pr]]`); the intent is
  that they should not. The checker warns.
- Erratum 4670: the precedence wording lists logical operators before attribute operators.

`tests/test_scim.py` keeps these as known issues: if a future version of the checker stops detecting them, the
tests fail.
