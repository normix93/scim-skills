#!/usr/bin/env python3
"""Un-blind grades and print a Markdown results table.

grades.jsonl: {"id": "...", "A": {"score": 0-2, "note": "..."}, "B": {...}}
blind_map.json: {"<id>": {"A": "baseline"|"skills", "B": "..."}}
"""
import collections
import json
import sys


def main(grades_path, map_path, questions_path="evals/questions.jsonl"):
    blind = json.load(open(map_path))
    skill_of = {}
    try:
        for line in open(questions_path):
            q = json.loads(line)
            skill_of[q["id"]] = q["skill"]
    except OSError:
        pass
    per = collections.defaultdict(lambda: {"baseline": 0, "skills": 0, "n": 0})
    tot = {"baseline": 0, "skills": 0}
    rows = []
    for line in open(grades_path):
        g = json.loads(line)
        m = blind[g["id"]]
        s = {m["A"]: g["A"], m["B"]: g["B"]}
        sk = skill_of.get(g["id"], g["id"].split("-")[0])
        per[sk]["n"] += 1
        for k in ("baseline", "skills"):
            per[sk][k] += s[k]["score"]
            tot[k] += s[k]["score"]
        rows.append((g["id"], s["baseline"]["score"], s["skills"]["score"], s["baseline"].get("note", ""),
                     s["skills"].get("note", "")))
    n = len(rows)
    print("# Results\n")
    print(f"{n} questions, 0–2 points each (max {2 * n}). Blind grading by a separate agent.\n")
    print("| Skill | Questions | Without skills | With skills |\n|---|---|---|---|")
    for sk, v in sorted(per.items()):
        print(f"| {sk} | {v['n']} | {v['baseline']}/{2 * v['n']} | {v['skills']}/{2 * v['n']} |")
    print(f"| **Total** | {n} | **{tot['baseline']}/{2 * n} ({100 * tot['baseline'] / (2 * n):.0f}%)** | "
          f"**{tot['skills']}/{2 * n} ({100 * tot['skills'] / (2 * n):.0f}%)** |\n")
    print("## Per question\n\n| id | without | with | grader note (without) | grader note (with) |\n|---|---|---|---|---|")
    for r in rows:
        print(f"| {r[0]} | {r[1]} | {r[2]} | {r[3].replace('|', '/')} | {r[4].replace('|', '/')} |")


if __name__ == "__main__":
    main(*sys.argv[1:])
