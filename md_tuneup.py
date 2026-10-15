#!/usr/bin/env python3
# md_tuneup.py v1.0 — 2026-10-15
# Changelog: v1.0 (2026-10-15): first release, built to SPEC.md v1.0.
"""MD Tune-Up: survey a folder of markdown files, flag the inconsistencies,
and fix them with your okay. Install and use: README.md. Design: SPEC.md."""

import argparse
import collections
import datetime
import difflib
import json
import os
import re
import shutil
import sys
from urllib.parse import quote, unquote

try:
    import yaml
except ImportError:
    sys.exit("MD Tune-Up needs PyYAML to read frontmatter. Install it with:\n\n"
             "  pip3 install pyyaml\n\nThen run MD Tune-Up again.")

VERSION = "1.0"
FRONTMATTER_SHARE = 0.5  # frontmatter is "the convention" when at least half the files have it
KEY_SHARE = 0.8          # a key is expected when 80% of the frontmatter files have it...
KEY_MIN_FILES = 3        # ...and there are at least this many files to judge from
LINK_CUTOFF = 0.8        # difflib similarity for a "likely match"
WIDTH = 62

SKIP_DIRS = {"node_modules", "__pycache__"}
BACKUP_DIR = re.compile(r"_backup_\d{8}_\d{4}(_\d+)?$")
PLACEHOLDERS = {"todo", "tbd", "tbc", "fixme", "xxx", "placeholder", "description", "description here",
                "add description", "add a description", "short description", "one line description",
                "write description", "coming soon", "lorem ipsum", "na", "n a", "none", "null",
                "untitled", "new note"}

GROUPS = [("yaml", "Frontmatter Error"), ("key", "Missing Frontmatter Key"),
          ("name", "Name/Filename Mismatch"), ("link", "Broken Link"),
          ("desc", "Placeholder Description")]

WIKI = re.compile(r"(!?)\[\[([^\[\]\n]+)\]\]")
MDLINK = re.compile(r"\[[^\]\n]*\]\(\s*(<[^>\n]+>|[^)\s]+)(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'))?\s*\)")
INLINE_CODE = re.compile(r"(`+)[^`\n].*?\1")
FENCE = re.compile(r"\s*(`{3,}|~{3,})")
SCHEME = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:")
OTHER_EXT = re.compile(r"\.([A-Za-z][A-Za-z0-9]{0,9})$")

VERBOSE = False
WRITING = False


# ── Small helpers ─────────────────────────────────────────────

def say(text=""):
    print(text)


def detail(text):
    if VERBOSE:
        print("    · " + text)


def plural(n, one, many=None):
    return "{} {}".format(n, one if n == 1 else (many or one + "s"))


def ask(prompt):
    try:
        return input(prompt).strip().lower()
    except EOFError:
        print()
        return "q"


def slug(text):
    """Lowercase; hyphens, underscores and spaces count as the same; .md dropped."""
    text = str(text).strip().lower()
    if text.endswith(".md"):
        text = text[:-3]
    return re.sub(r"[\s_\-]+", "-", text).strip("-")


def read_text(path):
    with open(path, encoding="utf-8", newline="") as f:
        return f.read()


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(text)


def newline_of(line):
    return "\r\n" if line.endswith("\r\n") else "\n"


def path_key(path):
    return os.path.normcase(os.path.normpath(path)).lower()


def same_path(a, b):
    return path_key(a) == path_key(b)


def frontmatter_end(lines):
    """Index of the line closing the frontmatter, or None (none there, or never closed)."""
    if not lines or lines[0].lstrip("﻿").strip() != "---":
        return None
    for i in range(1, len(lines)):
        if lines[i].strip() in ("---", "..."):
            return i
    return None


def yaml_value(value, old=""):
    """Write a string as a YAML value, keeping the old line's quote style."""
    if old.startswith("'"):
        return "'" + value.replace("'", "''") + "'"
    bare = bool(re.match(r"^[A-Za-z0-9_][A-Za-z0-9_ .\-]*$", value)) and not value.endswith(" ")
    if bare:
        try:
            bare = yaml.safe_load(value) == value
        except yaml.YAMLError:
            bare = False
    if old.startswith('"') or not bare:
        return json.dumps(value, ensure_ascii=False)
    return value


