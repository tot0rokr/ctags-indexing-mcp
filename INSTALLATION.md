# Installing ctags-indexing-mcp

This guide is meant to be followed by an **agent** (or a human) end-to-end with
minimal interaction. Every step is a copy-pasteable command. If a step fails,
read the error and apply the matching entry in "Troubleshooting" at the bottom.

---

## 0. Assumptions

- Linux or macOS shell (bash/zsh).
- Network access to PyPI / GitHub.
- The user is already running **some** MCP-capable agent (Claude Code,
  Claude Desktop, Cursor, Continue, Windsurf, or another client that speaks
  the Model Context Protocol). This guide adds the server to that client.
  If no MCP client is installed yet, install one first — this server is
  useless without one.

> **For the agent following this file:** steps 1–3 are client-agnostic and
> always run. Step 4 has one sub-section per MCP client (4A–4F); pick the
> one that matches the client **you are running inside**. If multiple
> clients are installed on the machine and you can't tell which one the
> user wants, ask the user. Step 5 is client-agnostic verification.

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
INSTALL_DIR="${CTAGS_INDEXING_MCP_DIR:-$HOME/work/ctags-indexing-mcp}"
REPO_URL="https://github.com/tot0rokr/ctags-indexing-mcp.git"

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

## 4. Register with your MCP client

Every MCP client ultimately consumes the **same** stdio payload:

```json
{
  "command": "<BIN value from step 3>",
  "args": [],
  "env": {}
}
```

…stored under the key `mcpServers.ctags-indexing` in some client-specific
config file (or, for Claude Code, written via a CLI). Pick the sub-section
that matches your client. All sub-sections are **idempotent** — re-running
them overwrites the previous registration in place.

Optional: detect which clients look installed on this machine (purely
informational, does not change anything):

```bash
present=()
command -v claude >/dev/null                                   && present+=("4A claude-code")
[[ -d "$HOME/Library/Application Support/Claude" \
   || -d "$HOME/.config/Claude" \
   || -d "$APPDATA/Claude" ]]                                   && present+=("4B claude-desktop")
[[ -d "$HOME/.cursor" ]]                                        && present+=("4C cursor")
[[ -d "$HOME/.continue" ]]                                      && present+=("4D continue")
[[ -d "$HOME/.codeium/windsurf" ]]                              && present+=("4E windsurf")
printf 'detected:\n'; printf '  %s\n' "${present[@]:-(none — fall back to 4F generic)}"
```

### 4A. Claude Code

```bash
claude mcp remove -s user ctags-indexing 2>/dev/null || true
claude mcp add    -s user ctags-indexing -- "$BIN"
claude mcp list | grep -q "^ctags-indexing" || { echo "not registered"; exit 1; }
claude mcp get ctags-indexing   # spawns the server briefly for a health check
```

A healthy `claude mcp get` output ends with `✓ Connected · 5 tools`.

### 4B. Claude Desktop

Edit the desktop config JSON. The location depends on OS:

| OS      | Path                                                         |
|---------|--------------------------------------------------------------|
| macOS   | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Linux   | `~/.config/Claude/claude_desktop_config.json`                |
| Windows | `%APPDATA%\Claude\claude_desktop_config.json`                |

Idempotent merge with Python (uses the venv we just built so `json` is
guaranteed available):

```bash
case "$(uname -s)" in
    Darwin) CFG="$HOME/Library/Application Support/Claude/claude_desktop_config.json" ;;
    Linux)  CFG="$HOME/.config/Claude/claude_desktop_config.json" ;;
    *)      CFG="${APPDATA:-$HOME}/Claude/claude_desktop_config.json" ;;
esac
mkdir -p "$(dirname "$CFG")"
"$INSTALL_DIR/.venv/bin/python" - "$CFG" "$BIN" <<'PY'
import json, os, sys
cfg_path, bin_path = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        try: cfg = json.load(f)
        except json.JSONDecodeError: cfg = {}
cfg.setdefault("mcpServers", {})["ctags-indexing"] = {
    "command": bin_path, "args": [], "env": {},
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"wrote {cfg_path}")
PY
```

**Restart Claude Desktop** so it re-reads the config.

### 4C. Cursor

```bash
CFG="$HOME/.cursor/mcp.json"
mkdir -p "$(dirname "$CFG")"
"$INSTALL_DIR/.venv/bin/python" - "$CFG" "$BIN" <<'PY'
import json, os, sys
cfg_path, bin_path = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        try: cfg = json.load(f)
        except json.JSONDecodeError: cfg = {}
cfg.setdefault("mcpServers", {})["ctags-indexing"] = {
    "command": bin_path, "args": [], "env": {},
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"wrote {cfg_path}")
PY
```

