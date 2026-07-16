#!/usr/bin/env python3
"""
sync_wiki.py — one-way docs → GitHub-wiki mirror.

The repo is canonical; the wiki is a generated artifact. This script
transforms markdown files tagged with `wiki: true` front matter into flat
wiki pages (banner + link rewrite), regenerates _Sidebar/_Footer, and
prunes orphaned pages in the wiki working tree. It NEVER touches git.

Run from the repo root:
  .venv/bin/python tools/sync_wiki.py --wiki ../Orlando-El-Bastardo.wiki
  .venv/bin/python tools/sync_wiki.py --wiki ... --dry-run

Excluded always: docs/local/** (machine specifics, local only), even if a
file there is accidentally tagged `wiki: true`.
"""

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass

REPO_URL = "https://github.com/twgmichael/Orlando-El-Bastardo"

SOURCE_ROOTS = ["docs", "PROJECT-TODO.md", "PROJECT-DONE.md"]
GROUP_ORDER = ["Design", "Standards", "Planning", "Journal", "Tracking"]
VALID_GROUPS = {"Home", *GROUP_ORDER}
VALID_STATUSES = {
    "draft",
    "active",
    "approved",
    "archived",
    "superseded",
    "remove_next_cleanup",
}

LINK_RE = re.compile(r"\[([^]]*)\]\(([^)#\s]+)(#[^)]*)?\)")


@dataclass(frozen=True)
class Page:
    src: str
    name: str
    group: str
    display: str
    order: int
    body: str
    created: str
    updated: str
    doc_type: str
    status: str
    canonical: bool
    canonical_for: str | None
    superseded_by: str | None


@dataclass(frozen=True)
class SourceDoc:
    metadata: dict


def head_hash():
    return subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                          capture_output=True, text=True,
                          check=True).stdout.strip()


def slugify(value):
    slug = re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-")
    return slug or "Untitled"


def parse_scalar(value):
    value = value.strip()
    if value == "true":
        return True
    if value == "false":
        return False
    if value.isdigit():
        return int(value)
    if ((value.startswith('"') and value.endswith('"')) or
            (value.startswith("'") and value.endswith("'"))):
        return value[1:-1]
    return value


def split_front_matter(path):
    text = open(path, encoding="utf-8").read()
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].strip() != "---":
        return {}, text
    for idx in range(1, len(lines)):
        if lines[idx].strip() == "---":
            raw = "".join(lines[1:idx])
            body = "".join(lines[idx + 1:])
            return parse_front_matter(raw), body.lstrip("\n")
    return {}, text


def parse_front_matter(raw):
    metadata = {}
    current_key = None
    for lineno, line in enumerate(raw.splitlines(), start=2):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("- "):
            if current_key is None:
                sys.exit(f"[sync_wiki] ERROR: orphaned front matter list item "
                         f"at line {lineno}")
            metadata.setdefault(current_key, []).append(parse_scalar(stripped[2:]))
            continue
        if ":" not in line:
            sys.exit(f"[sync_wiki] ERROR: invalid front matter line {lineno}: "
                     f"{line}")
        key, value = line.split(":", 1)
        key = key.strip()
        value = value.strip()
        current_key = key
        if value:
            metadata[key] = parse_scalar(value)
        else:
            metadata[key] = []
    return metadata


def source_files():
    for root in SOURCE_ROOTS:
        if os.path.isdir(root):
            for dirpath, dirs, files in os.walk(root):
                dirs[:] = sorted(d for d in dirs if d != ".git")
                for fname in sorted(files):
                    if fname.endswith(".md"):
                        yield os.path.normpath(os.path.join(dirpath, fname))
        elif os.path.isfile(root):
            yield os.path.normpath(root)


def is_local_only(path):
    return os.path.normpath(path).startswith(os.path.normpath("docs/local") + os.sep)


def load_source_docs():
    docs = {}
    for path in source_files():
        metadata, body = split_front_matter(path)
        docs[path] = SourceDoc(metadata=metadata)
    return docs


