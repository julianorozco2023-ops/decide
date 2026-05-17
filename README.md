# decide

A CLI tool that captures the *why* behind code decisions and surfaces them when you return to a file.

Most context loss in software isn't "I forgot what this does" — it's "I forgot why it's this way and not the obvious alternative." This tool fixes that.

## Install

```bash
git clone https://github.com/julianorozco2023-ops/decide.git
cd decide
```

Add the `work` alias to your shell:

```bash
# add to ~/.zshrc or ~/.bashrc
work() {
  if [ -z "$1" ]; then
    echo "Usage: work <file>"
    return 1
  fi
  python3 /path/to/decide.py --context "$1"
  echo ""
  read -r "?  Press enter to open file..."
  ${EDITOR:-open} "$1"
}
```

## Usage

**Capture a decision** (run this after making a non-obvious choice):
```bash
python3 decide.py src/auth/token.py
```

**Return to a file with full context:**
```bash
work src/auth/token.py
```

**List all decisions in the current project:**
```bash
python3 decide.py --list
```

**Search decisions:**
```bash
python3 decide.py --search jwt
```

**Surface relevant decisions for a file:**
```bash
python3 decide.py --context src/auth/token.py
```

## How it works

Decisions are stored as JSON in a `decisions/` folder inside your repo — version controlled, portable, no external dependencies.

Each decision captures:
- **What** you decided
- **Why** you decided it
- **What you rejected** and why
- **Constraints** that forced your hand
- **Confidence level**
- The git commit it was made at

The `--context` command scores every past decision against the file you're opening using file path matching, directory proximity, and function/class name overlap — then surfaces the most relevant ones.

## The habit

- Capture decisions **as they happen** — 30 seconds while the reasoning is fresh
- Run `work <file>` **before touching anything** when you return to a project
- Only capture decisions you'd have to *think* to reconstruct — skip the obvious ones

## Requirements

- Python 3.7+
- Git
