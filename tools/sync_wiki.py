#!/usr/bin/env python3
"""
sync_wiki.py — one-way docs → GitHub-wiki mirror (2026-07-11).

The repo is canonical; the wiki is a generated artifact. This script
transforms the public docs into flat wiki pages (banner + link rewrite),
regenerates _Sidebar/_Footer, and prunes orphaned pages in the wiki
working tree. It NEVER touches git — review, commit, and push the wiki
clone yourself.

Run from the repo root:
  .venv/bin/python tools/sync_wiki.py --wiki ../Orlando-El-Bastardo.wiki
  .venv/bin/python tools/sync_wiki.py --wiki ... --dry-run

Excluded always: docs/local/** (machine specifics, local only),
CLAUDE.md, LICENSE.md, the root README stub.
"""

import argparse
import os
import re
import subprocess
import sys

REPO_URL = "https://github.com/twgmichael/Orlando-El-Bastardo"

# (repo_path, wiki_page_name, sidebar_group, display) — sidebar order
# follows this list; Home is the landing page and stays out of the groups.
PAGES = [
    ("docs/README.md",            "Home",           None,        "Home"),
    ("docs/ARCHITECTURE.md",      "Architecture",   "Design",    "Architecture"),
    ("docs/SCHEMA.md",            "Schema",         "Design",    "Schema"),
    ("docs/BAR-SCENE.md",         "Bar-Scene",      "Design",    "Bar Scene"),
    ("docs/RIGGING.md",           "Rigging",        "Standards", "Rigging"),
    ("docs/PROVENANCE.md",        "Provenance",     "Standards", "Provenance"),
    ("docs/DECISIONS.md",         "Decisions",      "Standards", "Decisions"),
    ("docs/OPEN-QUESTIONS.md",    "Open-Questions", "Standards", "Open Questions"),
    ("docs/RESOURCES.md",         "Resources",      "Standards", "Resources"),
    ("docs/planning/AGENT-WORKFLOW-PLAN.md", "Agent-Workflow-Plan",
     "Planning", "Agent Workflow Plan"),
    ("docs/planning/PRODUCER-PLAN.md",       "Producer-Plan",
     "Planning", "Producer Plan"),
    ("docs/planning/ESCALATION-PROTOCOL.md", "Escalation-Protocol",
     "Planning", "Escalation Protocol"),
    ("docs/planning/SEAMLESS-RUN-PLAN.md",   "Seamless-Run-Plan",
     "Planning", "Seamless Run Plan"),
    ("docs/planning/GOAL-REVIEW-AND-RECOMMENDATIONS-2026-07-06.md",
     "Goal-Review-2026-07-06", "Journal", "Goal Review (2026-07-06)"),
    ("docs/planning/PROGRESS-2026-07-05-ANIMATED-PREVIEW.md",
     "Progress-2026-07-05-Animated-Preview", "Journal",
     "Animated Preview (2026-07-05)"),
    ("docs/planning/PROGRESS-2026-07-06-PHASE4-5.md",
     "Progress-2026-07-06-Phase-4-5", "Journal",
     "Phases 4-5 (2026-07-06)"),
    ("PROJECT-TODO.md",           "Roadmap",     "Tracking", "Roadmap"),
    ("PROJECT-DONE.md",           "Journal-Log", "Tracking", "Journal Log"),
]
GROUP_ORDER = ["Design", "Standards", "Planning", "Journal", "Tracking"]

LINK_RE = re.compile(r"\[([^]]*)\]\(([^)#\s]+)(#[^)]*)?\)")


def head_hash():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def rewrite_links(text, page_info):
    """Doc-to-doc links → wiki page links (plain markdown, which GitHub
    wikis resolve — no [[pipe]] syntax ambiguity); other repo-file links →
    absolute blob URLs; external links untouched. A label that is just the
    source filename is replaced by the page's display name."""
    def sub(m):
        label, target, anchor = m.group(1), m.group(2), m.group(3) or ""
        if re.match(r"^[a-z]+://|^mailto:", target):
            return m.group(0)
        base = os.path.basename(target)
        if base in page_info:
            page, display = page_info[base]
            if label == base:
                label = display
            return f"[{label}]({page}{anchor})"
        clean = target.lstrip("./")
        return f"[{label}]({REPO_URL}/blob/main/{clean}{anchor})"
    return LINK_RE.sub(sub, text)


def main():
    p = argparse.ArgumentParser(prog="sync_wiki")
    p.add_argument("--wiki", required=True,
                   help="Path to the cloned <repo>.wiki working tree")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    wiki = os.path.abspath(args.wiki)
    if not os.path.isdir(os.path.join(wiki, ".git")):
        sys.exit(f"[sync_wiki] ERROR: {wiki} is not a git working tree")
    for path, _n, _g, _d in PAGES:
        if not os.path.isfile(path):
            sys.exit(f"[sync_wiki] ERROR: source missing: {path} "
                     f"(run from the repo root)")
        if "docs/local" in path:
            sys.exit(f"[sync_wiki] ERROR: refusing local-only file: {path}")

    rev = head_hash()
    page_info = {os.path.basename(src): (name, display)
                 for src, name, _g, display in PAGES}
    generated = set()

    for src, name, _group, _display in PAGES:
        body = open(src, encoding="utf-8").read()
        body = rewrite_links(body, page_info)
        banner = (f"> Mirrored from [`{src}`]({REPO_URL}/blob/main/{src}) "
                  f"@ `{rev}` — the repo is canonical. Edit there, not "
                  f"here; hand edits are overwritten by the next sync.\n\n")
        out = os.path.join(wiki, f"{name}.md")
        generated.add(f"{name}.md")
        if args.dry_run:
            print(f"[sync_wiki] would write {name}.md  ← {src}")
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(banner + body)
            print(f"[sync_wiki] wrote {name}.md  ← {src}")

    # _Sidebar: Home first, then the groups in fixed order
    side = ["**[Home](Home)**", ""]
    for group in GROUP_ORDER:
        side.append(f"**{group}**")
        for _src, name, g, display in PAGES:
            if g == group:
                side.append(f"- [{display}]({name})")
        side.append("")
    side.append(f"---\n[Repository]({REPO_URL})")
    footer = (f"Generated from the repo's `docs/` @ `{rev}` by "
              f"`tools/sync_wiki.py` — [source repository]({REPO_URL}). "
              f"License: PolyForm Noncommercial 1.0.0.")
    for fname, content in (("_Sidebar.md", "\n".join(side) + "\n"),
                           ("_Footer.md", footer + "\n")):
        generated.add(fname)
        if args.dry_run:
            print(f"[sync_wiki] would write {fname}")
        else:
            with open(os.path.join(wiki, fname), "w", encoding="utf-8") as f:
                f.write(content)
            print(f"[sync_wiki] wrote {fname}")

    # Prune orphaned pages (one-way mirror owns the whole page set)
    for entry in sorted(os.listdir(wiki)):
        if entry.endswith(".md") and entry not in generated:
            if args.dry_run:
                print(f"[sync_wiki] would prune {entry}")
            else:
                os.remove(os.path.join(wiki, entry))
                print(f"[sync_wiki] pruned {entry}")

    print(f"[sync_wiki] done — {len(generated)} pages @ {rev}. Review the "
          f"wiki working tree, then commit and push it yourself.")


if __name__ == "__main__":
    main()
