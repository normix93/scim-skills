#!/usr/bin/env python3
"""Check SCIM 2.0 payloads, filters and PATCH paths against RFC 7643 / RFC 7644. Standard library only.

Usage:
  scim_check.py FILE.json [...] [--mode request|response]   auto-detects resources and API messages
  scim_check.py --filter 'emails[type eq "work"].value co "@example.com"' [--resource User]
  scim_check.py --path 'members[value eq "2819c223"].display' [--resource Group]

Exit code 0 = no errors, 1 = errors, 2 = unreadable input.

Recognized by their "schemas" value: User, Group (+ Enterprise User extension), ListResponse, SearchRequest,
PatchOp, BulkRequest, BulkResponse, Error, ServiceProviderConfig, ResourceType, Schema.
Schema facts come from scim_schema.json, generated from RFC 7643 section 8.7.
"""
from __future__ import annotations

import base64
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(HERE, "scim_schema.json"), encoding="utf-8") as fh:
    DATA = json.load(fh)

MSG = DATA["messages"]
URN_USER = "urn:ietf:params:scim:schemas:core:2.0:User"
URN_GROUP = "urn:ietf:params:scim:schemas:core:2.0:Group"
URN_ENT = "urn:ietf:params:scim:schemas:extension:enterprise:2.0:User"
URN_SPC = "urn:ietf:params:scim:schemas:core:2.0:ServiceProviderConfig"
URN_RT = "urn:ietf:params:scim:schemas:core:2.0:ResourceType"
URN_SCHEMA = "urn:ietf:params:scim:schemas:core:2.0:Schema"
OPS = set(DATA["filterOperators"])
DATETIME = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?(Z|[+-]\d{2}:\d{2})$")


class Report:
    def __init__(self):
        self.errors: list[str] = []
        self.warnings: list[str] = []

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    def warn(self, where: str, msg: str) -> None:
        self.warnings.append(f"{where}: {msg}")


# --------------------------------------------------------------------------- schema helpers

def schema_attrs(urn: str) -> dict:
    return (DATA["schemas"].get(urn) or {}).get("attributes", {})


def find_ci(d: dict, name: str):
    """Case-insensitive lookup (SCIM attribute names are case-insensitive). Returns (real_name, value)."""
    if name in d:
        return name, d[name]
    low = name.lower()
    for k, v in d.items():
        if k.lower() == low:
            return k, v
    return None, None


def subs_of(a: dict) -> dict:
    """Defined sub-attributes, plus the RFC 7643 2.4 defaults for multi-valued complex attributes."""
    subs = dict(a.get("sub", {}))
    if a.get("multiValued") and a.get("type") == "complex":
        for k, v in DATA.get("defaultSubAttributes", {}).items():
            subs.setdefault(k, v)
    return subs


def resource_attrs(resource: str | None) -> tuple[dict, list[str]]:
    """Core + common attributes of a resource type, and its extension URNs."""
    if not resource:
        return {}, []
    rt = DATA["resourceTypes"].get(resource)
    if not rt:
        return {}, []
    attrs = dict(DATA["common"])
    attrs.update(schema_attrs(rt["schema"]))
    return attrs, rt["extensions"]


def resolve_attr(path: dict, resource: str | None):
    """Definition of an attrPath {'uri','attr','sub'} for a resource type, or (None, reason)."""
    attrs, exts = resource_attrs(resource)
    if not attrs:
        return None, None
    uri = path.get("uri")
    pool = attrs
    if uri:
        if uri.lower() == DATA["resourceTypes"][resource]["schema"].lower():
            pool = attrs
        elif uri.lower() in [e.lower() for e in exts]:
            pool = schema_attrs(next(e for e in exts if e.lower() == uri.lower()))
        else:
            return None, f"schema URI '{uri}' is not a schema of {resource}"
    name, a = find_ci(pool, path["attr"])
    if a is None:
        return None, f"'{path['attr']}' is not an attribute of {resource}"
    if path.get("sub"):
        sname, s = find_ci(subs_of(a), path["sub"])
        if s is None:
            return None, f"~'{name}.{path['sub']}' is not a defined sub-attribute of {resource}"
        return s, None
    return a, None


def report_why(rep: Report, where: str, why: str) -> None:
    """Unknown attributes are errors; unknown sub-attributes are warnings (servers often add their own)."""
    if why.startswith("~"):
        rep.warn(where, why[1:])
    else:
        rep.err(where, why)


# --------------------------------------------------------------------------- filter parser (RFC 7644 3.4.2.2)

