#!/usr/bin/env python3
"""Generate the SCIM schema data and the schema reference from RFC 7643 section 8.7.

Only facts are extracted (attribute names, types and characteristics, canonical values, reference types):
no descriptive RFC text is copied. The RFCs are downloaded into .cache/rfc by tools/rfctext.py.

Usage: python3 tools/build_data.py
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import rfctext

ROOT = Path(__file__).resolve().parent.parent
SKILL = ROOT / "skills" / "scim"
KEYS = ("type", "multiValued", "required", "caseExact", "mutability", "returned", "uniqueness",
        "canonicalValues", "referenceTypes")


def compact_attr(a: dict) -> dict:
    out = {k: a[k] for k in KEYS if k in a}
    if a.get("subAttributes"):
        out["sub"] = {s["name"]: compact_attr(s) for s in a["subAttributes"]}
    return out


def schema_blocks() -> list[dict]:
    lines = rfctext.load("7643")
    res = rfctext.section(lines, "8.7.1.", "8.7.2.")
    sp = rfctext.section(lines, "8.7.2.", "9.")
    out = []
    for part in (res, sp):
        for _, blob in rfctext.json_blocks("\n".join(part)):
            if isinstance(blob, list) and blob and isinstance(blob[0], dict) and "attributes" in blob[0]:
                out += blob
    return out


def md_table(schema_id: str, attrs: list[dict]) -> list[str]:
    rows = ["| Attribute | Type | Multi | Required | Case exact | Mutability | Returned | Uniqueness | Canonical values / reference types |",
            "|---|---|---|---|---|---|---|---|---|"]

    def add(a: dict, prefix: str = "") -> None:
        extra = ", ".join(a.get("canonicalValues", []) or []) or ", ".join(a.get("referenceTypes", []) or [])
        rows.append(f"| `{prefix}{a['name']}` | {a.get('type', '')} | {'yes' if a.get('multiValued') else ''} | "
                    f"{'yes' if a.get('required') else ''} | {'yes' if a.get('caseExact') else ''} | "
                    f"{a.get('mutability', '')} | {a.get('returned', '')} | {a.get('uniqueness', '')} | {extra} |")
        for s in a.get("subAttributes", []) or []:
            add(s, prefix + a["name"] + ".")

    for a in attrs:
        add(a)
    return rows


# Where the machine-readable schema in section 8.7 contradicts the normative prose of the same RFC, the prose
# wins. Each correction cites the prose section and the reported erratum. See references/rfc-issues.md.
CORRECTIONS = [
    ("urn:ietf:params:scim:schemas:core:2.0:Group", ["displayName"], "required", True,
     "section 4.2 says displayName is REQUIRED; erratum 5368"),
    ("urn:ietf:params:scim:schemas:core:2.0:ResourceType", ["schemaExtensions"], "multiValued", True,
     "section 6: 'A list of URIs of the resource type's schema extensions'"),
    ("urn:ietf:params:scim:schemas:core:2.0:ResourceType", ["schemaExtensions"], "required", False,
     "section 6: schemaExtensions is OPTIONAL"),
    ("urn:ietf:params:scim:schemas:core:2.0:Schema", ["attributes", "referenceTypes"], "multiValued", True,
     "section 7 describes referenceTypes as a list; erratum 5607"),
    ("urn:ietf:params:scim:schemas:core:2.0:Schema", ["attributes", "subAttributes", "referenceTypes"], "multiValued", True,
     "same as above, for sub-attributes; erratum 5607"),
]


def apply_corrections(schemas: list[dict]) -> list[str]:
    done = []
    for urn, path, key, value, why in CORRECTIONS:
        s = next((x for x in schemas if x["id"] == urn), None)
        node = {"subAttributes": s["attributes"]} if s else None
        for name in path:
            node = next((a for a in (node or {}).get("subAttributes", []) or [] if a["name"] == name), None) \
                if node is not None else None
        if node is None:
            raise SystemExit(f"correction target not found: {urn} {path}")
        if node.get(key) != value:
            node[key] = value
            done.append(f"{urn} {'.'.join(path)}: {key} -> {value} ({why})")
    return done


def main() -> None:
    schemas = schema_blocks()
    corrections = apply_corrections(schemas)
    sha = "RFC 7643 (September 2015)"
    data = {
        "_generated": "tools/build_data.py from RFC 7643 section 8.7 (facts only)",
        "_corrections": corrections,
        "schemas": {s["id"]: {"name": s.get("name"), "attributes": {a["name"]: compact_attr(a) for a in s["attributes"]}}
                    for s in schemas},
        # common attributes (RFC 7643 section 3.1) are not part of the schema representations
        "common": {
            "id": {"type": "string", "caseExact": True, "mutability": "readOnly", "returned": "always",
                   "uniqueness": "server"},
            "externalId": {"type": "string", "caseExact": True, "mutability": "readWrite"},
            "meta": {"type": "complex", "mutability": "readOnly", "sub": {
                "resourceType": {"type": "string", "caseExact": True, "mutability": "readOnly"},
                "created": {"type": "dateTime", "mutability": "readOnly"},
                "lastModified": {"type": "dateTime", "mutability": "readOnly"},
                "location": {"type": "reference", "mutability": "readOnly", "referenceTypes": ["uri"]},
                "version": {"type": "string", "caseExact": True, "mutability": "readOnly"}}},
        },
        # default sub-attributes of multi-valued attributes "if not otherwise defined" (RFC 7643 section 2.4)
        "defaultSubAttributes": {
            "type": {"type": "string"}, "primary": {"type": "boolean"},
            "display": {"type": "string", "mutability": "immutable"}, "value": {"type": "string"},
            "$ref": {"type": "reference"}},
        "resourceTypes": {
            "User": {"endpoint": "/Users", "schema": "urn:ietf:params:scim:schemas:core:2.0:User",
                     "extensions": ["urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"]},
            "Group": {"endpoint": "/Groups", "schema": "urn:ietf:params:scim:schemas:core:2.0:Group", "extensions": []},
        },
        "messages": {
            "ListResponse": "urn:ietf:params:scim:api:messages:2.0:ListResponse",
            "SearchRequest": "urn:ietf:params:scim:api:messages:2.0:SearchRequest",
            "PatchOp": "urn:ietf:params:scim:api:messages:2.0:PatchOp",
            "BulkRequest": "urn:ietf:params:scim:api:messages:2.0:BulkRequest",
            "BulkResponse": "urn:ietf:params:scim:api:messages:2.0:BulkResponse",
            "Error": "urn:ietf:params:scim:api:messages:2.0:Error",
        },
        "filterOperators": ["eq", "ne", "co", "sw", "ew", "gt", "lt", "ge", "le", "pr"],
        "scimTypes": ["invalidFilter", "tooMany", "uniqueness", "mutability", "invalidSyntax", "invalidPath",
                      "noTarget", "invalidValue", "invalidVers", "sensitive"],
        "statusCodes": ["307", "308", "400", "401", "403", "404", "409", "412", "413", "500", "501"],
    }
    out = SKILL / "scripts" / "scim_schema.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, indent=1) + "\n", encoding="utf-8")

    md = [f"<!-- GENERATED by tools/build_data.py from {sha}, section 8.7, {dt.date.today().isoformat()}. "
          "Facts only (names, types, characteristics); no RFC prose is reproduced. Do not edit by hand. -->", "",
          "# SCIM 2.0 schemas: attributes and characteristics", "",
          "From the schema representations in RFC 7643 section 8.7 "
          "(<https://www.rfc-editor.org/rfc/rfc7643#section-8.7>). Defaults when a characteristic is not listed: "
          "`required` false, `caseExact` false, `mutability` readWrite, `returned` default, `uniqueness` none, "
          "`multiValued` false (RFC 7643 section 2.2). Common attributes `id`, `externalId`, `meta` (section 3.1) "
          "apply to every resource and are not repeated below.", ""]
    common = [{"name": k, **{kk: vv for kk, vv in v.items() if kk != "sub"},
               "subAttributes": [{"name": sk, **sv} for sk, sv in v.get("sub", {}).items()]}
              for k, v in data["common"].items()]
    md += ["## Common attributes (every resource, RFC 7643 section 3.1)", "",
           "Not part of the schema representations; characteristics as section 3.1 describes them. `id` is "
           "unique across the service provider, assigned by it, never `bulkId`; `externalId` belongs to the client.",
           ""] + md_table("common", common) + [""]
    md += ["## Default sub-attributes of multi-valued attributes (RFC 7643 section 2.4)", "",
           "Apply when a multi-valued complex attribute does not define its own: `type`, `primary` (true at most once), "
           "`display` (immutable), `value`, `$ref`.", ""]
    for s in schemas:
        md += [f"## {s.get('name')} — `{s['id']}`", ""] + md_table(s["id"], s["attributes"]) + [""]
    (SKILL / "references" / "schemas.md").write_text("\n".join(md), encoding="utf-8")
    print(f"{len(schemas)} schemas, {sum(len(s['attributes']) for s in schemas)} top-level attributes")


if __name__ == "__main__":
    main()
