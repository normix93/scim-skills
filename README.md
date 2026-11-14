# SCIM 2.0 Skills

An [Agent Skill](https://docs.claude.com/en/docs/agents-and-tools/agent-skills/overview) for **SCIM 2.0**
(RFC 7643 schema, RFC 7644 protocol) with a checker that validates what an AI model or a developer writes:
resources, filters, PATCH bodies and paths, list responses, bulk requests and error bodies.

> *"Write a filter for active users whose work email ends with @example.com."*
> *"How do I remove one member from a group with PATCH?"*
> *"Is `{\"status\": 400, \"scimType\": \"invalidAttribute\"}` a valid SCIM error?"*
> *"Our IAM tool provisions fine into app A but app B rejects the requests. Why?"*

Useful whether you build a SCIM server, a client, or map an IAM product (Entra ID, Okta, SailPoint, midPoint ...)
to a SCIM application.

## What's inside

| Path | What |
|---|---|
| `skills/scim/SKILL.md` | how to answer SCIM questions, the rules that prevent most bugs |
| `skills/scim/references/schemas.md` | GENERATED: every attribute of User, Group, Enterprise User and the discovery resources, with type, multi-valued, required, caseExact, mutability, returned, uniqueness, canonical values |
| `references/protocol.md`, `filters.md`, `patch.md`, `errors.md` | the protocol in plain words with the RFC section for each rule, recipes, common mistakes |
| `references/interop.md` | where implementations differ and how clients and servers stay robust |
| `references/rfc-issues.md` | contradictions and wrong examples found in the RFCs themselves |
| `skills/scim/scripts/scim_check.py` | the checker (Python 3, standard library) |

```bash
python3 skills/scim/scripts/scim_check.py body.json --mode request
python3 skills/scim/scripts/scim_check.py --filter 'emails[type eq "work"].value ew "@example.com"' --resource User
python3 skills/scim/scripts/scim_check.py --path 'members[value eq "2819c223"]' --resource Group
```

It parses filters with the RFC's ABNF and explains SQL/JS habits (`==`, `&&`, `LIKE`, single quotes), flags
attributes a resource does not have, `gt`/`lt` on booleans, PATCH paths with array indexes, PATCH operations on
readOnly attributes, wrong JSON types (`"active": "true"`), single vs multi-valued mistakes, two `primary` values,
extension attributes outside their URN object, numeric `status` in errors, 0-based paging, broken bulk requests.
When `schemas` is missing it guesses the message type and keeps checking.

## Tested against the RFCs themselves

`tests/test_scim.py` downloads RFC 7643 and 7644 (they are not committed here) and runs the checker on **every
JSON example (36) and every filter example** in them: all must pass, except the RFC defects listed below, which
must keep being detected. Plus hand-written good and broken fixtures with the exact errors expected.

## Findings: the RFCs contradict themselves

Running the checker over the RFCs turned up (details and errata IDs in `references/rfc-issues.md`):

- RFC 7644 uses **invalid filters in its own examples**: `(meta.resourceType eq User)` (unquoted strings, section
  3.4.2) and `displayName sw 'Group'` (single quotes, section 3.7.2). Neither is in the errata.
- The "full User representation" examples (RFC 7643 8.2, 8.3) return the `password` next to `id` and `meta`,
  although the same RFC defines it as writeOnly and never returned.
- A bulk response example uses `"status": {"code": "201"}` while the definition, and the next example, use
  `"status": "201"`.
- The machine-readable schemas in RFC 7643 section 8.7 disagree with the prose: Group `displayName` is
  `required: false` in the schema but REQUIRED in the text (erratum 5368, still only "Reported" after eight years);
  `schemaExtensions` and `referenceTypes` are single-valued in the schema but lists in the text. The skill's data
  applies the prose, and says so.
- The filter section requires a sub-attribute for complex attributes, then uses `emails co "example.com"` in its
  examples. The checker warns instead of failing, because servers differ.

## Measured

12 questions, same model with and without the skill, no web access, graded blind by a separate agent:
**20/24 (83%) without, 23/24 (96%) with** ([`evals/results.md`](evals/results.md)). SCIM is a public standard that
models know well, so the gap is smaller than for vendor products; the skill mainly adds the precise edge cases
(409 vs 400 for duplicates, 501 for unsupported features, the RFC's own inconsistencies) and, above all, the
checker. The questions were written from the same RFCs the skill uses.

## Install

**Claude Code**

```
/plugin marketplace add normix93/scim-skills
/plugin install scim-skills@scim-skills
```

**Other agents / Claude apps**: copy or zip `skills/scim/`.

## Rebuild

```bash
python3 tools/build_data.py          # downloads the RFCs into .cache/rfc and regenerates the data
python3 -m unittest discover -s tests
```

## License

MIT for everything written here. The generated schema data contains facts extracted from RFC 7643; the filter
ABNF in `references/filters.md` is an RFC 7644 code component under the Simplified BSD License (IETF Trust Legal
Provisions). The RFC text is not redistributed. See `NOTICE`.