TOKEN = re.compile(r"""
    (?P<ws>\s+)
  | (?P<lparen>\() | (?P<rparen>\)) | (?P<lbrack>\[) | (?P<rbrack>\])
  | (?P<string>"(?:[^"\\]|\\.)*")
  | (?P<number>-?(?:0|[1-9]\d*)(?:\.\d+)?(?:[eE][+-]?\d+)?(?![\w:.]))
  | (?P<path>(?:urn:[A-Za-z0-9:._\-]+:)?[A-Za-z][\w\-$]*(?:\.[A-Za-z][\w\-$]*)?)
  | (?P<bad>\S)
""", re.X)


class FilterError(Exception):
    pass


def tokenize(s: str) -> list[tuple[str, str, int]]:
    toks = []
    for m in TOKEN.finditer(s):
        kind = m.lastgroup
        if kind == "ws":
            continue
        toks.append((kind, m.group(), m.start()))
    return toks


def split_path(text: str) -> dict:
    uri = None
    rest = text
    if text.lower().startswith("urn:"):
        uri, rest = text.rsplit(":", 1)
    attr, _, sub = rest.partition(".")
    return {"uri": uri, "attr": attr, "sub": sub or None, "text": text}


class Parser:
    """FILTER := or ; or := and ('or' and)* ; and := unary ('and' unary)* ;
    unary := 'not' '(' FILTER ')' | '(' FILTER ')' | attrPath '[' FILTER ']' ('.' sub)? | attrExp"""

    def __init__(self, text: str, in_brackets: bool = False):
        self.text = text
        self.toks = tokenize(text)
        self.i = 0
        for kind, val, pos in self.toks:
            if kind == "bad":
                hint = {"=": " (use eq)", "&": " (use and)", "|": " (use or)", "!": " (use ne or not(...))",
                        "'": " (strings need double quotes)", "<": " (use lt/le)", ">": " (use gt/ge)"}.get(val, "")
                raise FilterError(f"unexpected character '{val}' at position {pos}{hint}")

    def peek(self, k: int = 0):
        j = self.i + k
        return self.toks[j] if j < len(self.toks) else (None, None, len(self.text))

    def next(self):
        t = self.peek()
        self.i += 1
        return t

    def word(self, k: int = 0) -> str:
        kind, val, _ = self.peek(k)
        return val.lower() if kind == "path" and val else ""

    def parse(self):
        node = self.parse_or()
        kind, val, pos = self.peek()
        if kind is not None:
            raise FilterError(f"unexpected '{val}' at position {pos}")
        return node

    def parse_or(self):
        left = self.parse_and()
        while self.word() == "or":
            self.next()
            left = ("or", left, self.parse_and())
        return left

    def parse_and(self):
        left = self.parse_unary()
        while self.word() == "and":
            self.next()
            left = ("and", left, self.parse_unary())
        return left

    def parse_unary(self):
        kind, val, pos = self.peek()
        if kind is None:
            raise FilterError("filter ends too early: expected an expression")
        if self.word() == "not" and self.peek(1)[0] == "lparen":
            self.next()
            self.next()
            inner = self.parse_or()
            self.expect("rparen", ")")
            return ("not", inner)
        if kind == "lparen":
            self.next()
            inner = self.parse_or()
            self.expect("rparen", ")")
            return inner
        if kind != "path":
            raise FilterError(f"expected an attribute name at position {pos}, found '{val}'")
        if self.word() in ("and", "or"):
            raise FilterError(f"'{val}' at position {pos} needs an expression on its left")
        self.next()
        path = split_path(val)
        if self.peek()[0] == "lbrack":
            self.next()
            inner = self.parse_or()
            self.expect("rbrack", "]")
            node = ("valuePath", path, inner)
            return node
        opk, op, opos = self.next()
        if opk != "path" or op.lower() not in OPS:
            sug = {"==": "eq", "=": "eq", "!=": "ne", "like": "co or sw", "contains": "co", "startswith": "sw",
                   "endswith": "ew", "in": "several eq joined with or", "is": "pr or eq null"}.get((op or "").lower(), "")
            raise FilterError(f"'{op}' at position {opos} is not a SCIM operator (eq ne co sw ew gt lt ge le pr)"
                              + (f"; use {sug}" if sug else ""))
        op = op.lower()
        if op == "pr":
            return ("attrExp", path, "pr", None)
        vk, vv, vpos = self.next()
        if vk == "string":
            value = json.loads(vv)
        elif vk == "number":
            value = json.loads(vv)
        elif vk == "path" and vv.lower() in ("true", "false", "null"):
            if vv not in ("true", "false", "null"):
                raise FilterError(f"'{vv}' must be lowercase JSON literal ({vv.lower()})")
            value = json.loads(vv)
        elif vk is None:
            raise FilterError(f"operator '{op}' needs a value")
        else:
            raise FilterError(f"value '{vv}' at position {vpos} must be a JSON string in double quotes, a number, "
                              "true, false or null")
        return ("attrExp", path, op, value)

    def expect(self, kind: str, char: str):
        k, v, pos = self.next()
        if k != kind:
            raise FilterError(f"expected '{char}' at position {pos}" + (f", found '{v}'" if v else " (unbalanced)"))


