# Installing ctags-indexing-mcp

This guide is meant to be followed by an **agent** (or a human) end-to-end with
minimal interaction. Every step is a copy-pasteable command. If a step fails,
read the error and apply the matching entry in "Troubleshooting" at the bottom.

---

## 0. Assumptions

- Linux or macOS shell (bash/zsh).
- Network access to PyPI.
- The user has `claude` (Claude Code) on `$PATH`. Check with
  `command -v claude` — if missing, follow Claude Code's own install guide
  first; do **not** try to install this MCP server without it.

---

## 1. Verify system prerequisites

Run this block. It is read-only — exit code 0 means all good. Anything missing
must be installed via the system package manager **before** continuing.

```bash
set -e
need() { command -v "$1" >/dev/null || { echo "MISSING: $1"; exit 1; }; }
need python3
need cscope
need ctags
need git
python3 -c "import sys; assert sys.version_info >= (3,10), sys.version" \
  || { echo "MISSING: python >= 3.10"; exit 1; }
# uv is preferred but optional; pip works too.
command -v uv >/dev/null && echo "uv: $(uv --version)" || echo "uv: not found (pip fallback will be used)"
echo "ctags: $(ctags --version | head -1)"
echo "cscope: $(cscope -V 2>&1 | head -1)"
echo "OK"
```

Install hints if anything is missing:
- Debian/Ubuntu: `sudo apt-get install -y cscope universal-ctags python3-venv`
- Fedora/RHEL:   `sudo dnf install -y cscope ctags python3`
- macOS:         `brew install cscope universal-ctags`
- uv (optional, recommended): `curl -LsSf https://astral.sh/uv/install.sh | sh`

---

## 2. Get the source

Pick **one** of A or B.

### A. Clone from git (preferred)

```bash
INSTALL_DIR="${CODE_INDEX_MCP_DIR:-$HOME/work/ctags-indexing-mcp}"
REPO_URL="<FILL THIS IN — git remote URL>"

if [[ ! -d $INSTALL_DIR/.git ]]; then
    git clone "$REPO_URL" "$INSTALL_DIR"
else
    git -C "$INSTALL_DIR" pull --ff-only
fi
```

### B. Use an existing local copy

If the repo is already present locally (e.g. you authored it on this machine):

```bash
INSTALL_DIR="${CODE_INDEX_MCP_DIR:-$HOME/work/ctags-indexing-mcp}"
test -f "$INSTALL_DIR/pyproject.toml" \
  || { echo "no pyproject.toml at $INSTALL_DIR — clone from git instead"; exit 1; }
```

---

## 3. Install the package into a private venv

This is **idempotent** — running it twice is safe.

```bash
cd "$INSTALL_DIR"
if command -v uv >/dev/null; then
    uv venv --python 3.12 >/dev/null
    uv pip install -e . >/dev/null
else
    python3 -m venv .venv
    .venv/bin/pip install --upgrade pip >/dev/null
    .venv/bin/pip install -e . >/dev/null
fi
BIN="$INSTALL_DIR/.venv/bin/ctags-indexing-mcp"
test -x "$BIN" || { echo "binary not produced at $BIN"; exit 1; }
echo "binary: $BIN"
```

Verify the server can at least start (it will sit on stdio waiting for input;
we kill it after a moment):

```bash
timeout 2 "$BIN" </dev/null >/dev/null 2>&1 ; rc=$?
# timeout returns 124 on the kill — that means the server started and was idle.
[[ $rc == 124 || $rc == 0 ]] || { echo "server failed to start (rc=$rc)"; exit 1; }
echo "server boots OK"
```

---

## 4. Register with Claude Code

Use the `user` scope so the server is available in **all** projects, not just
the current directory. The `--` separates `claude mcp add` flags from the
subprocess command.

```bash
# Remove any prior registration so this is idempotent
claude mcp remove -s user ctags-indexing 2>/dev/null || true

claude mcp add -s user ctags-indexing -- "$BIN"
```

Verify:

```bash
claude mcp list | grep -E "^ctags-indexing" || { echo "not registered"; exit 1; }
claude mcp get ctags-indexing   # spawns the server briefly for a health check
```

