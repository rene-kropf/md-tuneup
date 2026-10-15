<!--
SPEC.md v1.1 — 2026-10-15
Changelog:
- v1.1 (2026-10-15): Version header moved into this comment so GitHub opens on the title.
- v1.0 (2026-10-15): Initial spec from settled decisions.
-->

# MD Tune-Up — v1 Specification

## What it is

A command-line Python tool that surveys a folder of markdown files, flags
inconsistencies, and applies fixes with the user's approval. Run it
occasionally — like a tune-up for the files your AI reads.

**Not** a linter. Not a formatter. Those exist (Prettier, markdownlint). This
catches the structural drift that happens when a human maintains context files
over months: frontmatter that went stale, filenames that stopped matching
content, links that point nowhere, descriptions that say nothing.

## Who it's for

Anyone who relies on AI daily — not just builders — and feeds it markdown
files (memory files, project notes, context docs). The pitch: your AI is only
as consistent as the context you feed it. Most drift is mess on your side, not
the model's. This is the tune-up for that.

## Design principles

1. **Adapt to the folder, never impose a format.** Every check is conditional
   on what the folder actually contains. If no files use frontmatter, skip
   frontmatter checks. If no files use `[[wiki-links]]`, skip link checks. A
   clean plain-markdown folder should get "nothing to tune up," not warnings
   about conventions it never adopted.

2. **Verbose and communicative.** The tool holds the user's hand. It narrates
   what it's doing at every stage. Never "type a command and stare at a blank
   screen." This verbosity is what lets a non-technical user copy-paste into a
   terminal — it removes the need for a GUI.

3. **Zero config.** No config file required. Sensible defaults. A few optional
   CLI flags (`--dry-run`, `--folder`, `--no-backup`). Run it, point it at a
   folder, go.

4. **Draft-then-approve.** The tool never writes without asking. It scans,
   builds a list of proposed changes, then walks the user through them for
   approval before touching any file.

5. **Safety first.** Auto-creates a timestamped backup of the folder before
   any write operation. Don't rely on the user having git. `--dry-run` is
   always available for a no-touch preview.

---

## v1 check set

Four checks. Each is conditional — only runs if the convention is detected in
the folder.

### Check 1: Frontmatter validity

**Condition:** At least N files (e.g., ≥50% of `.md` files) have YAML
frontmatter (`---` delimited block at top of file).

**What it checks:**
- Frontmatter parses as valid YAML (no syntax errors)
- Required keys are present *if* a consensus set is detected (e.g., if 80%+
  of files have `name`, `description`, `aliases`, flag files missing any of
  those)
- `name` value matches the filename stem (see Check 2)
- `description` is non-empty and non-placeholder (see Check 4)

**Fixes offered:**
- YAML syntax errors: flag only (too risky to auto-fix; show the error and
  the line)
- Missing keys: offer to add the key with a placeholder value the user fills
  in, or skip

### Check 2: Name/filename agreement

**Condition:** Frontmatter with a `name` field exists.

**What it checks:**
- The `name` value in frontmatter matches the filename stem. Matching is
  slug-normalized: lowercase, hyphens and underscores treated as equivalent,
  `.md` extension stripped. So `name: my-project` in `my_project.md` is fine.
  `name: old-name` in `new-name.md` is a mismatch.

**Fixes offered:**
- Update the `name` field to match the filename (default), OR
- Rename the file to match the `name` field
- User picks per occurrence

### Check 3: Broken internal links

**Condition:** At least one file uses `[[wiki-links]]` or relative markdown
links (`[text](./path.md)`). The tool detects which convention is in use.

**What it checks:**
- `[[target]]` — does `target.md` (or a slug-normalized match) exist in the
  folder?
