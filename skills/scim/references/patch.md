# SCIM PATCH (RFC 7644 section 3.5.2)

```json
{
  "schemas": ["urn:ietf:params:scim:api:messages:2.0:PatchOp"],
  "Operations": [ { "op": "add" | "remove" | "replace", "path": "...", "value": ... } ]
}
```

- Operations apply in order; the whole request is **atomic** (one failure = nothing changes).
- Only `add`, `remove`, `replace` (no JSON Patch `move`, `copy`, `test`, no array indexes).
- Success: 200 with the resource or 204 without body.
- Mutability applies: readOnly attributes cannot be changed (400 `mutability`); immutable ones can only be added
  when empty.
- Setting `primary: true` on one value makes the server set the others to false.

## Path forms (Figure 7)

| Path | Targets |
|---|---|
| `title` | an attribute |
| `name.familyName` | a sub-attribute |
| `emails[type eq "work"]` | the matching values of a multi-valued attribute |
| `emails[type eq "work"].value` | a sub-attribute of the matching values |
| `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager.value` | an extension attribute (writing it adds the URN to `schemas` implicitly) |

Invalid path → 400 `invalidPath`; a filter that matches nothing → 400 `noTarget` (for remove/replace).

## Semantics

| op | path omitted | path to single-valued | path to multi-valued | path with filter |
|---|---|---|---|---|
| **add** | `value` is an object of attributes merged into the resource | sets it (replaces) | **appends** the values (existing values stay; duplicates are ignored) | — (use replace) |
| **replace** | `value` object: each attribute replaced | sets it | **replaces all** values | replaces the matching values (or their sub-attribute) |
| **remove** | not allowed (`path` required) | clears it | removes all values | removes the matching values |

`add` with a path to a complex single-valued attribute merges sub-attributes (5.2.1 details).

## Recipes

Add a member to a group:
```json
{ "op": "add", "path": "members", "value": [ { "value": "2819c223-7f76-453a-919d-413861904646" } ] }
```

Remove one member (not all!):
```json
{ "op": "remove", "path": "members[value eq \"2819c223-7f76-453a-919d-413861904646\"]" }
```

Change the work email only:
```json
{ "op": "replace", "path": "emails[type eq \"work\"].value", "value": "b.jensen@example.com" }
```

Set the work email whether or not one exists yet: a `replace` with a filter that matches nothing fails with
`noTarget`, so either read the user first, or send `add` on the attribute (which appends a new value):
```json
{ "op": "add", "path": "emails", "value": [ { "type": "work", "value": "b.jensen@example.com" } ] }
```

Deactivate a user:
```json
{ "op": "replace", "path": "active", "value": false }
```

Set the manager (Enterprise User):
```json
{ "op": "replace", "path": "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:manager",
  "value": { "value": "26118915-6090-4610-87e4-49d8ca9f808d" } }
```

Several attributes at once (path omitted):
```json
{ "op": "replace", "value": { "displayName": "Babs Jensen", "title": "Tour Guide" } }
```

## Pitfalls

- `remove` with `path: "members"` and a `value` array: RFC 7644 defines no `value` for remove, so a strict server
  removes **all** members. Use a path filter.
- `replace` on `members` without a filter replaces the **whole** membership.
- Paths like `emails[0]` or `/emails/0` (JSON Patch pointers) are invalid in SCIM.
- `op` values are lowercase in the RFC; clients that send `"Add"` work only with lenient servers.
- Large groups: one PATCH per batch of members keeps payloads under `bulk.maxPayloadSize`-style limits; the RFC does
  not define a limit for PATCH, servers do.

Check: `python3 scripts/scim_check.py patch.json` or `--path '...' --resource Group`.