def simple_line(md, key):
    """True when `key:` sits on one line in the frontmatter, so it can be rewritten safely."""
    for line in md.lines[1:md.fm_end]:
        if re.match(re.escape(key) + r"\s*:", line):
            value = line.split(":", 1)[1].strip()
            return value != "" and value[0] not in "|>&*!"
    return False


def valid_filename(stem):
    return (bool(stem) and stem == stem.strip() and len(stem) <= 200 and not stem.startswith(".")
            and not re.search(r'[/\\:*?"<>|\x00-\x1f]', stem))


# ── Files and links ───────────────────────────────────────────

class MdFile(object):
    def __init__(self, root, path):
        self.root, self.path = root, path
        self.planned_path = None  # set when a rename is approved
        self.text, self.lines = "", []
        self.has_fm, self.fm, self.fm_end, self.fm_error = False, None, None, None
        self.links = []

    @property
    def rel(self):
        return os.path.relpath(self.path, self.root).replace(os.sep, "/")

    @property
    def stem(self):
        return os.path.splitext(os.path.basename(self.path))[0]

    def future(self):
        return self.planned_path or self.path

    def load(self):
        self.text = read_text(self.path)
        self.lines = self.text.splitlines(True)
        if not self.lines or self.lines[0].lstrip("﻿").strip() != "---":
            return
        self.has_fm = True
        self.fm_end = frontmatter_end(self.lines)
        if self.fm_end is None:
            self.fm_error = (1, "the frontmatter opens with --- but never closes", self.lines[0])
            return
        try:
            data = yaml.safe_load("".join(self.lines[1:self.fm_end]))
        except yaml.YAMLError as e:
            mark = getattr(e, "problem_mark", None)
            n = mark.line + 2 if mark is not None else 1
            n = max(1, min(n, self.fm_end - 1))
            problem = getattr(e, "problem", None) or str(e).split("\n")[0]
            self.fm_error = (n, problem, self.lines[n - 1])
            return
        if data is None:
            data = {}
        if not isinstance(data, dict):
            self.fm_error = (2, "the frontmatter isn't a set of key: value lines", self.lines[1])
            return
        self.fm = data


class Link(object):
    def __init__(self, md, line, kind, raw, **info):
        self.md, self.line, self.kind, self.raw = md, line, kind, raw
        self.target, self.ok = None, False
        self.__dict__.update(info)


class Index(object):
    def __init__(self, files):
        self.files = files
        self.by_stem = collections.defaultdict(list)
        self.by_rel, self.paths = {}, {}
        for f in files:
            self.by_stem[slug(f.stem)].append(f)
            self.by_rel[slug(f.rel)] = f
            self.paths[path_key(f.path)] = f


def find_files(root):
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d not in SKIP_DIRS
                             and not BACKUP_DIR.search(d))
        for name in sorted(filenames):
            if name.lower().endswith(".md") and not name.startswith("."):
                found.append(os.path.join(dirpath, name))
    return found


def each_link(text, fn):
    """Call fn(line_no, kind, match, raw) for every [[wiki-link]] and relative .md link
    outside code. Where fn returns a string, the link is replaced with it.
    Returns (text, number of links replaced)."""
    out, changed, fence = [], 0, None
    for n, line in enumerate(text.splitlines(True), 1):
        m = FENCE.match(line)
        if fence:
            if m and m.group(1)[0] == fence[0] and len(m.group(1)) >= len(fence) \
                    and not line.strip().strip(fence[0]):
                fence = None
            out.append(line)
            continue
        if m:
            fence = m.group(1)
            out.append(line)
            continue
        masked = INLINE_CODE.sub(lambda c: " " * len(c.group(0)), line)
        hits = [("wiki", h) for h in WIKI.finditer(masked)] + [("md", h) for h in MDLINK.finditer(masked)]
        for kind, h in sorted(hits, key=lambda x: x[1].start(), reverse=True):
            raw = line[h.start():h.end()]
            new = fn(n, kind, h, raw)
            if new is not None and new != raw:
                line = line[:h.start()] + new + line[h.end():]
                changed += 1
        out.append(line)
    return "".join(out), changed