def nested_value_paths(node, inside: bool = False) -> bool:
    if node[0] in ("and", "or"):
        return nested_value_paths(node[1], inside) or nested_value_paths(node[2], inside)
    if node[0] == "not":
        return nested_value_paths(node[1], inside)
    if node[0] == "valuePath":
        return inside or nested_value_paths(node[2], True)
    return False


def check_filter(text: str, where: str, rep: Report, resource: str | None = None) -> object:
    try:
        tree = Parser(text).parse()
    except FilterError as e:
        rep.err(where, f"invalid filter (scimType invalidFilter): {e}")
        return None
    if resource:
        semantic(tree, rep, where, resource, None)
    elif nested_value_paths(tree):
        rep.warn(where, "nested [ ] filters: erratum 4690 to RFC 7644 (by its editor) says valuePath filters should "
                        "not nest; many servers reject it")
    return tree


def semantic(node, rep: Report, where: str, resource: str, parent: dict | None) -> None:
    kind = node[0]
    if kind in ("and", "or"):
        semantic(node[1], rep, where, resource, parent)
        semantic(node[2], rep, where, resource, parent)
    elif kind == "not":
        semantic(node[1], rep, where, resource, parent)
    elif kind == "valuePath":
        path = node[1]
        a, why = resolve_attr(path, resource)
        if why:
            report_why(rep, where, why)
            return
        if a is not None:
            if a.get("type") != "complex" or not a.get("multiValued"):
                rep.warn(where, f"'{path['text']}[...]' filters values of a multi-valued complex attribute; "
                                f"'{path['attr']}' is {'multi-valued ' if a.get('multiValued') else ''}{a.get('type')}")
            if path.get("sub"):
                rep.err(where, f"'{path['text']}[...]': the attribute before '[' cannot have a sub-attribute")
        if parent is not None:
            rep.warn(where, f"nested filter '{parent['text']}[... {path['text']}[...]]': erratum 4690 to RFC 7644 "
                            "(by its editor) says valuePath filters should not nest; many servers reject it")
        semantic(node[2], rep, where, resource, path)
    elif kind == "attrExp":
        path, op, value = node[1], node[2], node[3]
        full = path
        if parent is not None:  # inside [ ]: names are sub-attributes of the parent
            full = {"uri": parent.get("uri"), "attr": parent["attr"], "sub": path["attr"],
                    "text": f"{parent['text']}[{path['text']}]"}
            if path.get("sub") or path.get("uri"):
                rep.err(where, f"inside '{parent['text']}[...]' use plain sub-attribute names, not '{path['text']}'")
                return
        a, why = resolve_attr(full, resource)
        if why:
            report_why(rep, where, why)
            return
        if a is None:
            return
        t = a.get("type")
        if t == "complex" and not full.get("sub") and op != "pr":
            if a.get("multiValued") and "value" in a.get("sub", {}):
                rep.warn(where, f"'{path['text']}' is complex: RFC 7644 3.4.2.2 requires a sub-attribute "
                                f"({path['text']}.value), although its own examples use the short form; "
                                "servers differ, so write the sub-attribute")
            else:
                rep.err(where, f"'{path['text']}' is complex: compare a sub-attribute or use a [ ] filter")
        if op in ("gt", "ge", "lt", "le") and t in ("boolean", "binary"):
            rep.err(where, f"'{op}' on {t} attribute '{path['text']}' must fail with invalidFilter (RFC 7644 3.4.2.2)")
        if op in ("co", "sw", "ew") and t not in ("string", "reference", "complex"):
            rep.warn(where, f"'{op}' on {t} attribute '{path['text']}' is unusual: substring operators apply to strings")
        if op != "pr" and value is not None and t:
            ok = {"boolean": isinstance(value, bool), "integer": isinstance(value, int) and not isinstance(value, bool),
                  "decimal": isinstance(value, (int, float)) and not isinstance(value, bool),
                  "string": isinstance(value, str), "reference": isinstance(value, str),
                  "dateTime": isinstance(value, str), "binary": isinstance(value, str)}.get(t, True)
            if not ok:
                rep.warn(where, f"'{path['text']}' is {t} but the filter compares it with {json.dumps(value)}")
            if t == "dateTime" and isinstance(value, str) and not DATETIME.match(value):
                rep.warn(where, f"'{value}' is not an xsd:dateTime such as 2011-05-13T04:42:34Z")
            if t == "boolean" and isinstance(value, str) and value.lower() in ("true", "false"):
                rep.err(where, f"'{path['text']}' is boolean: write {value.lower()} without quotes")


