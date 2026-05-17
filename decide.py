#!/usr/bin/env python3
"""
decide — capture the why behind code decisions
Usage:
  decide                      interactive, auto-detects git context
  decide <file>               capture decision for a specific file
  decide --list               show recent decisions
  decide --search <term>      search decisions
  decide --context <file>     surface relevant decisions when returning to a file
"""

import argparse
import ast
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime
from pathlib import Path
import re


DECISIONS_DIR = "decisions"


def git_root():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True
        )
        return Path(result.stdout.strip())
    except subprocess.CalledProcessError:
        return None


def git_commit():
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True, text=True, check=True
        )
        return result.stdout.strip()
    except subprocess.CalledProcessError:
        return None


def git_recent_files():
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "HEAD"],
            capture_output=True, text=True, check=True
        )
        files = result.stdout.strip().split("\n")
        return [f for f in files if f]
    except subprocess.CalledProcessError:
        return []


def prompt(label, required=True, hint=None):
    hint_str = f" ({hint})" if hint else ""
    while True:
        value = input(f"  {label}{hint_str}: ").strip()
        if value or not required:
            return value
        print("  Required. Try again.")


def prompt_list(label, hint=None):
    hint_str = f" ({hint})" if hint else ""
    raw = input(f"  {label}{hint_str}: ").strip()
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def prompt_confidence():
    while True:
        raw = input("  Confidence [H/m/l] (default: H): ").strip().lower()
        if raw in ("", "h"):
            return "high"
        if raw == "m":
            return "medium"
        if raw == "l":
            return "low"


def slugify(text):
    text = text.lower()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"\s+", "-", text.strip())
    return text[:50]


def save_decision(root, record):
    decisions_path = root / DECISIONS_DIR
    decisions_path.mkdir(exist_ok=True)

    date_str = datetime.now().strftime("%Y-%m-%d")
    slug = slugify(record["decision"])
    filename = f"{date_str}-{slug}.json"
    filepath = decisions_path / filename

    with open(filepath, "w") as f:
        json.dump(record, f, indent=2)

    return filepath


def capture(artifact_path=None):
    root = git_root()
    if not root:
        print("Not inside a git repository. Navigate to your project first.")
        sys.exit(1)

    print("\n── Decision Capture ──────────────────────────────")

    # auto-suggest artifact from recent git changes
    if not artifact_path:
        recent = git_recent_files()
        if recent:
            print(f"\n  Recently changed: {', '.join(recent[:3])}")
        artifact_path = prompt(
            "File or module this decision affects",
            required=False,
            hint="e.g. src/auth/token.ts or leave blank"
        )

    decision = prompt("What did you decide")
    why = prompt("Why")
    rejected = prompt_list(
        "What did you reject",
        hint="comma-separated, or leave blank"
    )
    constraints = prompt_list(
        "Any constraints that forced this",
        hint="deadline, dependency, etc. — or leave blank"
    )
    confidence = prompt_confidence()

    record = {
        "id": str(uuid.uuid4()),
        "timestamp": datetime.now().isoformat(),
        "artifact": {
            "path": artifact_path or "",
            "ref": git_commit()
        },
        "decision": decision,
        "why": why,
        "rejected": rejected,
        "constraints": constraints,
        "confidence": confidence,
        "tags": []
    }

    filepath = save_decision(root, record)
    print(f"\n  Saved → {filepath.relative_to(root)}\n")


def list_decisions():
    root = git_root()
    if not root:
        print("Not inside a git repository.")
        sys.exit(1)

    decisions_path = root / DECISIONS_DIR
    if not decisions_path.exists():
        print("No decisions recorded yet.")
        return

    files = sorted(decisions_path.glob("*.json"), reverse=True)
    if not files:
        print("No decisions recorded yet.")
        return

    print(f"\n── Recent Decisions ({len(files)} total) ─────────────────\n")
    for f in files[:10]:
        with open(f) as fh:
            r = json.load(fh)
        artifact = r["artifact"].get("path") or "—"
        print(f"  {r['timestamp'][:10]}  {artifact}")
        print(f"    Decision:  {r['decision']}")
        print(f"    Why:       {r['why']}")
        if r["rejected"]:
            print(f"    Rejected:  {', '.join(r['rejected'])}")
        print()