def parse_wiki(h):
    """[[name#heading|alias]] -> (embed mark, name, the rest after the name)."""
    embed, inner = h.group(1), h.group(2)
    name = re.match(r"[^|#^]*", inner).group(0)
    rest = inner[len(name):]
    if name.endswith("\\"):  # [[note\|alias]] inside a table
        name, rest = name[:-1], "\\" + rest
    return embed, name.strip(), rest


def is_md_name(name):
    m = OTHER_EXT.search(name)
    return not m or m.group(1).lower() == "md"


def parse_md(md, h):
    """A relative link to a .md file -> dict(path, anchor, angle, full, tok); else None."""
    tok = h.group(1)
    angle = tok.startswith("<")
    path = tok[1:-1] if angle else tok
    if SCHEME.match(path) or path.startswith(("/", "#")):
        return None
    path, _, anchor = path.partition("#")
    if not path.lower().endswith(".md"):
        return None
    full = os.path.normpath(os.path.join(os.path.dirname(md.path), unquote(path)))
    return dict(path=path, anchor=anchor, angle=angle, full=full,
                tok=(h.start(1) - h.start(0), h.end(1) - h.start(0)))


def resolve_wiki(name, index):
    key = slug(name)
    if "/" in key:
        for rel, f in index.by_rel.items():
            if rel == key or rel.endswith("/" + key):
                return f
        return None
    hits = index.by_stem.get(key)
    return hits[0] if hits else None


def wiki_text(embed, name, rest, target_path, root):
    rel = os.path.splitext(os.path.relpath(target_path, root).replace(os.sep, "/"))[0]
    new = rel if "/" in name else rel.rsplit("/", 1)[-1]
    if name.lower().endswith(".md"):
        new += ".md"
    return embed + "[[" + new + rest + "]]"


def md_text(from_md, raw, link, target_path):
    rel = os.path.relpath(target_path, os.path.dirname(from_md.path)).replace(os.sep, "/")
    if link["path"].startswith("./") and not rel.startswith("../"):
        rel = "./" + rel
    if "%" in link["path"]:
        rel = quote(rel, safe="/._-~")
    tok = rel + ("#" + link["anchor"] if link["anchor"] else "")
    if link["angle"] or " " in tok:
        tok = "<" + tok + ">"
    start, end = link["tok"]
    return raw[:start] + tok + raw[end:]


def collect_links(files, index):
    for f in files:
        def found(n, kind, h, raw, f=f):
            if kind == "wiki":
                embed, name, rest = parse_wiki(h)
                if name and is_md_name(name):
                    link = Link(f, n, kind, raw, col=h.start(), embed=embed, name=name, rest=rest)
                    link.target = resolve_wiki(name, index)
                    link.ok = link.target is not None
                    f.links.append(link)
            else:
                parsed = parse_md(f, h)
                if parsed:
                    link = Link(f, n, kind, raw, col=h.start(), md_info=parsed)
                    link.ok = os.path.isfile(parsed["full"])
                    link.target = index.paths.get(path_key(parsed["full"])) if link.ok else None
                    f.links.append(link)
            return None
        each_link(f.text, found)
        f.links.sort(key=lambda link: (link.line, link.col))


def suggest(key, index, basename=None):
    """Files a missing link target might mean -> (files, why)."""
    if basename:
        same = [f for f in index.files if os.path.basename(f.path).lower() == basename.lower()]
        if same:
            return same, "same filename, in another folder"
    named = []
    for f in index.files:
        if not f.fm:
            continue
        if slug(f.fm.get("name") or "") == key:
            named.append((f, 'its name field is "{}"'.format(f.fm.get("name"))))
            continue
        aliases = f.fm.get("aliases") or []
        aliases = [aliases] if isinstance(aliases, str) else aliases
        if isinstance(aliases, list) and key in [slug(a) for a in aliases if a is not None]:
            named.append((f, "it lists that name as an alias"))
    if named:
        return [f for f, _ in named], named[0][1]
    words = sorted(key.split("-"))
    reordered = [f for f in index.files if sorted(slug(f.stem).split("-")) == words]
    if reordered:
        return reordered, "same words, different order"
    close = difflib.get_close_matches(key, list(index.by_stem), n=3, cutoff=LINK_CUTOFF)
    return [f for k in close for f in index.by_stem[k]], "closest filename"