def load_pages(source_docs):
    pages = []
    skipped_publishable_local = []
    cleanup_tombstones = []
    untagged = []
    for path in source_files():
        metadata, body = split_front_matter(path)
        if is_local_only(path):
            if source_docs[path].metadata.get("wiki") is True:
                skipped_publishable_local.append(path)
            continue
        if not metadata:
            untagged.append(path)
            continue
        status = metadata.get("status")
        if status and status not in VALID_STATUSES:
            sys.exit(f"[sync_wiki] ERROR: {path} has invalid status: {status}")
        if status == "remove_next_cleanup":
            cleanup_tombstones.append(path)
            continue
        if metadata.get("wiki") is not True:
            continue
        title = metadata.get("title")
        group = metadata.get("wiki_group")
        if not title:
            sys.exit(f"[sync_wiki] ERROR: {path} has wiki: true but no title")
        if group not in VALID_GROUPS:
            sys.exit(f"[sync_wiki] ERROR: {path} has invalid wiki_group: {group}")
        for key in (
            "created",
            "updated",
            "doc_type",
            "production_area",
            "department",
            "status",
            "canonical",
        ):
            if key not in metadata:
                sys.exit(f"[sync_wiki] ERROR: {path} has wiki: true but no {key}")
        if metadata.get("status") == "superseded" and not metadata.get("superseded_by"):
            sys.exit(f"[sync_wiki] ERROR: {path} is superseded but has no superseded_by")
        if metadata.get("canonical") is True and not metadata.get("canonical_for"):
            sys.exit(f"[sync_wiki] ERROR: {path} is canonical but has no canonical_for")
        name = metadata.get("wiki_page") or slugify(title)
        if not re.match(r"^[A-Za-z0-9][A-Za-z0-9-]*$", name):
            sys.exit(f"[sync_wiki] ERROR: {path} has invalid wiki_page: {name}")
        order = metadata.get("wiki_order", 999)
        if not isinstance(order, int):
            sys.exit(f"[sync_wiki] ERROR: {path} has non-integer wiki_order")
        pages.append(Page(
            src=path,
            name=name,
            group=group,
            display=title,
            order=order,
            body=body,
            created=metadata.get("created", "unknown"),
            updated=metadata.get("updated", "unknown"),
            doc_type=metadata.get("doc_type", "unknown"),
            status=metadata.get("status", "unknown"),
            canonical=metadata.get("canonical") is True,
            canonical_for=metadata.get("canonical_for"),
            superseded_by=metadata.get("superseded_by"),
        ))

    by_name = {}
    for page in pages:
        if page.name in by_name:
            sys.exit(f"[sync_wiki] ERROR: duplicate wiki_page {page.name}: "
                     f"{by_name[page.name]} and {page.src}")
        by_name[page.name] = page.src

    pages.sort(key=lambda p: (
        -1 if p.group == "Home" else GROUP_ORDER.index(p.group),
        p.order,
        p.display.lower(),
        p.src,
    ))
    home_pages = [p for p in pages if p.group == "Home"]
    if len(home_pages) != 1:
        sys.exit(f"[sync_wiki] ERROR: expected exactly one wiki_group: Home page, "
                 f"found {len(home_pages)}")

    if skipped_publishable_local:
        print(f"[sync_wiki] WARNING — {len(skipped_publishable_local)} docs/local "
              f"file(s) had wiki: true and were ignored:")
        for path in skipped_publishable_local:
            print(f"  {path}")
    if cleanup_tombstones:
        print(f"[sync_wiki] INFO — {len(cleanup_tombstones)} markdown file(s) "
              f"marked remove_next_cleanup will not be published:")
        for path in cleanup_tombstones:
            print(f"  {path}")
    if untagged:
        print(f"[sync_wiki] WARNING — {len(untagged)} markdown file(s) without "
              f"front matter were ignored:")
        for path in untagged:
            print(f"  {path}")
    return pages


def resolve_target(src, target):
    if target.startswith("/"):
        return os.path.normpath(target.lstrip("/"))
    return os.path.normpath(os.path.join(os.path.dirname(src), target))


def unpublished_reason(path, metadata):
    if is_local_only(path):
        return "docs/local/** and will not publish"
    if metadata.get("status") == "remove_next_cleanup":
        return "remove_next_cleanup and will not publish"
    if metadata.get("wiki") is False:
        return "wiki: false and will not publish"
    return None