def search_decisions(term):
    root = git_root()
    if not root:
        print("Not inside a git repository.")
        sys.exit(1)

    decisions_path = root / DECISIONS_DIR
    if not decisions_path.exists():
        print("No decisions recorded yet.")
        return

    term = term.lower()
    matches = []
    for f in sorted(decisions_path.glob("*.json"), reverse=True):
        with open(f) as fh:
            r = json.load(fh)
        searchable = json.dumps(r).lower()
        if term in searchable:
            matches.append(r)

    if not matches:
        print(f"No decisions matching '{term}'.")
        return

    print(f"\n── Matches for '{term}' ({len(matches)} found) ────────────\n")
    for r in matches:
        artifact = r["artifact"].get("path") or "—"
        print(f"  {r['timestamp'][:10]}  {artifact}")
        print(f"    Decision:  {r['decision']}")
        print(f"    Why:       {r['why']}")
        print()


def extract_identifiers(filepath):
    """Extract function/class names from a Python file as retrieval signals."""
    try:
        source = Path(filepath).read_text()
        tree = ast.parse(source)
        names = set()
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                names.add(node.name.lower())
        return names
    except Exception:
        return set()


def score_decision(record, target_path, target_dir, identifiers):
    score = 0
    artifact_path = record["artifact"].get("path", "").lower()
    searchable = (
        record["decision"] + " " +
        record["why"] + " " +
        " ".join(record.get("rejected", [])) + " " +
        " ".join(record.get("constraints", []))
    ).lower()

    # exact file match — strongest signal
    if artifact_path == target_path.lower():
        score += 10

    # same directory
    if artifact_path and str(target_dir).lower() in artifact_path:
        score += 4

    # identifier overlap — function/class names appear in decision text
    for ident in identifiers:
        if len(ident) > 3 and ident in searchable:
            score += 2

    # tag overlap
    for tag in record.get("tags", []):
        if tag.lower() in searchable:
            score += 1

    return score


def context(filepath):
    root = git_root()
    if not root:
        print("Not inside a git repository.")
        sys.exit(1)

    decisions_path = root / DECISIONS_DIR
    if not decisions_path.exists():
        print("No decisions recorded yet.")
        return

    target = Path(filepath)
    target_dir = target.parent
    identifiers = extract_identifiers(root / filepath) if (root / filepath).exists() else set()

    scored = []
    for f in decisions_path.glob("*.json"):
        with open(f) as fh:
            r = json.load(fh)
        s = score_decision(r, filepath, target_dir, identifiers)
        if s > 0:
            scored.append((s, r))

    scored.sort(key=lambda x: (-x[0], x[1]["timestamp"]), reverse=False)
    scored = scored[:8]

    if not scored:
        print(f"\n  No relevant decisions found for {filepath}.\n")
        return

    print(f"\n── Context for {filepath} ({len(scored)} relevant decisions) ──\n")
    for score, r in scored:
        artifact = r["artifact"].get("path") or "—"
        confidence_marker = {"high": "●", "medium": "◐", "low": "○"}.get(r["confidence"], "●")
        print(f"  {confidence_marker} {r['timestamp'][:10]}  {artifact}")
        print(f"    Decision:  {r['decision']}")
        print(f"    Why:       {r['why']}")
        if r["rejected"]:
            print(f"    Rejected:  {', '.join(r['rejected'])}")
        if r["constraints"]:
            print(f"    Constraints: {', '.join(r['constraints'])}")
        print()


def main():
    parser = argparse.ArgumentParser(description="Capture the why behind code decisions")
    parser.add_argument("file", nargs="?", help="File this decision affects")
    parser.add_argument("--list", action="store_true", help="List recent decisions")
    parser.add_argument("--search", metavar="TERM", help="Search decisions")
    parser.add_argument("--context", metavar="FILE", help="Surface relevant decisions for a file")
    args = parser.parse_args()

    if args.list:
        list_decisions()
    elif args.search:
        search_decisions(args.search)
    elif args.context:
        context(args.context)
    else:
        capture(args.file)


if __name__ == "__main__":
    main()