# ── Fixes ─────────────────────────────────────────────────────

class FixError(Exception):
    pass


class Fix(object):
    order = 0

    def approve(self):
        pass


class SetName(Fix):
    order = 0

    def __init__(self, md, value):
        self.md, self.value = md, value

    def plan(self):
        return "Update name field in {}".format(self.md.rel)

    def apply(self):
        lines = read_text(self.md.path).splitlines(True)
        for i in range(1, frontmatter_end(lines) or 0):
            if re.match(r"name\s*:", lines[i]):
                old = lines[i].split(":", 1)[1].strip()
                lines[i] = "name: " + yaml_value(self.value, old) + newline_of(lines[i])
                write_text(self.md.path, "".join(lines))
                return "Updated: {} (name field)".format(self.md.rel), {self.md.path}
        raise FixError("the name line isn't there any more")


class RenameFile(Fix):
    order = 1

    def __init__(self, md, new_stem, index, inbound):
        self.md, self.new_stem, self.index, self.inbound = md, new_stem, index, inbound

    def target(self):
        return os.path.join(os.path.dirname(self.md.path), self.new_stem + ".md")

    def approve(self):
        self.md.planned_path = self.target()

    def plan(self):
        text = "Rename {} → {}.md".format(self.md.rel, self.new_stem)
        if self.inbound:
            text += " and update the {} to it".format(plural(self.inbound, "link"))
        return text

    def apply(self):
        old, new = self.md.path, self.target()
        if os.path.exists(new) and not same_path(old, new):
            raise FixError("{}.md already exists".format(self.new_stem))
        old_rel = self.md.rel
        os.rename(old, new)
        self.md.path = new
        changed, count = {new}, 0
        for f in self.index.files:
            text, n = each_link(read_text(f.path), lambda ln, kind, h, raw: relink(f, kind, h, raw, old, new))
            if n:
                write_text(f.path, text)
                changed.add(f.path)
                count += n
        note = " ({} updated)".format(plural(count, "link")) if count else ""
        return "Renamed: {} → {}{}".format(old_rel, self.md.rel, note), changed


def relink(f, kind, h, raw, old, new):
    """Point a link at the renamed file, if it pointed at the old name."""
    if kind == "md":
        parsed = parse_md(f, h)
        if parsed and same_path(parsed["full"], old):
            return md_text(f, raw, parsed, new)
        return None
    embed, name, rest = parse_wiki(h)
    if not name or not is_md_name(name):
        return None
    key, old_rel = slug(name), slug(os.path.relpath(old, f.root))
    if "/" in key:
        hit = old_rel == key or old_rel.endswith("/" + key)
    else:
        hit = key == old_rel.rsplit("/", 1)[-1]
    return wiki_text(embed, name, rest, new, f.root) if hit else None


class FixLink(Fix):
    order = 2

    def __init__(self, link, target):
        self.link, self.target = link, target

    def new_raw(self):
        link = self.link
        if link.kind == "wiki":
            return wiki_text(link.embed, link.name, link.rest, self.target.future(), link.md.root)
        return md_text(link.md, link.raw, link.md_info, self.target.future())

    def plan(self):
        return "Fix link {} → {} in {}".format(self.link.raw, self.new_raw(), self.link.md.rel)

    def apply(self):
        md, raw, new = self.link.md, self.link.raw, self.new_raw()
        text = read_text(md.path)
        lines = text.splitlines(True)
        i = self.link.line - 1
        if i < len(lines) and raw in lines[i]:
            lines[i] = lines[i].replace(raw, new, 1)
            text = "".join(lines)
        elif text.count(raw) == 1:
            text = text.replace(raw, new)
        else:
            raise FixError("the link isn't where it was any more")
        write_text(md.path, text)
        return "Updated: {} (link fix)".format(md.rel), {md.path}


