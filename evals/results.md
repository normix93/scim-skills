# Results

12 questions, 0–2 points each (max 24). Blind grading by a separate agent.

| Group | Questions | Without skills | With skills |
|---|---|---|---|
| scim | 12 | 20/24 | 23/24 |
| **Total** | 12 | **20/24 (83%)** | **23/24 (96%)** |

## Per question

| Question | Without | With | Grader note (without) | Grader note (with) |
|---|---|---|---|---|
| scim-01 | 2 | 2 | Correct value filter with unquoted true and quoted strings; different-emails caveat explained. | Value filter, active eq true, quoting rules, and different-emails caveat all present. |
| scim-02 | 2 | 2 | Filtered remove path, PatchOp schema, warns unfiltered members path removes all. | Filtered remove path, PatchOp schema, warns path members removes all (value undefined). |
| scim-03 | 2 | 2 | startIndex/count, 1-based, totalResults/itemsPerPage, count=0 behavior all correct. | All paging facts correct, including count=0 and 1-based startIndex. |
| scim-04 | 2 | 2 | String status, Error schema, invalidAttribute undefined with valid scimType list. | String status, invalidAttribute undefined with full valid list, Error schema required. |
| scim-05 | 2 | 2 | Enterprise extension, URN in schemas, fully qualified filter path. | Enterprise extension, URN in schemas, fully qualified filter path. |
| scim-06 | 1 | 2 | 409 uniqueness correct but omits Table 9 / 400 note. | 409 uniqueness per 3.3, notes Table 9 400 listing and client handling. |
| scim-07 | 2 | 2 | id/meta readOnly server-assigned, externalId client-set, password writeOnly returned never. | id/meta readOnly, use externalId, password writeOnly returned never. |
| scim-08 | 1 | 2 | Boolean part correct; claims short form applies to value, omits 3.4.2.2 sub-attribute requirement. | 400 invalidFilter for ordering on booleans; sub-attribute requirement and RFC example inconsistency noted. |
| scim-09 | 1 | 2 | ServiceProviderConfig and flags correct; no mention of 501 for unsupported features. | ServiceProviderConfig, all flags and limits, and 501 for unsupported features. |
| scim-10 | 2 | 2 | replace with emails[type eq "work"].value, PatchOp schema and Operations. | replace with emails[type eq "work"].value, PatchOp schema and Operations. |
| scim-11 | 2 | 2 | Prose REQUIRED vs 8.7.1 required false, noted as known discrepancy. | Prose REQUIRED vs 8.7 schema required false, erratum 5368 cited. |
| scim-12 | 1 | 1 | bulkId and bulkId:<id> reference correct; response status as string not stated. | bulkId and references correct; response per-operation string status missing. |