def check_path(text: str, where: str, rep: Report, resource: str | None = None) -> None:
    """PATCH path = attrPath / valuePath [subAttr]  (RFC 7644 Figure 7)."""
    m = re.match(r"^\s*((?:urn:[A-Za-z0-9:._\-]+:)?[A-Za-z][\w\-$]*(?:\.[A-Za-z][\w\-$]*)?)\s*(?:\[(.*)\](?:\.([A-Za-z][\w\-$]*))?)?\s*$",
                 text, re.S)
    if not m:
        rep.err(where, f"invalid path (scimType invalidPath): '{text}' — expected attr, attr.sub, attr[filter] or "
                       "attr[filter].sub; SCIM has no array indexes like emails[0]")
        return
    base, flt, sub = m.group(1), m.group(2), m.group(3)
    path = split_path(base)
    if flt is not None:
        if path.get("sub"):
            rep.err(where, f"invalid path: '{base}[...]' — the filtered attribute cannot have a sub-attribute before '['")
            return
        if re.fullmatch(r"\s*\d+\s*", flt):
            rep.err(where, f"invalid path: '{text}' — SCIM does not support array indexes; filter on a value instead")
            return
        sub_rep = Report()
        tree = check_filter(flt, where + " [filter]", sub_rep, None)
        rep.errors += sub_rep.errors
        if tree is not None and resource:
            semantic(("valuePath", path, tree), rep, where, resource, None)
        if sub and resource:
            a, why = resolve_attr({"uri": path["uri"], "attr": path["attr"], "sub": sub, "text": text}, resource)
            if why:
                report_why(rep, where, why)
    elif resource:
        a, why = resolve_attr(path, resource)
        if why:
            report_why(rep, where, why)


# --------------------------------------------------------------------------- resources

def check_value(a: dict, value, where: str, rep: Report, mode: str, single: bool = False) -> None:
    if a.get("multiValued") and not single:
        if not isinstance(value, list):
            rep.err(where, "multi-valued attribute must be a JSON array")
            return
        primaries = 0
        for i, v in enumerate(value):
            check_value(a, v, f"{where}[{i}]", rep, mode, single=True)
            if isinstance(v, dict):
                _, p = find_ci(v, "primary")
                primaries += p is True
        if primaries > 1:
            rep.err(where, "more than one value has primary=true (RFC 7643 2.4)")
        return
    if isinstance(value, list) and not a.get("multiValued"):
        rep.err(where, "single-valued attribute must not be an array")
        return
    t = a.get("type")
    if value is None:
        return
    if t == "complex":
        if not isinstance(value, dict):
            rep.err(where, "complex attribute must be a JSON object")
            return
        subs = subs_of(a)
        for k, v in value.items():
            real, s = find_ci(subs, k)
            if s is None:
                if k != "$ref" or "$ref" not in subs:
                    rep.warn(f"{where}.{k}", "not a defined sub-attribute")
                continue
            if real != k:
                rep.warn(f"{where}.{k}", f"defined as '{real}' (names are case-insensitive, but match the schema)")
            check_value(s, v, f"{where}.{k}", rep, mode)
            check_mutability(s, f"{where}.{k}", rep, mode)
        if a.get("multiValued"):
            # canonical values of the "type" sub-attribute are open lists: warn only
            _, tv = find_ci(value, "type")
            canon = (subs.get("type") or {}).get("canonicalValues")
            if canon and isinstance(tv, str) and tv not in canon:
                rep.warn(f"{where}.type", f"'{tv}' is not a canonical value ({', '.join(canon)}); allowed but less interoperable")
        return
    ok = {
        "string": isinstance(value, str),
        "boolean": isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "decimal": isinstance(value, (int, float)) and not isinstance(value, bool),
        "dateTime": isinstance(value, str),
        "binary": isinstance(value, str),
        "reference": isinstance(value, str),
    }.get(t, True)
    if not ok:
        hint = ""
        if t == "boolean" and isinstance(value, str) and value.lower() in ("true", "false"):
            hint = f" (use {value.lower()} without quotes)"
        rep.err(where, f"expected {t}, got {type(value).__name__} {json.dumps(value)[:40]}{hint}")
        return
    if t == "dateTime" and not DATETIME.match(value):
        rep.err(where, f"'{value}' is not an xsd:dateTime (e.g. 2011-08-01T18:29:49.793Z)")
    if t == "binary":
        try:
            base64.b64decode(value, validate=True)
        except Exception:
            rep.err(where, "binary values must be base64")
    canon = a.get("canonicalValues")
    if canon and t == "string" and value not in canon:
        rep.warn(where, f"'{value}' is not a canonical value ({', '.join(canon)})")