class AddKey(Fix):
    order = 3

    def __init__(self, md, key, value):
        self.md, self.key, self.value = md, key, value

    def plan(self):
        return 'Add missing "{}" key to {}'.format(self.key, self.md.rel)

    def apply(self):
        lines = read_text(self.md.path).splitlines(True)
        end = frontmatter_end(lines)
        if end is None:
            raise FixError("the frontmatter isn't there any more")
        if any(re.match(re.escape(self.key) + r"\s*:", line) for line in lines[1:end]):
            raise FixError('it has a "{}" key now'.format(self.key))
        lines.insert(end, "{}: {}{}".format(yaml_value(self.key), self.value, newline_of(lines[0])))
        write_text(self.md.path, "".join(lines))
        return "Updated: {} (added {} key)".format(self.md.rel, self.key), {self.md.path}


# ── Checks ────────────────────────────────────────────────────

class Item(object):
    def __init__(self, group, md, body, options=()):
        self.group, self.md, self.body, self.options = group, md, body, list(options)


def yaml_hint(problem):
    if "mapping values are not allowed" in problem:
        return ["A colon inside a value is the usual cause: put the value", "in quotes."]
    if "'\\t'" in problem or "tab" in problem:
        return ["YAML doesn't allow tabs here: use spaces."]
    if "never closes" in problem:
        return ["Add a line with just --- where the frontmatter ends."]
    if "expected ':'" in problem or "quoted scalar" in problem:
        return ["A line is missing its colon, or a quote isn't closed."]
    return ["Fixing it by hand is safer than letting a tool guess."]


def check_frontmatter(with_fm, parsed, items):
    for f in with_fm:
        if f.fm_error:
            n, problem, source = f.fm_error
            body = ["File: {}, line {}".format(f.rel, n), "YAML says: " + problem, "",
                    "  {:>3} | {}".format(n, source.rstrip("\r\n")), "",
                    "The frontmatter can't be read, so the other checks skip this",
                    "file. It needs a fix by hand."] + yaml_hint(problem)
            items.append(Item("yaml", f, body))
    if len(parsed) < KEY_MIN_FILES:
        detail("Too few frontmatter files to tell which keys are expected; skipping missing keys")
        return
    counts = collections.Counter(k for f in parsed for k in f.fm if isinstance(k, str))
    expected = sorted((k for k, c in counts.items() if c >= KEY_SHARE * len(parsed)),
                      key=lambda k: (-counts[k], k))
    detail("Expected keys (in {}% or more of {}): {}".format(
        int(KEY_SHARE * 100), plural(len(parsed), "file"), ", ".join(expected) or "none"))
    for f in parsed:
        for key in expected:
            if key in f.fm:
                continue
            if key == "name":
                value = yaml_value(f.stem)
                label = "Add name: {} (from the filename)".format(value)
            else:
                kinds = collections.Counter(type(g.fm[key]).__name__ for g in parsed if key in g.fm)
                value = {"list": "[]", "dict": "{}"}.get(kinds.most_common(1)[0][0], '""')
                label = "Add {}: {} (empty, for you to fill in)".format(key, value)
            body = ["File: " + f.rel, "Missing: " + key, "",
                    '"{}" is in {} of {} files with frontmatter. This one'.format(key, counts[key], len(parsed)),
                    "doesn't have it."]
            items.append(Item("key", f, body, [(label, AddKey(f, key, value))]))


def check_names(named, index, items):
    for f in named:
        value = f.fm.get("name")
        if value is None or isinstance(value, (list, dict)) or not str(value).strip():
            continue
        value = str(value).strip()
        folder = os.path.basename(os.path.dirname(f.path))
        if slug(value) in (slug(f.stem), slug(folder)):  # SKILL.md named after its folder is fine
            continue
        options = []
        if simple_line(f, "name"):
            options.append(('Update name to "{}" (match the file)'.format(f.stem), SetName(f, f.stem)))
        new_stem = value[:-3] if value.lower().endswith(".md") else value
        inbound = sum(1 for g in index.files for link in g.links if link.target is f)
        if valid_filename(new_stem) and not os.path.exists(os.path.join(os.path.dirname(f.path), new_stem + ".md")):
            options.append(('Rename file to "{}.md" (match the name)'.format(new_stem),
                            RenameFile(f, new_stem, index, inbound)))
        body = ["File: " + f.rel, 'name: "{}"'.format(value), "",
                "The frontmatter name doesn't match the filename."]
        if inbound and len(options) == 2:
            body.append("{} to this file; renaming updates {} too.".format(
                plural(inbound, "link points", "links point"), "it" if inbound == 1 else "them"))
        if not options:
            body.append("Change one of them by hand so they agree.")
        items.append(Item("name", f, body, options))


