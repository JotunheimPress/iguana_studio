#!/usr/bin/env bash
# Publishes docs/wiki/ to the repo's GitHub wiki (github.com/<owner>/iguana_studio/wiki).
# Adapted from AI Ecosystem's docs/publish-wiki.sh: same build, this repo's branch and name.
#
#   docs/publish-wiki.sh             build, show what changes, commit and push it
#   docs/publish-wiki.sh --dry-run   build and show what would change; push nothing
#   docs/publish-wiki.sh --out DIR   only build the pages into DIR, to read them; no git
#
# docs/wiki/ is the source and stays the source: it is reviewed in PRs with the code it
# describes, and the GitHub wiki is a generated copy. Edits made on GitHub are overwritten
# by the next publish (every page's footer says so). The GitHub wiki is its own git repo
# (<repo>.wiki.git); this clones it, replaces every page, and pushes one commit.
#
# What the build changes, since a wiki is flat and has no files around it:
#   * page names come from each page's title: getting-started.md -> Getting-started,
#     README.md -> Home. The title line itself is dropped (GitHub shows the name as one).
#   * links between pages point at those names, anchors kept.
#   * links out of docs/wiki/ (../../comfyui-auto/CLAUDE.md, ../../comfyui-auto/workflows/)
#     point at the file or folder on GitHub, on the default branch (main).
#   * _Sidebar.md lists the pages, from the tables on the home page; _Footer.md names the
#     release (the newest vX.Y.Z tag in HEAD's history) and commit the pages were built from.
#
# Publishes what is committed: refuses if docs/wiki/ has uncommitted changes.
set -euo pipefail

DRY=0 OUT=""
case "${1:-}" in
  --dry-run|-n) DRY=1 ;;
  --out) OUT="${2:?--out needs a directory}"; mkdir -p "$OUT"; OUT="$(cd "$OUT" && pwd)" ;;
  "") ;;
  -h|--help) sed -n 2,24p "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
  *) echo "unknown option: $1 (try --help)" >&2; exit 1 ;;
esac

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"
if [[ -z "$OUT" && -n "$(git status --porcelain -- docs/wiki)" ]]; then
  echo "docs/wiki/ has uncommitted changes: commit them first, so the wiki matches a commit." >&2
  exit 1
fi

ORIGIN="$(git remote get-url origin)"
SLUG="$(sed -E 's#^(https://github\.com/|git@github\.com:)##; s#\.git$##' <<<"$ORIGIN")"
WIKI_URL="https://github.com/$SLUG.wiki.git"
# No VERSION file here: releases are tags, so the release is the newest one HEAD contains.
VERSION="$(git describe --tags --abbrev=0 --match 'v[0-9]*' 2>/dev/null || echo unreleased)"
BRANCH="$(git symbolic-ref --short refs/remotes/origin/HEAD 2>/dev/null | sed 's|^origin/||')"
BRANCH="${BRANCH:-main}"
COMMIT="$(git rev-parse --short HEAD)"

if [[ -n "$OUT" ]]; then
  PAGES="$OUT"
else
  WORK="$(mktemp -d)"
  trap 'rm -rf "$WORK"' EXIT
  PAGES="$WORK/wiki"
  git clone -q "$WIKI_URL" "$PAGES" || {
    echo "couldn't clone $WIKI_URL — is the wiki enabled, with at least one page?" >&2; exit 1; }
fi
find "$PAGES" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +

python3 - "$ROOT/docs/wiki" "$PAGES" "$SLUG" "$VERSION" "$COMMIT" "$BRANCH" <<'PY'
import re, sys
from pathlib import Path

src, out, slug, version, commit, branch = Path(sys.argv[1]), Path(sys.argv[2]), *sys.argv[3:]
blob = f"https://github.com/{slug}/blob/{branch}/"
tree = f"https://github.com/{slug}/tree/{branch}/"

def title(text):
    m = re.search(r"^# (.+)$", text, re.M)
    return m.group(1).strip() if m else None

def page_name(path, text):
    if path.name == "README.md":
        return "Home"
    t = title(text) or path.stem.replace("-", " ")
    t = re.sub(r"\s*\([^)]*\)", "", t).replace("`", "").strip()
    return re.sub(r"[^A-Za-z0-9]+", "-", t).strip("-")

pages = {p.name: p.read_text() for p in sorted(src.glob("*.md"))}
names = {f: page_name(src / f, t) for f, t in pages.items()}
if len(set(names.values())) != len(names):
    sys.exit(f"two pages would get the same wiki name: {names}")

def link(m):
    text, target = m.group(1), m.group(2)
    if re.match(r"[a-z]+:|#", target):
        return m.group(0)                            # web links and same-page anchors
    path, _, anchor = target.partition("#")
    anchor = f"#{anchor}" if anchor else ""
    if path in names:
        return f"[{text}]({names[path]}{anchor})"
    if path.startswith("../../"):
        rel = path[len("../../"):]
        return f"[{text}]({(tree if rel.endswith('/') or not rel else blob) + rel}{anchor})"
    sys.exit(f"don't know where this link goes: {target}")

LINK = re.compile(r"(?<!!)\[([^\]]+)\]\(([^)\s]+)\)")
for f, text in pages.items():
    body = re.sub(r"\A# .+\n+", "", text) if f != "README.md" else text
    (out / f"{names[f]}.md").write_text(LINK.sub(link, body))

# The sidebar: the home page's tables (| [Page](x.md) | … |), under their ## headings.
side = ["**[Iguana Studio wiki](Home)**", ""]
for line in pages["README.md"].splitlines():
    if line.startswith("## ") and "guide" in line.lower():
        side += ["", f"**{line[3:].strip()}**", ""]
    m = re.match(r"\|\s*\[([^\]]+)\]\(([^)#]+)\)", line)
    if m and m.group(2) in names:
        side.append(f"- [{m.group(1)}]({names[m.group(2)]})")
side += ["", "---", "", f"[Releases](https://github.com/{slug}/releases) · [Repo](https://github.com/{slug})"]
(out / "_Sidebar.md").write_text("\n".join(side) + "\n")
(out / "_Footer.md").write_text(
    f"Iguana Studio {version} · built from [`docs/wiki/`]({tree}docs/wiki) at "
    f"[`{commit}`](https://github.com/{slug}/commit/{commit}). Edit it there, in a PR: "
    "changes made here are overwritten by the next publish.\n")
print(f"built {len(pages)} pages: " + ", ".join(sorted(names.values())))
PY

[[ -n "$OUT" ]] && { echo "pages in $OUT"; exit 0; }
cd "$PAGES"
git add -A
if git diff --cached --quiet; then
  echo "the wiki is already up to date with $COMMIT"; exit 0
fi
git diff --cached --stat | tail -n 20
if ((DRY)); then
  echo "dry run: nothing pushed"; exit 0
fi
git commit -q -m "Publish docs/wiki/ at $COMMIT (Iguana Studio $VERSION)"
git push -q origin HEAD
echo "published: https://github.com/$SLUG/wiki"