def check_mutability(a: dict, where: str, rep: Report, mode: str) -> None:
    mut = a.get("mutability", "readWrite")
    ret = a.get("returned", "default")
    if mode == "request" and mut == "readOnly":
        rep.warn(where, "readOnly: a server ignores it in create/replace requests")
    if mode == "response" and (mut == "writeOnly" or ret == "never"):
        rep.err(where, "must never be returned (writeOnly / returned never), e.g. password")


def check_resource(obj: dict, where: str, rep: Report, mode: str, urn: str) -> None:
    resource = "User" if urn == URN_USER else "Group"
    schemas = obj.get("schemas") or []
    attrs = schema_attrs(urn)
    common = DATA["common"]
    for name, a in attrs.items():
        if a.get("required") and find_ci(obj, name)[1] in (None, "", []):
            rep.err(where, f"required attribute '{name}' is missing")
    if mode == "response":
        if not obj.get("id"):
            rep.err(where, "'id' is required in responses")
        meta = obj.get("meta")
        if isinstance(meta, dict) and meta.get("resourceType") not in (None, resource):
            rep.warn(f"{where}.meta.resourceType", f"'{meta.get('resourceType')}' but schemas say {resource}")
    exts = DATA["resourceTypes"][resource]["extensions"]
    for k, v in obj.items():
        w = f"{where}.{k}"
        if k == "schemas":
            continue
        if k.lower().startswith("urn:"):
            ext = next((e for e in exts if e.lower() == k.lower()), None)
            if ext is None:
                if k.lower() in (s.lower() for s in DATA["schemas"]):
                    rep.err(w, f"schema '{k}' is not an extension of {resource}")
                else:
                    rep.warn(w, "custom extension: not checked")
                if k not in schemas:
                    rep.err(w, f"extension URN must also be listed in 'schemas'")
                continue
            if k not in schemas:
                rep.err(w, "extension URN must also be listed in 'schemas' (RFC 7643 3.3)")
            if not isinstance(v, dict):
                rep.err(w, "extension attributes go in a JSON object")
                continue
            ext_attrs = schema_attrs(ext)
            for ek, ev in v.items():
                real, a = find_ci(ext_attrs, ek)
                if a is None:
                    rep.warn(f"{w}.{ek}", "not an attribute of this extension")
                    continue
                check_value(a, ev, f"{w}.{ek}", rep, mode)
                check_mutability(a, f"{w}.{ek}", rep, mode)
            continue
        real, a = find_ci(attrs, k)
        if a is None:
            real, a = find_ci(common, k)
        if a is None:
            other = [e for e in exts if find_ci(schema_attrs(e), k)[1] is not None]
            if other:
                rep.err(w, f"belongs to extension {other[0]}: put it inside \"{other[0]}\": {{...}}")
            else:
                rep.warn(w, f"not an attribute of {resource}")
            continue
        if real != k:
            rep.warn(w, f"defined as '{real}' (names are case-insensitive, but match the schema)")
        check_value(a, v, w, rep, mode)
        check_mutability(a, w, rep, mode)


# --------------------------------------------------------------------------- API messages

