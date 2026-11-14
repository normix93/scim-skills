"""Regression tests for the SCIM skill. Run: python3 -m unittest discover -s tests -v  (stdlib only)

The RFC-example tests download RFC 7643/7644 into .cache/rfc (or use $SCIM_RFC_DIR); they are skipped when the
RFCs cannot be fetched. The RFC text is never committed to this repository.
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPTS = os.path.join(ROOT, "skills", "scim", "scripts")
FIX = os.path.join(ROOT, "tests", "fixtures")
sys.path.insert(0, SCRIPTS)
sys.path.insert(0, os.path.join(ROOT, "tools"))
import scim_check as c  # noqa: E402

CHECK = os.path.join(SCRIPTS, "scim_check.py")

# Examples in the RFCs that contradict the RFCs' own rules. Each is documented in references/rfc-issues.md.
KNOWN_RFC_ISSUES = {
    ("7644", "3.7.2.", "status"): "bulk response example uses {\"code\": \"201\"} instead of a status string",
    ("7643", "8.2.", "password"): "full User representation (with id and meta) shows the writeOnly password",
    ("7643", "8.3.", "password"): "same, in the Enterprise User representation",
}
KNOWN_RFC_FILTERS = {
    "(meta.resourceType eq User) or (meta.resourceType eq Group)": "unquoted string values (section 3.4.2)",
    "displayName sw 'Group'": "single-quoted string (section 3.7.2)",
}


def run(*args) -> tuple[int, str]:
    p = subprocess.run([sys.executable, CHECK, *args], capture_output=True, text=True)
    return p.returncode, p.stdout + p.stderr


def filt(text: str, resource: str | None = None) -> c.Report:
    rep = c.Report()
    c.check_filter(text, "f", rep, resource)
    return rep


def path(text: str, resource: str | None = None) -> c.Report:
    rep = c.Report()
    c.check_path(text, "p", rep, resource)
    return rep


class Fixtures(unittest.TestCase):
    def test_good_fixtures_pass_clean(self):
        for f in sorted(glob.glob(os.path.join(FIX, "good", "*.json"))):
            with self.subTest(f=os.path.basename(f)):
                code, out = run(f)
                self.assertEqual(code, 0, out)
                self.assertIn("0 error(s), 0 warning(s)", out)

    def test_bad_fixtures_report_expected_errors(self):
        for f in sorted(glob.glob(os.path.join(FIX, "bad", "*.json"))):
            with open(f[:-5] + ".expected", encoding="utf-8") as fh:
                expected = [l.strip() for l in fh if l.strip()]
            with self.subTest(f=os.path.basename(f)):
                code, out = run(f, "--mode", "response")
                self.assertEqual(code, 1, out)
                for e in expected:
                    self.assertIn(e, out)


class Filters(unittest.TestCase):
    GOOD = [
        'userName eq "bjensen"',
        'name.familyName co "O\'Malley"',
        'urn:ietf:params:scim:schemas:core:2.0:User:userName sw "J"',
        'title pr',
        'meta.lastModified gt "2011-05-13T04:42:34Z"',
        'title pr and userType eq "Employee"',
        'userType ne "Employee" and not (emails.value co "example.com" or emails.value co "example.org")',
        'emails[type eq "work" and value co "@example.com"] or ims[type eq "xmpp" and value co "@foo.com"]',
        'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber eq "1001"',
        'active eq true',
        'userName Eq "john"',
    ]
    BAD = {
        'userName == "bjensen"': "use eq",
        'userName eq "a" && active eq true': "use and",
        "userName eq 'bjensen'": "double quotes",
        'userName like "b%"': "use co or sw",
        'userName eq bjensen': "must be a JSON string",
        '(userName eq "a"': "unbalanced",
        'emails[type eq "work"': "unbalanced",
        'and userName eq "a"': "needs an expression",
        'active eq True': "lowercase",
        'userName pr "x"': "unexpected",
    }

    def test_valid_filters(self):
        for f in self.GOOD:
            with self.subTest(f=f):
                self.assertEqual(filt(f, "User").errors, [])

    def test_invalid_filters(self):
        for f, hint in self.BAD.items():
            with self.subTest(f=f):
                rep = filt(f)
                self.assertTrue(rep.errors, f)
                self.assertIn(hint, " ".join(rep.errors))

    def test_semantics(self):
        self.assertIn("boolean", " ".join(filt('active gt false', "User").errors))
        self.assertIn("without quotes", " ".join(filt('active eq "true"', "User").errors))
        self.assertIn("not an attribute of User", " ".join(filt('department eq "x"', "User").errors))
        self.assertEqual(filt('urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:department eq "x"', "User").errors, [])
        self.assertTrue(filt('emails co "x"', "User").warnings)       # RFC short form: warning, not error
        self.assertTrue(filt('a[b[c pr]]').warnings)                   # nested valuePath, erratum 4690


class Paths(unittest.TestCase):
    def test_paths(self):
        for p in ("members", "name.familyName", 'addresses[type eq "work"]',
                  'members[value eq "2819c223-7f76-453a-919d-413861904646"]',
                  'urn:ietf:params:scim:schemas:extension:enterprise:2.0:User:employeeNumber'):
            with self.subTest(p=p):
                self.assertEqual(path(p).errors, [])
        for p, hint in {"emails[0].value": "array indexes", "emails[0]": "array indexes",
                        "name.givenName[value pr]": "cannot have a sub-attribute", "/name/givenName": "invalid path"}.items():
            with self.subTest(p=p):
                self.assertIn(hint, " ".join(path(p).errors))

    def test_patch_mutability(self):
        rep = c.Report()
        c.check_patch({"Operations": [{"op": "replace", "path": "id", "value": "x"},
                                      {"op": "replace", "value": {"meta": {}}}]}, "r", rep, "User")
        self.assertEqual(sum("readOnly" in e for e in rep.errors), 2, rep.errors)


class RfcExamples(unittest.TestCase):
    """Every JSON example with a "schemas" member in RFC 7643/7644 must pass, except known RFC issues."""

    @classmethod
    def setUpClass(cls):
        try:
            import rfctext
            cls.rfc = {n: rfctext.load(n) for n in ("7643", "7644")}
            cls.rfctext = rfctext
        except Exception as e:  # offline
            raise unittest.SkipTest(f"RFCs not available: {e}")

    def test_json_examples(self):
        checked = 0
        for num, lines in self.rfc.items():
            text = "\n".join(lines)
            for pos, blob in self.rfctext.json_blocks(text):
                if not (isinstance(blob, dict) and "schemas" in blob):
                    continue
                line = text[:pos].count("\n")
                sec = [l.split("  ")[0] for l in lines[:line] if re.match(r"^\d+(\.\d+)*\.  ", l)][-1]
                rep = c.Report()
                c.check(blob, rep)
                errs = [e for e in rep.errors
                        if not any(num == k[0] and sec == k[1] and k[2] in e for k in KNOWN_RFC_ISSUES)]
                with self.subTest(rfc=num, section=sec, line=line):
                    self.assertEqual(errs, [])
                checked += 1
        self.assertGreaterEqual(checked, 30)

    def test_filter_examples(self):
        lines = self.rfc["7644"]
        found = [m.group(1).strip() for l in lines for m in [re.search(r"filter=(.+)$", l)] if m]
        complete = [f for f in found if f.count("(") == f.count(")") and f.count("[") == f.count("]")
                    and not re.search(r"\s(and|or|not)$", f)]  # skip examples wrapped over two lines
        self.assertGreaterEqual(len(complete), 15)
        for f in complete:
            with self.subTest(f=f):
                rep = filt(f)
                if f in KNOWN_RFC_FILTERS:
                    self.assertTrue(rep.errors, "known RFC issue no longer detected")
                else:
                    self.assertEqual(rep.errors, [])


class SkillFiles(unittest.TestCase):
    def test_frontmatter_and_links(self):
        for skill in glob.glob(os.path.join(ROOT, "skills", "*", "SKILL.md")):
            with open(skill, encoding="utf-8") as fh:
                text = fh.read()
            m = re.match(r"^---\nname: (.+)\ndescription: (.+?)\n---\n", text, re.S)
            self.assertIsNotNone(m)
            self.assertEqual(m.group(1).strip(), os.path.basename(os.path.dirname(skill)))
            self.assertLessEqual(len(m.group(2)), 1024)
            for ref in re.findall(r"`((?:references|scripts)/[\w./-]+)`", text):
                self.assertTrue(os.path.exists(os.path.join(os.path.dirname(skill), ref)), ref)

    def test_json_parses(self):
        for f in glob.glob(os.path.join(ROOT, "skills", "*", "scripts", "*.json")):
            with open(f, encoding="utf-8") as fh:
                json.load(fh)


if __name__ == "__main__":
    unittest.main()
