<!--
README.md v1.1 — 2026-10-15
Changelog:
- v1.1 (2026-10-15): Repo is rene-kropf/md-tuneup; note for pip's "externally-managed-environment" error; version header moved into this comment so GitHub opens on the title; Adopt a Pet line.
- v1.0 (2026-10-15): Initial README.
-->

# MD Tune-Up

**Your AI is only as consistent as the context you feed it.**

If you use AI every day — Claude, ChatGPT, anything — and you feed it
markdown files (notes, memory files, project docs), those files drift over
time. Names stop matching filenames. Links point to files that got renamed.
Descriptions say "TODO" six months after you wrote them. Frontmatter goes
stale.

None of that crashes anything. But your AI reads every word of it, and
inconsistent context produces inconsistent answers. The drift is on your
side, not the model's.

MD Tune-Up is a small command-line tool that scans a folder of markdown
files, finds the structural inconsistencies, and walks you through fixing
them — one at a time, with your approval, and with an automatic backup
before it touches anything. Think of it like an occasional tune-up for
your car, except the car is your AI's context.

**Free. Open-source. Runs on your machine. No account, no cloud, no tracking.**

---

## What it checks (v1)

MD Tune-Up adapts to your folder. It looks at what conventions your files
actually use and only checks for those. A folder of plain markdown with no
frontmatter won't get frontmatter warnings — that would be imposing a format
you never adopted.

| Check | What it catches | Can it fix it? |
|---|---|---|
| **Frontmatter validity** | YAML syntax errors, missing keys that most of your files have | Flags errors; offers to add missing keys |
| **Name/filename agreement** | `name: old-name` in a file called `new-name.md` | Yes — update the name or rename the file, your choice |
| **Broken internal links** | `[[something]]` or `[text](./path.md)` pointing nowhere | Yes, if a likely match exists; otherwise flags it |
| **Placeholder descriptions** | `description: "TODO"` or descriptions that just repeat the filename | Flag only — writing a real description is your job |

That's it for v1. No cosmetic nitpicks (heading levels, bullet styles,
trailing whitespace) — tools like Prettier already cover those. MD Tune-Up
catches the stuff formatters miss.

---

## Before you start