def check_list_response(obj: dict, where: str, rep: Report) -> None:
    tr = obj.get("totalResults")
    if not isinstance(tr, int) or isinstance(tr, bool):
        rep.err(where, "'totalResults' (integer) is required")
    res = obj.get("Resources")
    if res is None and find_ci(obj, "Resources")[1] is not None:
        rep.warn(where, "use 'Resources' (capital R) as in RFC 7644")
        res = find_ci(obj, "Resources")[1]
    if res is not None and not isinstance(res, list):
        rep.err(where, "'Resources' must be an array")
        res = []
    si = obj.get("startIndex")
    if si is not None and (not isinstance(si, int) or si < 1):
        rep.err(where, "'startIndex' is 1-based: an integer >= 1")
    ipp = obj.get("itemsPerPage")
    if ipp is not None and (not isinstance(ipp, int) or ipp < 0):
        rep.err(where, "'itemsPerPage' must be a non-negative integer")
    if isinstance(ipp, int) and isinstance(res, list) and ipp != len(res):
        rep.warn(where, f"itemsPerPage is {ipp} but this page has {len(res)} resources: itemsPerPage counts the "
                        "results in this response (RFC 7644 3.4.2.4; erratum 6010)")
    if isinstance(tr, int) and res and tr == 0:
        rep.err(where, "totalResults is 0 but Resources is not empty")
    if res and ("startIndex" not in obj or "itemsPerPage" not in obj):
        rep.warn(where, "paged results should carry startIndex and itemsPerPage")
    for i, r in enumerate(res or []):
        if isinstance(r, dict):
            if "schemas" not in r:
                rep.warn(f"{where}.Resources[{i}]", "no 'schemas': acceptable for a partial result requested with "
                                                     "'attributes', but clients may rely on it")
                continue
            check_object(r, f"{where}.Resources[{i}]", rep, "response")


def check_error(obj: dict, where: str, rep: Report) -> None:
    st = obj.get("status")
    if st is None:
        rep.err(where, "'status' is required")
    elif not isinstance(st, str):
        rep.err(where, f"'status' must be a JSON string (\"{st}\"), not a number (RFC 7644 3.12)")
    elif st not in DATA["statusCodes"]:
        rep.warn(where, f"status {st} is not one of the codes RFC 7644 Table 8 describes")
    t = obj.get("scimType")
    if t is not None:
        if t not in DATA["scimTypes"]:
            rep.err(where, f"scimType '{t}' is not defined; one of {', '.join(DATA['scimTypes'])}")
        if str(st) != "400" and not (str(st) == "409" and t == "uniqueness"):
            rep.warn(where, "scimType values are defined for status 400 (and 409 uniqueness, section 3.3)")


def check_search(obj: dict, where: str, rep: Report) -> None:
    for k in ("attributes", "excludedAttributes"):
        if k in obj and not isinstance(obj[k], list):
            rep.err(where, f"'{k}' must be an array of attribute names in a SearchRequest")
    if "attributes" in obj and "excludedAttributes" in obj:
        rep.warn(where, "use either attributes or excludedAttributes, not both")
    if "filter" in obj:
        check_filter(str(obj["filter"]), f"{where}.filter", rep)
    so = obj.get("sortOrder")
    if so is not None and so not in ("ascending", "descending"):
        rep.err(where, "sortOrder must be ascending or descending")
    si = obj.get("startIndex")
    if si is not None and (not isinstance(si, int) or si < 1):
        rep.err(where, "startIndex is 1-based: an integer >= 1")
    c = obj.get("count")
    if c is not None and (not isinstance(c, int) or c < 0):
        rep.err(where, "count must be a non-negative integer")


def check_patch(obj: dict, where: str, rep: Report, resource: str | None = None) -> None:
    ops = obj.get("Operations")
    if ops is None:
        real, ops = find_ci(obj, "Operations")
        if ops is None:
            rep.err(where, "'Operations' (array) is required")
            return
        rep.warn(where, f"'{real}': RFC 7644 uses 'Operations'")
    if not isinstance(ops, list) or not ops:
        rep.err(where, "'Operations' must be a non-empty array")
        return
    attrs, _ = resource_attrs(resource)
    for i, op in enumerate(ops):
        w = f"{where}.Operations[{i}]"
        if not isinstance(op, dict):
            rep.err(w, "must be an object")
            continue
        name = op.get("op")
        if not isinstance(name, str) or name.lower() not in ("add", "remove", "replace"):
            rep.err(w, f"op '{name}' is not add, remove or replace (SCIM has no move/copy/test)")
            continue
        if name != name.lower():
            rep.warn(w, f"op '{name}': RFC 7644 spells it '{name.lower()}'; many servers accept any case, strict ones do not")
        name = name.lower()
        path = op.get("path")
        if path is not None:
            if not isinstance(path, str):
                rep.err(w, "'path' must be a string")
            else:
                check_path(path, f"{w}.path", rep, resource)
                if resource:
                    base = split_path(re.split(r"[\[]", path, 1)[0])
                    a, _ = resolve_attr(base if "[" not in path else {**base, "sub": None}, resource)
                    if a is not None and a.get("mutability") == "readOnly":
                        rep.err(w, f"'{path}' is readOnly: modifying it fails with scimType mutability")
                    elif a is not None and a.get("mutability") == "immutable" and name != "add":
                        rep.warn(w, f"'{path}' is immutable: it can only be added when it has no value")
        if name == "remove":
            if path is None:
                rep.err(w, "'remove' needs a 'path' (scimType noTarget)")
            if "value" in op:
                rep.warn(w, "'remove' takes no 'value' in RFC 7644; to remove one member use a path filter, "
                            "e.g. members[value eq \"...\"]")
        else:
            if "value" not in op:
                rep.err(w, f"'{name}' needs a 'value'")
            elif path is None:
                v = op["value"]
                if not isinstance(v, dict):
                    rep.err(w, f"'{name}' without 'path' needs an object value whose keys are attribute names")
                elif attrs:
                    for k in v:
                        if k.lower().startswith("urn:") or "." in k:
                            continue
                        real, a = find_ci(attrs, k)
                        if a is None:
                            rep.warn(f"{w}.value.{k}", f"not an attribute of {resource}")
                        elif a.get("mutability") == "readOnly":
                            rep.err(f"{w}.value.{k}", "readOnly attribute (scimType mutability)")