A healthy `claude mcp get` output ends with something like
`✓ Connected · 5 tools`.

---

## 5. Smoke test against a real project

Pick any C/C++/Python project the user owns. This calls the server through
Python directly (does not require Claude to be running). It is optional but
proves the tool plumbing end to end.

```bash
TEST_PROJECT="${1:-$HOME/work/some-project}"
test -d "$TEST_PROJECT" || { echo "skipping smoke test, no project at $TEST_PROJECT"; exit 0; }

cd "$INSTALL_DIR"
.venv/bin/python - "$TEST_PROJECT" <<'PY'
import asyncio, json, sys
from ctags_indexing_mcp.server import mcp

async def call(name, **a):
    contents = await mcp.call_tool(name, a)
    return json.loads(contents[0].text)

async def main(path):
    a = await call("analyze", path=path)
    print(f"analyze: {a['total_source_files']} files, langs={a['detected_languages']}")
    r = await call("index_create", path=path)
    print(f"index_create: cscope={r['cscope_built']} ctags={r['ctags_built']} files={r['files_indexed']}")
    s = await call("index_status", path=path)
    for k, v in s["artifacts"].items():
        print(f"  {k:14s} {'size=%d' % v['size'] if v else '(missing)'}")
    e = await call("editor_setup", path=path)
    print(f"editor_setup: {e['activate_script']}")

asyncio.run(main(sys.argv[1]))
PY
```

---

## 6. Tell the user how to actually use it

After installation, the user (not the agent) should add the activation line
**themselves**. Do **not** silently edit `~/.bashrc` without consent.

Print the following two lines to the user:

```
Index a project from Claude with:   "Index this project at <path>"
After Claude finishes, run:         source <path>/.codeindex/activate.sh
                                    (or add that to ~/.bashrc to make it permanent)
```

---

## Reference: other MCP clients

The server speaks plain stdio MCP, so any compliant client works. The
underlying config payload is always:

```json
{
  "command": "<INSTALL_DIR>/.venv/bin/ctags-indexing-mcp",
  "args": [],
  "env": {}
}
```

| Client          | Where to put it                                                          |
|-----------------|---------------------------------------------------------------------------|
| Claude Code     | `claude mcp add -s user ctags-indexing -- <BIN>` (this guide)                |
| Claude Desktop  | `~/Library/Application Support/Claude/claude_desktop_config.json` (mac), `%APPDATA%\Claude\claude_desktop_config.json` (win). Key: `mcpServers.ctags-indexing` |
| Cursor          | Settings → MCP → Add Server, paste the JSON above                        |
| Continue (VSCode)| `.continue/config.json` → `mcpServers.ctags-indexing`                        |

---

## Troubleshooting

**`claude: command not found`** — Install Claude Code first; this server is
useless without an MCP client.

**`ModuleNotFoundError: No module named 'mcp'` when running the binary** —
The venv install failed or the wrong python is being used. Re-run step 3 and
confirm `head -1 $BIN` points at `$INSTALL_DIR/.venv/bin/python`.

**`cscope: command not found` warnings in `index_create`** — `cscope` is a
runtime dependency, not a Python dependency. Install via the package manager
(step 1) and retry. `ctags` is similarly required for the `tags` half.

**`claude mcp get ctags-indexing` shows "Failed to connect"** — Spawn the binary
manually: `$BIN < /dev/null` — any Python traceback will tell you what's wrong
(usually a stale venv after a pull; rerun `uv pip install -e .`).

**`Cs db add` does nothing inside nvim** — The user is missing
`cscope_maps.nvim`. The activation script is wrapped in `silent!` so it won't
error, but cscope lookups won't work. Tell the user to install the plugin or
fall back to plain `:cs` (real vim).

**`tags` not found from a sub-directory of the project** — That's normal for
nvim's default `'tags'` (it does an upward search from the current *file*'s
directory). If the user opens a file that lives **outside** the project root,
tags won't resolve; that's expected, not a bug.

**Want to uninstall** —
```bash
claude mcp remove -s user ctags-indexing
rm -rf "$INSTALL_DIR"
```
(`.codeindex/` directories inside individual projects are independent — delete
them by hand if desired.)