def check_links(files, index, items):
    total = sum(len(f.links) for f in files)
    broken = [link for f in files for link in f.links if not link.ok]
    detail("Checked {}; {} lead nowhere".format(plural(total, "link"), len(broken)))
    for link in broken:
        f = link.md
        if link.kind == "wiki":
            name = link.name if link.name.lower().endswith(".md") else link.name + ".md"
            missing = "There's no {} in this folder.".format(name)
            cands, why = suggest(slug(link.name), index)
        else:
            path = link.md_info["path"]
            missing = "Nothing at {} (from this file's folder).".format(path)
            base = os.path.basename(unquote(path))
            cands, why = suggest(slug(base), index, basename=base)
        body = ["File: {}, line {}".format(f.rel, link.line), "Link: " + link.raw, "", missing]
        options = []
        if len(cands) == 1:
            body.append("Likely match: {} ({})".format(cands[0].rel, why))
            fix = FixLink(link, cands[0])
            options.append(("Change the link to " + fix.new_raw(), fix))
        elif cands:
            body.append("Possible matches: {} ({}).".format(", ".join(c.rel for c in cands), why))
            body.append("Pick one and fix the link by hand.")
        else:
            body.append("Nothing close enough to suggest. Fix or remove the link by")
            body.append("hand; if that note is still to be written, leave it.")
        items.append(Item("link", f, body, options))


def check_descriptions(described, items):
    for f in described:
        d = f.fm.get("description")
        if isinstance(d, (list, dict)):
            continue
        text = "" if d is None else str(d).strip()
        norm = re.sub(r"[^a-z0-9]+", " ", text.lower()).strip()
        if not text:
            shown, why = "(empty)", "This description is empty."
        elif slug(text) in (slug(f.stem), slug(f.fm.get("name") or "")):
            shown, why = '"{}"'.format(text), "This looks like a placeholder — it just repeats the filename."
        elif not norm or norm in PLACEHOLDERS or norm.split()[0] in ("todo", "tbd", "fixme"):
            shown, why = '"{}"'.format(text), "This looks like a placeholder."
        else:
            continue
        items.append(Item("desc", f, ["File: " + f.rel, "description: " + shown, "", why,
                                      "Consider writing a real one-line description of what this file",
                                      "covers."]))


# ── The walk-through ──────────────────────────────────────────

def show(item, n, total, preview):
    head = "── {} ({} of {}) ".format(dict(GROUPS)[item.group], n, total)
    say()
    say(head + "─" * max(3, WIDTH - len(head)))
    say()
    for line in item.body:
        say("  " + line if line else "")
    if item.options:
        say()
        for i, (label, _) in enumerate(item.options, 1):
            say("  [{}] {}".format(i, label))
        if not preview:
            say("  [s] Skip")
            say("  [q] Quit (no more changes)")
    say()


def choose(count):
    valid = [str(i) for i in range(1, count + 1)] + ["s", "q"]
    while True:
        answer = ask("  Choice: ")
        if answer in valid:
            return answer
        say("  Type {} or q.".format(", ".join(valid[:-1])))


def walk(items, preview=False):
    approved = []
    for key, _ in GROUPS:
        group = [i for i in items if i.group == key]
        for n, item in enumerate(group, 1):
            show(item, n, len(group), preview)
            if preview:
                continue
            if not item.options:
                if ask("  [Enter] Next ") == "q":
                    return approved
                continue
            answer = choose(len(item.options))
            if answer == "q":
                return approved
            if answer == "s":
                say("  Skipped.")
                continue
            fix = item.options[int(answer) - 1][1]
            fix.approve()
            approved.append(fix)
            say("  ✓ Approved.")
    return approved


def backup_path(root):
    base = root.rstrip(os.sep) + "_backup_" + datetime.datetime.now().strftime("%Y%m%d_%H%M")
    dest, n = base, 1
    while os.path.exists(dest):
        n += 1
        dest = "{}_{}".format(base, n)
    return dest