def check_bulk_request(obj: dict, where: str, rep: Report) -> None:
    ops = obj.get("Operations")
    if not isinstance(ops, list) or not ops:
        rep.err(where, "'Operations' (non-empty array) is required")
        return
    foe = obj.get("failOnErrors")
    if foe is not None and (not isinstance(foe, int) or foe < 1):
        rep.err(where, "failOnErrors must be a positive integer")
    seen = set()
    for i, op in enumerate(ops):
        w = f"{where}.Operations[{i}]"
        m = str(op.get("method", "")).upper()
        if m not in ("POST", "PUT", "PATCH", "DELETE"):
            rep.err(w, f"method '{op.get('method')}' must be POST, PUT, PATCH or DELETE")
            continue
        if not op.get("path"):
            rep.err(w, "'path' is required")
        if m == "POST":
            if not op.get("bulkId"):
                rep.err(w, "POST needs a 'bulkId'")
            elif op["bulkId"] in seen:
                rep.err(w, f"bulkId '{op['bulkId']}' is used twice")
            seen.add(op.get("bulkId"))
        if m in ("POST", "PUT", "PATCH") and "data" not in op:
            rep.err(w, f"{m} needs 'data'")
        if m == "DELETE" and "data" in op:
            rep.warn(w, "DELETE takes no 'data'")
        if m in ("PUT", "PATCH", "DELETE") and isinstance(op.get("path"), str) and op["path"].rstrip("/").count("/") < 2 \
                and "bulkId:" not in op["path"]:
            rep.warn(w, f"{m} path should address one resource, e.g. /Users/{{id}}")
        data = op.get("data")
        if m == "PATCH" and isinstance(data, dict):
            check_patch(data, f"{w}.data", rep)
        elif m in ("POST", "PUT") and isinstance(data, dict) and data.get("schemas"):
            check_object(data, f"{w}.data", rep, "request")


def check_bulk_response(obj: dict, where: str, rep: Report) -> None:
    for i, op in enumerate(obj.get("Operations") or []):
        w = f"{where}.Operations[{i}]"
        st = op.get("status")
        if st is None:
            rep.err(w, "'status' is required in bulk responses")
        elif isinstance(st, dict):
            rep.err(w, "'status' must be the HTTP status as a string (\"201\"), not an object {\"code\": ...} "
                       "(that form appears in one RFC 7644 example, section 3.7.2, but not in the definition)")
        elif not isinstance(st, str):
            rep.err(w, "'status' is a string in bulk responses")
        if str(op.get("method", "")).upper() == "POST" and not op.get("bulkId"):
            rep.err(w, "POST results carry the bulkId")
        resp = op.get("response")
        if isinstance(resp, dict) and resp.get("schemas"):
            check_object(resp, f"{w}.response", rep, "response")


def check_by_schema(obj: dict, urn: str, where: str, rep: Report) -> None:
    """ServiceProviderConfig / ResourceType / Schema resources, checked against RFC 7643 section 8.7.2."""
    attrs = schema_attrs(urn)
    for name, a in attrs.items():
        if a.get("required") and find_ci(obj, name)[1] is None:
            rep.err(where, f"required attribute '{name}' is missing")
    for k, v in obj.items():
        if k in ("schemas", "meta", "id"):
            continue
        real, a = find_ci(attrs, k)
        if a is None:
            rep.warn(f"{where}.{k}", "not defined by this schema")
            continue
        check_value(a, v, f"{where}.{k}", rep, "response")