- `[text](./relative/path.md)` — does the path resolve?
- Does NOT check external URLs (that's a different tool).

**Fixes offered:**
- If a likely match exists (e.g., `[[old-name]]` and `new-name.md` is the
  only close match by edit distance or alias): offer to update the link
- If no match: flag only, with the file and line number

### Check 4: Empty/placeholder descriptions

**Condition:** Frontmatter with a `description` field exists.

**What it checks:**
- Description is not empty, not whitespace-only
- Description is not a placeholder pattern: e.g., exactly equals the filename,
  equals "TODO", "TBD", "Description here", or similar short generic strings

**Fixes offered:**
- Flag only. The tool can't write a good description — that's the human's job
  (or their AI's). Show the file, show the current description, say "this
  looks like a placeholder."

---

## CLI interface

```
md-tuneup [FOLDER] [OPTIONS]
```

**Arguments:**
- `FOLDER` — path to the folder to scan. Defaults to current directory (`.`).

**Options:**
- `--dry-run` — scan and report only; don't offer to apply any fixes, don't
  create a backup. Safe preview mode.
- `--no-backup` — skip the automatic backup before applying fixes. For users
  who trust their git.
- `--verbose` — extra detail on what each check is doing and why (default
  output is already communicative; this is debug-level).
- `--version` — print version and exit.
- `--help` — print help and exit.

No config file. No `.md-tuneup.yaml`. If a v2 needs one, that's a v2 decision.

---

## Approval flow UX

This is the heart of the tool's personality. The experience should feel like a
knowledgeable friend walking you through your files, not a wall of warnings.

### Phase 1: Scan

```
MD Tune-Up v1.0

Scanning: /Users/rene/memory-files
Found 47 markdown files.

Detecting conventions...
  ✓ Frontmatter: 44 of 47 files (94%) — will check frontmatter
  ✓ Wiki-links: 31 files use [[links]] — will check for broken links
  ✓ Name field: 44 files — will check name/filename agreement
  ✓ Description field: 42 files — will check for placeholders

Running checks...
```

### Phase 2: Summary

```
Done. Found 12 items across 9 files:

  Frontmatter issues:    3  (1 YAML error, 2 missing keys)
  Name mismatches:       4
  Broken links:          2
  Placeholder descs:     3  (flag only — no auto-fix)

5 items are fixable. 7 are flag-only (shown for your review).

I'll walk you through each one. For fixable items, you can approve,
skip, or quit at any time. Nothing is written until you approve it.

Ready? Press Enter to start, or 'q' to quit.
```

### Phase 3: Walk-through

Group by type (all name mismatches together, etc.) to reduce context
switching. Within each group, go one at a time.

```
── Name/Filename Mismatch (1 of 4) ──────────────────────────

  File: /areas/old-project-name.md
  name: "new-project-name"

  The frontmatter name doesn't match the filename.

  [1] Update name to "old-project-name" (match the file)
  [2] Rename file to "new-project-name.md" (match the name)
  [s] Skip
  [q] Quit (no more changes)

  Choice:
```

Flag-only items are shown but don't prompt for a choice:

```
── Placeholder Description (1 of 3) ─────────────────────────

  File: /topics/hobbies.md
  description: "hobbies"

  This looks like a placeholder — it just repeats the filename.
  Consider writing a real one-line description of what this file
  covers.

  [Enter] Next
```

### Phase 4: Apply

```
You approved 4 changes. Here's what will happen:

  1. Back up folder to /Users/rene/memory-files_backup_20261015_1430/
  2. Update name field in old-project-name.md
  3. Update name field in another-file.md
  4. Fix link [[old-ref]] → [[new-ref]] in areas/project.md
  5. Add missing "aliases" key to people/someone.md

Proceed? [y/n]
```

Then execute, reporting each step:

```
  ✓ Backup created
  ✓ Updated: old-project-name.md (name field)
  ✓ Updated: another-file.md (name field)
  ✓ Updated: areas/project.md (link fix)
  ✓ Updated: people/someone.md (added aliases key)

Done. 4 files changed. Backup at:
  /Users/rene/memory-files_backup_20261015_1430/
```

---

## Backup behavior

- Before applying any approved changes, copy the entire target folder to
  `{folder}_backup_{YYYYMMDD}_{HHMM}/` as a sibling directory.
- If the backup path already exists (second run in the same minute), append
  `_2`, `_3`, etc.
- In `--dry-run` mode: no backup created (nothing to protect).
- In `--no-backup` mode: skip backup, proceed directly to apply.
- The backup is a flat copy of `.md` files only — not the entire directory
  tree. Non-markdown files are not the tool's business.

---

## Project structure

```
md-tuneup/
├── README.md
├── SPEC.md            ← this file
├── LICENSE            ← MIT
├── md_tuneup.py       ← single-file script, no package structure
└── requirements.txt   ← PyYAML only (if needed; stdlib may suffice)
```

Single file. No `src/` directory, no `__init__.py`, no package. The user
should be able to run `python md_tuneup.py ~/my-notes` and go. If it grows
past ~800 lines, split — but not before.

---

## Dependencies

- **Python 3.8+** (broad compatibility; no f-string walrus operators or
  3.10+ features)
- **PyYAML** — for parsing frontmatter. The only external dependency.
  `pip install pyyaml` in the README.
- Everything else is stdlib: `os`, `pathlib`, `re`, `shutil`, `argparse`,
  `datetime`, `difflib` (for fuzzy link matching).

---

## What's NOT in v1

Deferred to v2 or later, with rationale:

- **Cosmetic checks** (heading levels, bullet marker consistency, trailing
  whitespace) — formatters like Prettier and markdownlint already cover
  these. Not our lane.
- **External URL checking** — different problem, different failure modes
  (network, rate limits, auth). Separate tool territory.
- **Config file** — zero-config is a feature, not a limitation. If real
  user feedback says "I need to customize the threshold," add it then.
- **Browser UI** — the leading option for a friendlier face later. A
  read-only HTML report is nearly free; interactive approve-and-apply needs
  a small built-in Python server. Same shape as a Worker + backend pattern.
  v2 decision driven by real user feedback, not a guess.
- **Auto-generated descriptions** — tempting, but this tool doesn't call
  an LLM. It's a static analysis tool. If it ever generates descriptions,
  that's a different mode with different dependencies.