def make_backup(root, paths, dest):
    for path in paths:
        target = os.path.join(dest, os.path.relpath(path, root))
        os.makedirs(os.path.dirname(target), exist_ok=True)
        shutil.copy2(path, target)


def apply_all(root, paths, approved, no_backup):
    global WRITING
    approved.sort(key=lambda fix: fix.order)
    backup = None if no_backup else backup_path(root)
    say()
    say("You approved {}. Here's what will happen:".format(plural(len(approved), "change")))
    say()
    steps = (["Back up folder to {}{}".format(backup, os.sep)] if backup else []) + [f.plan() for f in approved]
    for i, step in enumerate(steps, 1):
        say("  {}. {}".format(i, step))
    say()
    while True:
        answer = ask("Proceed? [y/n] ")
        if answer in ("y", "yes"):
            break
        if answer in ("n", "no", "q"):
            say("Okay. Nothing was written.")
            return 0
    say()
    if backup:
        try:
            make_backup(root, paths, backup)
        except OSError as e:
            say("  ✗ Backup failed: {}".format(e))
            say()
            say("Nothing was changed, because the backup didn't work.")
            return 1
        say("  ✓ Backup created")
    WRITING = True
    changed, failed = set(), 0
    for fix in approved:
        try:
            message, touched = fix.apply()
            changed |= touched
            say("  ✓ " + message)
        except (FixError, OSError, UnicodeDecodeError) as e:
            failed += 1
            say("  ✗ {}: {}".format(fix.plan(), e))
    say()
    summary = "Done. {} changed.".format(plural(len(changed), "file"))
    if failed:
        summary += " {} couldn't be made (marked ✗ above).".format(plural(failed, "change"))
    if backup:
        say(summary + " Backup at:")
        say("  {}{}".format(backup, os.sep))
    else:
        say(summary)
    return 1 if failed else 0


# ── Main ──────────────────────────────────────────────────────

