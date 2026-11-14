# SCIM filters (RFC 7644 section 3.4.2.2)

Check any filter: `python3 scripts/scim_check.py --filter '<filter>' [--resource User|Group]`.

## Operators

| Operator | Meaning | Notes |
|---|---|---|
| `eq` / `ne` | equal / not equal | strings compare per the attribute's `caseExact` |
| `co` | contains | substring |
| `sw` / `ew` | starts / ends with | substring at the start / end |
| `pr` | present | non-empty value; takes no value: `title pr` |
| `gt` `ge` `lt` `le` | ordering | strings lexicographic, dateTime chronological, numbers numeric; **not allowed** on boolean and binary (400 `invalidFilter`) |
| `and` `or` `not( )` | logic | `not` must be followed by parentheses |
| `( )` | grouping | |
| `attr[ ... ]` | value filter | expressions inside apply to the same value of a multi-valued complex attribute |

Operators and attribute names are case-insensitive (`userName Eq "john"` works).

**Precedence**: grouping first, then `not` over `and` over `or`. So `a or b and c` means `a or (b and c)`.
(Erratum 4670 points out that the RFC's wording puts logical operators before attribute operators, which reads
oddly; every implementation evaluates `attr op value` first.)

## Values

`compValue` is a JSON literal: `"string"` (double quotes, JSON escapes), number, `true`, `false`, `null` — all
lowercase, no single quotes, no unquoted words.

## Attribute paths

- `userName`, `name.familyName` (sub-attribute), fully qualified
  `urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber` (extension attributes need the URN
  unless the server resolves short names).
- On multi-valued attributes a filter matches if **any** value matches.
- For complex attributes write the sub-attribute: `emails.value co "@example.com"`. The RFC requires it, though
  some of its own examples use `emails co ...` (see `rfc-issues.md`).

## Value filters `[ ]`

`emails[type eq "work" and value co "@example.com"]` — both conditions on the **same** email.
`emails.type eq "work" and emails.value co "@example.com"` — conditions may hold on **different** emails.
Value filters inside value filters (`a[b[c pr]]`) are discouraged by erratum 4690 and rejected by many servers.

## ABNF

Code component of RFC 7644 (Figure 1), reproduced under the Simplified BSD License per the IETF Trust Legal
Provisions; Copyright (c) 2015 IETF Trust and the persons identified as the document authors.

```
FILTER    = attrExp / logExp / valuePath / *1"not" "(" FILTER ")"
valuePath = attrPath "[" valFilter "]"
valFilter = attrExp / logExp / *1"not" "(" valFilter ")"
attrExp   = (attrPath SP "pr") /
            (attrPath SP compareOp SP compValue)
logExp    = FILTER SP ("and" / "or") SP FILTER
compValue = false / null / true / number / string
compareOp = "eq" / "ne" / "co" /
                   "sw" / "ew" /
                   "gt" / "lt" /
                   "ge" / "le"
attrPath  = [URI ":"] ATTRNAME *1subAttr
ATTRNAME  = ALPHA *(nameChar)
nameChar  = "-" / "_" / DIGIT / ALPHA
subAttr   = "." ATTRNAME
```

The PATCH `path` reuses it: `PATH = attrPath / valuePath [subAttr]` (Figure 7).

## Examples (ours)

```
userName eq "bjensen@example.com"
externalId eq "E1001"
active eq true and meta.lastModified gt "2026-01-01T00:00:00Z"
emails[type eq "work" and primary eq true].value ew "@example.com"      ← as a PATCH path; in a GET filter drop ".value"
urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department eq "Sales"
displayName sw "Sales" and not (displayName eq "Sales Archive")
members[value eq "2819c223-7f76-453a-919d-413861904646"]                ← Group has member X (if the server filters members)
```

In a URL, percent-encode the filter: spaces `%20`, quotes `%22` (`?filter=userName%20eq%20%22bjensen%22`).

## Common mistakes

| Wrong | Right |
|---|---|
| `userName = "a"`, `userName == "a"` | `userName eq "a"` |
| `a eq "x" && b eq "y"` | `a eq "x" and b eq "y"` |
| `userName eq 'bjensen'` | `userName eq "bjensen"` |
| `active eq "true"` | `active eq true` |
| `userName like "b%"` | `userName sw "b"` |
| `emails[0].value eq ...` | `emails[type eq "work"]` or `emails.value eq ...` |
| `department eq "Sales"` (extension attribute) | fully qualified URN path |
| `not userName eq "a"` | `not (userName eq "a")` |
