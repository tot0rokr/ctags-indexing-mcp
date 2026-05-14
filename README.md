# ctags-indexing-mcp

MCP server that builds cscope/ctags indexes for C/C++/Python projects and wires
them into vim/neovim. Exposes the indexing workflow to any MCP-capable agent
(Claude Code, Claude Desktop, Cursor, Continue, Windsurf, …) and gives you a
one-line shell activation that makes `vim` auto-attach the indexes from any cwd.

## What it does

- **`index_create(path?, languages?, excludes?, output_dir?, dry_run?)`** —
  one-shot: analyzes the project (language counts, build systems, recommended
  excludes) AND builds the cscope/ctags indexes. The response always
  contains an `analysis` block. Pass `dry_run=True` for a read-only
  preview (no files written). Otherwise writes artifacts **directly into
  the project root**:
  `<path>/{cscope.files, cscope.out, cscope.in.out, cscope.po.out, tags, .codeindex.config.json}`.
  When `<path>` is a git repo, those names are appended to
  `<path>/.gitignore` automatically (idempotent).
- **`index_regen(path?)`** — rebuild using the previously saved
  `.codeindex.config.json`.
- **`index_status(path?)`** — list artifacts with sizes and mtimes.
- **`editor_setup(path?)`** — generate `<path>/codeindex-activate.sh`. Source
  it once per shell. After sourcing, every `vim` invocation auto-attaches
  `tags` and the cscope DB regardless of cwd.
- **`self_update()`** — `git pull --ff-only` + `pip install -e .` on the
  server's own source checkout. Use when the user says "update the MCP".
  Reports the before/after commit and prompts the user to restart the MCP
  client (the running server process keeps the old code until then). No-op
  for non-editable / PyPI installs.

The agent calling these tools is expected to figure out the user's project
root itself and pass it as `path`. If `path` is omitted, the server falls
back to its own cwd (the directory the MCP client launched it from); the
response includes a `path_source` field so the agent can tell which one was
used.

## Requirements

- Python 3.10+
- `cscope` and `ctags` (Universal Ctags) on `$PATH`
- For the nvim auto-attach: `cscope_maps.nvim` plugin

## Install

Hand [`INSTALLATION.md`](./INSTALLATION.md) to your coding agent and ask it
to follow the guide end-to-end. It is written to be agent-followable and
**MCP-client-agnostic** — step 4 has one sub-section per client:

- CLI-based clients (preferred, one-liner): Claude Code (`claude mcp add`),
  OpenAI Codex (`codex mcp add`), Gemini CLI (`gemini mcp add`),
  Amazon Q (`q mcp add`).
- Config-file clients: Cursor, Windsurf, Continue, Claude Desktop — add the
  same stdio entry to that client's config and restart it.

All steps are idempotent; re-running on an already-installed machine just
updates and reconnects.

Concretely, paste this into your agent:

> "Read INSTALLATION.md from https://github.com/tot0rokr/ctags-indexing-mcp
> and install + register the MCP server in whatever client you are running
> inside."

Manual install is also fine if you prefer; the same commands are in
INSTALLATION.md. After installation, restart your MCP client so it picks up
the new server.

## Update

Three ways, pick whichever is convenient:

**A. From within your MCP client (easiest).** Just ask:

> "Update the ctags-indexing MCP."

The agent calls the `self_update` tool, which runs `git pull --ff-only`
followed by `pip install -e .` on the server's own checkout, reports the
before/after commit, and tells you to restart the client. Restart the MCP
client (quit and reopen Claude Code / Cursor / etc.) so a fresh server
process is spawned with the new code — the running process keeps the old
code in memory until then.

**B. Manual (one liner).**

```bash
cd /path/to/ctags-indexing-mcp && git pull --ff-only && uv pip install -e .
```

Then restart your MCP client.

**C. Re-run INSTALLATION.md.** Steps 1–3 of [`INSTALLATION.md`](./INSTALLATION.md)
are idempotent and double as an update path. Step 4 (registration) is
already done, so skip it.

### When is restart required?

Always, in practice. The tools the client sees, their signatures, and the
running logic all come from the server process that was spawned at client
startup. New code lands on disk, but the live server keeps using the old
copy until you restart the client and it spawns a new one.

## Typical session

Inside your MCP client (Claude Code, Cursor, etc.), just ask:

> "Index this project at ~/work/foo and set me up so vim auto-attaches."

The agent will call `analyze` → `index_create` → `editor_setup` in sequence.
Then in your shell:

```bash
source ~/work/foo/codeindex-activate.sh
vim some/file.c   # tags and cscope DB attached automatically
```

To persist across shells, add the `source ...` line to `~/.bashrc` /
`~/.zshrc`.

## What `codeindex-activate.sh` does

The script defines a shell function `vim` that wraps the real `vim`/`nvim`
binary. It:

1. Detects whether `vim` resolves to neovim (via alias or symlink).
2. Adds `--cmd 'set tags+=<abs path>'` so ctags lookups work from any cwd.
3. Adds `-c 'silent! Cs db add <abs path>'` for neovim with
   `cscope_maps.nvim`, or `-c 'silent! cs add ...'` for real vim.

Because a shell function takes precedence over the `alias vim='nvim'` you may
already have, this composes cleanly.

## `.gitignore`

`index_create` adds the artifact names to your project's `.gitignore`
automatically when the project is a git repo. No manual setup needed. The
entries it adds:

```
cscope.files
cscope.out
cscope.in.out
cscope.po.out
tags
codeindex-activate.sh
.codeindex.config.json
```

## Limitations

- cscope itself only understands C/C++ (and is happy enough on assembly).
  Python files are indexed by ctags only.
- For TypeScript/Rust/Go projects, LSP (clangd / rust-analyzer / gopls / tsserver)
  gives you a far better experience. This tool does not try to compete there.
- The `vim` wrapper is shell-scoped: source the activation script in every
  shell or put it in your rc file.