You need two things installed on your computer. If you already have them,
skip to [How to install](#how-to-install).

### 1. Python

MD Tune-Up is a Python script. You need Python 3.8 or newer.

**Check if you already have it.** Open your terminal and type:

```
python3 --version
```

If you see something like `Python 3.10.4`, you're good. Skip to step 2.

If you see "command not found" or a version below 3.8, install Python:

- **Mac:** The easiest way is to go to [python.org/downloads](https://www.python.org/downloads/)
  and download the latest version. Run the installer. When it's done, close
  your terminal, open a new one, and try `python3 --version` again.
- **Windows:** Same thing — [python.org/downloads](https://www.python.org/downloads/).
  **Important:** During installation, check the box that says "Add Python to
  PATH." If you miss this, the `python3` command won't work from your terminal.
- **Linux:** You almost certainly have it already. If not: `sudo apt install python3`
  (Ubuntu/Debian) or `sudo dnf install python3` (Fedora).

### 2. pip (Python's package installer)

pip usually comes with Python. Check:

```
pip3 --version
```

If that works, you're set. If not, Python's installer may have installed it
as `pip` instead of `pip3` — try `pip --version`. If neither works, see
[pip installation guide](https://pip.pypa.io/en/stable/installation/).

---

## How to install

Open your terminal and run these commands one at a time. Each line is one
command — copy it, paste it into your terminal, press Enter, and wait for
it to finish before running the next one.

**Step 1: Download MD Tune-Up from GitHub**

```
git clone https://github.com/rene-kropf/md-tuneup.git
```

This creates a folder called `md-tuneup` wherever your terminal is currently
pointed. (If you want it somewhere specific, `cd` to that location first.)

> **Don't have git?** You can also download it manually: go to the GitHub page,
> click the green "Code" button, click "Download ZIP," unzip it, and you'll
> have the same folder.

**Step 2: Install the one dependency**

```
cd md-tuneup
pip3 install -r requirements.txt
```

This installs PyYAML, which MD Tune-Up uses to read frontmatter. That's the
only external dependency.

> **pip says "externally-managed-environment"?** Newer Linux (Ubuntu 23.04+,
> Debian 12+) and Python from Homebrew on a Mac block pip installs. Use one of
> these instead:
>
> - Ubuntu or Debian: `sudo apt install python3-yaml`
> - Mac with Homebrew Python: `pip3 install --user --break-system-packages pyyaml`
>   (this installs PyYAML for your user account only; Homebrew's own packages
>   aren't touched)

**That's it.** There's nothing else to install, no accounts to create, no
services to start.

---

## How to use it

### The basic command

```
python3 md_tuneup.py /path/to/your/markdown/folder
```

Replace `/path/to/your/markdown/folder` with the actual path to your files.

**Examples:**

```
# Scan your Claude memory files
python3 md_tuneup.py ~/claude-memory

# Scan the current folder
python3 md_tuneup.py .

# Scan a specific project's docs
python3 md_tuneup.py ~/projects/my-app/docs
```

### What happens when you run it

The tool walks you through everything. Here's the short version:

1. **It scans your folder** and tells you what it found (how many files,
   which conventions are in use).
2. **It runs the checks** and gives you a summary: "Found 12 items across
   9 files."
3. **It walks you through each item** one at a time. For fixable items, you
   choose: apply the fix, skip it, or quit. For flag-only items, it shows
   you the issue and moves on.
4. **Before writing anything**, it creates a backup of your folder — a
   timestamped copy sitting right next to the original.
5. **It applies your approved changes** and tells you what it did.

At no point does it silently change anything. Every change is shown to you
first and applied only with your explicit approval.

### Preview mode (dry run)

Not ready to make changes? Just want to see what it would find?

```
python3 md_tuneup.py ~/my-notes --dry-run
```

Dry run does everything except offer fixes or create a backup. It scans,
checks, and reports. Read-only. Safe to run as many times as you want.

**If you're running this for the first time, start with `--dry-run`.** Get
a feel for what it finds before you let it make changes.

### Skip the backup

If your files are already in git (or another version control system) and you
don't need the automatic backup:

```
python3 md_tuneup.py ~/my-notes --no-backup
```

### All options

| Option | What it does |
|---|---|
| `--dry-run` | Scan and report only. No changes, no backup. |
| `--no-backup` | Skip the automatic backup before applying fixes. |
| `--verbose` | Extra detail about what each check is doing (debug-level). |
| `--version` | Print the version number and exit. |
| `--help` | Print help and exit. |

---

## How the backup works

Before MD Tune-Up writes any changes, it copies all `.md` files from your
folder into a backup folder right next to the original:

```
your-notes/                          ← your files (these get changed)
your-notes_backup_20261015_1430/     ← backup (frozen snapshot)
```

The backup name includes the date and time so you can tell which backup
goes with which run. If something goes wrong — or you just change your
mind — copy the files back from the backup folder.

The backup contains only `.md` files. Images, config files, and other
non-markdown content in your folder are not the tool's business and are
never touched.

---

## FAQ

**Does this send my files anywhere?**
No. Everything runs locally on your machine. No network calls, no cloud,
no telemetry, no analytics. Your files never leave your computer.

**Does this call an AI?**
No. MD Tune-Up is a static analysis tool. It reads your files, applies
pattern matching, and reports what it finds. No LLM involved.

**Will it mess up my files?**
It tries very hard not to. It backs up your folder before writing, it
shows you every proposed change before applying it, and it only applies
changes you explicitly approve. But it's software, so: keep backups of
things you care about. (Which this tool does for you.)

**What if I have hundreds of files?**
It should handle that fine. The checks are simple file operations — no
heavy computation. If the number of findings is large, the one-at-a-time
approval flow keeps it manageable.

**Can I run it on the same folder repeatedly?**
Yes. It's designed for occasional re-runs. Each run creates a fresh backup
(timestamped, so they don't collide) and only flags things that are still
inconsistent.

**What markdown conventions does it understand?**
YAML frontmatter (`---` delimited), `[[wiki-links]]`, and relative markdown
links (`[text](./path.md)`). If your files don't use any of these, the tool
will tell you "nothing to tune up" and exit — which is the right answer.

---

## License

MIT. Use it however you want.

---

## Credits

Built by [Emmaus Development](https://emmausdev.com) — AI that remembers.
Systems that last.

🐾 [Adopt a Pet — Get a Dog](https://www.petfinder.com/)