def warn_unpublished_link(src_label, target, reason, seen_warnings):
    key = (src_label, target, reason)
    if key in seen_warnings:
        return
    seen_warnings.add(key)
    print(f"[sync_wiki] WARNING — {src_label} links to {target}, which is {reason}")


def rewrite_links(text, src, src_label, page_info, source_docs, seen_warnings):
    """Doc-to-doc links → wiki page links (plain markdown, which GitHub
    wikis resolve — no [[pipe]] syntax ambiguity); other repo-file links →
    absolute blob URLs; external links untouched. A label that is just the
    source filename is replaced by the page's display name."""
    def sub(m):
        label, target, anchor = m.group(1), m.group(2), m.group(3) or ""
        if re.match(r"^[a-z]+://|^mailto:", target):
            return m.group(0)
        resolved = resolve_target(src, target)
        if resolved in page_info:
            page, display = page_info[resolved]
            if label in (target, os.path.basename(target)):
                label = display
            return f"[{label}]({page}{anchor})"
        if resolved in source_docs:
            reason = unpublished_reason(resolved, source_docs[resolved].metadata)
            if reason:
                warn_unpublished_link(src_label, resolved, reason, seen_warnings)
        clean = resolved if not resolved.startswith("..") else target.lstrip("./")
        return f"[{label}]({REPO_URL}/blob/main/{clean}{anchor})"
    return LINK_RE.sub(sub, text)


def superseded_banner_line(page, page_info):
    if page.status != "superseded":
        return ""
    target = page.superseded_by or "unknown"
    resolved = resolve_target(page.src, target)
    if resolved in page_info:
        page_name, display = page_info[resolved]
        target = f"[{display}]({page_name})"
    elif target.endswith(".md"):
        clean = resolved if not resolved.startswith("..") else target.lstrip("./")
        target = f"[{target}]({REPO_URL}/blob/main/{clean})"
    return f"> Superseded by: {target}\n"


def main():
    p = argparse.ArgumentParser(prog="sync_wiki")
    p.add_argument("--wiki", required=True,
                   help="Path to the cloned <repo>.wiki working tree")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    wiki = os.path.abspath(args.wiki)
    if not os.path.isdir(os.path.join(wiki, ".git")):
        sys.exit(f"[sync_wiki] ERROR: {wiki} is not a git working tree")

    source_docs = load_source_docs()
    pages = load_pages(source_docs)
    rev = head_hash()
    page_info = {page.src: (page.name, page.display) for page in pages}
    generated = set()
    seen_warnings = set()

    for page in pages:
        body = rewrite_links(
            page.body,
            page.src,
            f"{page.name}.md",
            page_info,
            source_docs,
            seen_warnings,
        )
        metadata_line = (f"> Metadata: `{page.doc_type}` / `{page.status}`")
        if page.canonical:
            metadata_line += f" / canonical for `{page.canonical_for}`"
        metadata_line += f" / created `{page.created}` / updated `{page.updated}`"
        banner = (f"> Mirrored from [`{page.src}`]({REPO_URL}/blob/main/{page.src}) "
                  f"@ `{rev}` — the repo is canonical. Edit there, not "
                  f"here; hand edits are overwritten by the next sync.\n"
                  f"{superseded_banner_line(page, page_info)}"
                  f"{metadata_line}\n\n")
        out = os.path.join(wiki, f"{page.name}.md")
        generated.add(f"{page.name}.md")
        if args.dry_run:
            print(f"[sync_wiki] would write {page.name}.md  ← {page.src}")
        else:
            with open(out, "w", encoding="utf-8") as f:
                f.write(banner + body)
            print(f"[sync_wiki] wrote {page.name}.md  ← {page.src}")

    # _Sidebar: Home first, then the groups in fixed order
    side = ["**[Home](Home)**", ""]
    for group in GROUP_ORDER:
        side.append(f"**{group}**")
        for page in pages:
            if page.group == group:
                side.append(f"- [{page.display}]({page.name})")
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

    print(f"\n[sync_wiki] done — {len(generated)} pages @ {rev}. Review the "
          f"wiki working tree, then commit and push it yourself.")


if __name__ == "__main__":
    main()