def main(argv=None):
    global VERBOSE
    parser = argparse.ArgumentParser(
        prog="md_tuneup.py",
        description="Survey a folder of markdown files, flag the inconsistencies, and fix them "
                    "with your okay. Nothing is written until you approve it.",
        epilog="examples:\n  python3 md_tuneup.py ~/my-notes --dry-run\n  python3 md_tuneup.py .",
        formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("folder", nargs="?", default=".", help="folder to scan (default: the current folder)")
    parser.add_argument("--dry-run", action="store_true", help="scan and report only: no fixes, no backup")
    parser.add_argument("--no-backup", action="store_true", help="skip the automatic backup before applying fixes")
    parser.add_argument("--verbose", action="store_true", help="extra detail on what each check is doing")
    parser.add_argument("--version", action="version", version="MD Tune-Up v" + VERSION)
    args = parser.parse_args(argv)
    VERBOSE = args.verbose
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")
        except (AttributeError, ValueError):
            pass

    root = os.path.abspath(os.path.expanduser(args.folder))
    say("MD Tune-Up v" + VERSION)
    say()
    if not os.path.isdir(root):
        say("{} is a file. Point MD Tune-Up at the folder that holds your markdown files.".format(root)
            if os.path.exists(root) else "Can't find that folder: " + root)
        return 2

    # Phase 1: scan
    say("Scanning: " + root)
    paths = find_files(root)
    files, unreadable = [], []
    for path in paths:
        md = MdFile(root, path)
        try:
            md.load()
            files.append(md)
        except (UnicodeDecodeError, OSError):
            unreadable.append(md.rel)
    say("Found {}.".format(plural(len(paths), "markdown file")))
    if unreadable:
        say("  (Skipping {} that can't be read as UTF-8 text: {})".format(
            plural(len(unreadable), "file"), ", ".join(unreadable)))
    if not files:
        say()
        say("Nothing to tune up. Check the path, or point MD Tune-Up at the folder")
        say("that holds your .md files.")
        return 0

    index = Index(files)
    collect_links(files, index)
    total = len(files)
    with_fm = [f for f in files if f.has_fm]
    parsed = [f for f in with_fm if f.fm is not None]
    fm_on = len(with_fm) >= FRONTMATTER_SHARE * total
    named = [f for f in parsed if "name" in f.fm] if fm_on else []
    described = [f for f in parsed if "description" in f.fm] if fm_on else []
    wiki_files = [f for f in files if any(link.kind == "wiki" for link in f.links)]
    md_files = [f for f in files if any(link.kind == "md" for link in f.links)]

    say()
    say("Detecting conventions...")
    share = "{} of {} files ({}%)".format(len(with_fm), total, round(100 * len(with_fm) / total))
    if fm_on:
        say("  ✓ Frontmatter: {} — will check frontmatter".format(share))
        for f in files:
            if not f.has_fm:
                detail("No frontmatter, left alone: " + f.rel)
    else:
        detail("Frontmatter: {} — under half, so it isn't checked".format(share))
    if wiki_files:
        say("  ✓ Wiki-links: {} [[links]] — will check for broken links".format(
            plural(len(wiki_files), "file uses", "files use")))
    if md_files:
        say("  ✓ Markdown links: {} to other .md files — will check for broken links".format(
            plural(len(md_files), "file links", "files link")))
    if named:
        say("  ✓ Name field: {} — will check name/filename agreement".format(plural(len(named), "file")))
    if described:
        say("  ✓ Description field: {} — will check for placeholders".format(plural(len(described), "file")))
    if not (fm_on or wiki_files or md_files):
        say("  No frontmatter, no [[wiki-links]], no links between files.")
        say()
        say("Nothing to tune up. These are plain markdown files, and MD Tune-Up")
        say("only checks conventions a folder actually uses.")
        return 0

    say()
    say("Running checks...")
    items = []
    if fm_on:
        check_frontmatter(with_fm, parsed, items)
        check_names(named, index, items)
        check_descriptions(described, items)
    if wiki_files or md_files:
        check_links(files, index, items)

    # Phase 2: summary
    say()
    if not items:
        say("Done. Everything checks out — nothing to tune up.")
        return 0
    count = collections.Counter(i.group for i in items)
    say("Done. Found {} across {}:".format(plural(len(items), "item"),
                                           plural(len({i.md.path for i in items}), "file")))
    say()
    if fm_on:
        parts = []
        if count["yaml"]:
            parts.append(plural(count["yaml"], "YAML error"))
        if count["key"]:
            parts.append(plural(count["key"], "missing key"))
        say("  {:<22}{:>2}{}".format("Frontmatter issues:", count["yaml"] + count["key"],
                                     "  ({})".format(", ".join(parts)) if parts else ""))
    if named:
        say("  {:<22}{:>2}".format("Name mismatches:", count["name"]))
    if wiki_files or md_files:
        say("  {:<22}{:>2}".format("Broken links:", count["link"]))
    if described:
        say("  {:<22}{:>2}{}".format("Placeholder descs:", count["desc"],
                                     "  (flag only — no auto-fix)" if count["desc"] else ""))
    say()
    fixable = sum(1 for i in items if i.options)
    flagged = len(items) - fixable
    if fixable and flagged:
        say("{} fixable. {} {} flag-only (shown for your review).".format(
            plural(fixable, "item is", "items are"), flagged, "is" if flagged == 1 else "are"))
    elif fixable:
        say("It's fixable." if fixable == 1 else "All {} are fixable.".format(fixable))
    else:
        say("None can be fixed automatically. Each is shown for your review.")

    if args.dry_run:
        say()
        say("Dry run: here's each item. Nothing will be changed.")
        walk(items, preview=True)
        say("Dry run complete. Nothing was changed. Run again without --dry-run")
        say("to walk through the fixes.")
        return 0

    # Phase 3: walk-through
    say()
    say("I'll walk you through each one. For fixable items, you can approve,")
    say("skip, or quit at any time. Nothing is written until you approve it.")
    say()
    if ask("Ready? Press Enter to start, or 'q' to quit. ") == "q":
        say("Okay. Nothing was written.")
        return 0
    approved = walk(items)
    if not approved:
        say()
        say("No changes approved. Nothing was written.")
        return 0

    # Phase 4: apply
    return apply_all(root, paths, approved, args.no_backup)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print()
        print("\nStopped. " + ("Changes made before you stopped are listed above; the backup has the originals."
                               if WRITING else "Nothing was written."))
        sys.exit(130)