def guess_schema(obj: dict) -> str | None:
    """Best guess of the schema URN of an object that forgot 'schemas', so the other checks still run."""
    keys = {k.lower() for k in obj}
    if "operations" in keys and any(isinstance(o, dict) and "op" in o for o in obj.get("Operations", []) or []):
        return MSG["PatchOp"]
    if "operations" in keys:
        return MSG["BulkRequest"]
    if "status" in keys and ({"scimtype", "detail"} & keys):
        return MSG["Error"]
    if "totalresults" in keys or "resources" in keys:
        return MSG["ListResponse"]
    if "username" in keys:
        return URN_USER
    if "displayname" in keys and ("members" in keys or "username" not in keys):
        return URN_GROUP
    return None


def check_object(obj: dict, where: str, rep: Report, mode: str) -> None:
    schemas = obj.get("schemas")
    if schemas is None:
        guess = guess_schema(obj)
        rep.err(where, "'schemas' (array of URNs) is required on every SCIM resource and message"
                + (f"; this looks like {guess}, checked as such" if guess else ""))
        if not guess:
            return
        schemas = [guess]
    if isinstance(schemas, str):
        rep.err(where, "'schemas' must be an array, not a string")
        schemas = [schemas]
    low = [str(s).lower() for s in schemas]
    if URN_USER.lower() in low:
        check_resource(obj, where, rep, mode, URN_USER)
    elif URN_GROUP.lower() in low:
        check_resource(obj, where, rep, mode, URN_GROUP)
    elif MSG["ListResponse"].lower() in low:
        check_list_response(obj, where, rep)
    elif MSG["Error"].lower() in low:
        check_error(obj, where, rep)
    elif MSG["SearchRequest"].lower() in low:
        check_search(obj, where, rep)
    elif MSG["PatchOp"].lower() in low:
        check_patch(obj, where, rep)
    elif MSG["BulkRequest"].lower() in low:
        check_bulk_request(obj, where, rep)
    elif MSG["BulkResponse"].lower() in low:
        check_bulk_response(obj, where, rep)
    elif URN_SPC.lower() in low:
        check_by_schema(obj, URN_SPC, where, rep)
    elif URN_RT.lower() in low:
        check_by_schema(obj, URN_RT, where, rep)
    elif URN_SCHEMA.lower() in low:
        check_by_schema(obj, URN_SCHEMA, where, rep)
    elif URN_ENT.lower() in low:
        rep.err(where, "the Enterprise User extension needs the core User schema in 'schemas' too")
    else:
        rep.warn(where, f"unknown schemas {schemas}: not checked")


def check(obj, rep: Report, mode: str = "auto") -> None:
    items = obj if isinstance(obj, list) else [obj]
    for i, o in enumerate(items):
        w = f"[{i}]" if isinstance(obj, list) else "root"
        if not isinstance(o, dict):
            rep.err(w, "expected a JSON object")
            continue
        m = mode
        if m == "auto":
            m = "response" if ("id" in o or "meta" in o) else "request"
        check_object(o, w, rep, m)


def main(argv) -> int:
    import argparse
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("files", nargs="*")
    ap.add_argument("--mode", choices=("auto", "request", "response"), default="auto")
    ap.add_argument("--filter", help="check a filter expression")
    ap.add_argument("--path", help="check a PATCH path")
    ap.add_argument("--resource", choices=("User", "Group"), help="check attribute names against this resource type")
    a = ap.parse_args(argv[1:])
    if not (a.files or a.filter or a.path):
        ap.print_help()
        return 2
    failed = False
    jobs = []
    if a.filter is not None:
        jobs.append(("filter", a.filter))
    if a.path is not None:
        jobs.append(("path", a.path))
    for kind, text in jobs:
        rep = Report()
        (check_filter if kind == "filter" else check_path)(text, kind, rep, a.resource)
        for e in rep.errors:
            print(f"  ERROR   {e}")
        for w in rep.warnings:
            print(f"  WARNING {w}")
        print(f"{kind} {text!r}: {'FAIL' if rep.errors else 'OK'}")
        failed |= bool(rep.errors)
    for path in a.files:
        try:
            with open(path, encoding="utf-8") as fh:
                obj = json.load(fh)
        except (OSError, ValueError) as e:
            print(f"{path}: cannot read JSON: {e}")
            return 2
        rep = Report()
        check(obj, rep, a.mode)
        for e in rep.errors:
            print(f"  ERROR   {e}")
        for w in rep.warnings:
            print(f"  WARNING {w}")
        print(f"{path}: {'FAIL' if rep.errors else 'OK'} ({len(rep.errors)} error(s), {len(rep.warnings)} warning(s))")
        failed |= bool(rep.errors)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