**Restart Cursor** (or toggle MCP in Settings → MCP) to pick it up.

### 4D. Continue (VS Code / JetBrains)

Continue reads `~/.continue/config.json` (global) or `.continue/config.json`
(per workspace). The same Python snippet works — choose the path the user
prefers:

```bash
CFG="$HOME/.continue/config.json"     # or ".continue/config.json" for project-scoped
mkdir -p "$(dirname "$CFG")"
"$INSTALL_DIR/.venv/bin/python" - "$CFG" "$BIN" <<'PY'
import json, os, sys
cfg_path, bin_path = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        try: cfg = json.load(f)
        except json.JSONDecodeError: cfg = {}
cfg.setdefault("mcpServers", {})["ctags-indexing"] = {
    "command": bin_path, "args": [], "env": {},
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"wrote {cfg_path}")
PY
```

Reload Continue (`Cmd/Ctrl+Shift+P` → "Continue: Reload").

### 4E. Windsurf (Codeium)

```bash
CFG="$HOME/.codeium/windsurf/mcp_config.json"
mkdir -p "$(dirname "$CFG")"
"$INSTALL_DIR/.venv/bin/python" - "$CFG" "$BIN" <<'PY'
import json, os, sys
cfg_path, bin_path = sys.argv[1], sys.argv[2]
cfg = {}
if os.path.exists(cfg_path):
    with open(cfg_path) as f:
        try: cfg = json.load(f)
        except json.JSONDecodeError: cfg = {}
cfg.setdefault("mcpServers", {})["ctags-indexing"] = {
    "command": bin_path, "args": [], "env": {},
}
with open(cfg_path, "w") as f:
    json.dump(cfg, f, indent=2)
print(f"wrote {cfg_path}")
PY
```

Restart Windsurf.

### 4F. Generic (any other MCP-capable client)

The client almost certainly has a JSON config with an `mcpServers` (or
similarly named) map. Add:

```json
"ctags-indexing": {
  "command": "<value of $BIN from step 3>",
  "args": [],
  "env": {}
}
```

Substitute `$BIN` with the absolute path printed at the end of step 3
(`<INSTALL_DIR>/.venv/bin/ctags-indexing-mcp`). Restart the client.

---

## 5. Smoke test against a real project

Pick any C/C++/Python project the user owns. This calls the server through
Python directly (does not require any MCP client to be running). It is
optional but proves the tool plumbing end to end.

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
Index a project from your agent with:   "Index this project at <path>"
After the agent finishes, run:          source <path>/.codeindex/activate.sh
                                        (or add that to ~/.bashrc to make it permanent)
```

---

## Troubleshooting

**No MCP client is installed** — Install one first (Claude Code, Claude
Desktop, Cursor, Continue, Windsurf, …); this server only does anything
when an MCP client connects to it.

**`ModuleNotFoundError: No module named 'mcp'` when running the binary** —
The venv install failed or the wrong python is being used. Re-run step 3 and
confirm `head -1 $BIN` points at `$INSTALL_DIR/.venv/bin/python`.

**`cscope: command not found` warnings in `index_create`** — `cscope` is a
runtime dependency, not a Python dependency. Install via the package manager
(step 1) and retry. `ctags` is similarly required for the `tags` half.

**Client doesn't see the server / "Failed to connect"** — Spawn the binary
manually: `$BIN < /dev/null` — any Python traceback will tell you what's
wrong (usually a stale venv after a pull; rerun `uv pip install -e .`).
Also: most clients only re-read their config on restart — make sure you
restarted Claude Desktop / Cursor / Windsurf / Continue after step 4.

**`Cs db add` does nothing inside nvim** — The user is missing
`cscope_maps.nvim`. The activation script is wrapped in `silent!` so it won't
error, but cscope lookups won't work. Tell the user to install the plugin or
fall back to plain `:cs` (real vim).

**`tags` not found from a sub-directory of the project** — That's normal for
nvim's default `'tags'` (it does an upward search from the current *file*'s
directory). If the user opens a file that lives **outside** the project root,
tags won't resolve; that's expected, not a bug.

**Want to uninstall** —
- Claude Code: `claude mcp remove -s user ctags-indexing`
- Other clients: open the same config JSON you edited in step 4 and remove
  the `mcpServers.ctags-indexing` entry, then restart the client.
- Then: `rm -rf "$INSTALL_DIR"`.

(`.codeindex/` directories inside individual projects are independent — delete
them by hand if desired.)
