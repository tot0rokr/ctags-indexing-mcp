# ctags-indexing-mcp

MCP server that builds cscope/ctags indexes for C/C++/Python projects and wires
them into vim/neovim. Exposes the indexing workflow to any MCP-capable agent
(Claude Code, Claude Desktop, Cursor, Continue, Windsurf, …) and gives you a
one-line shell activation that makes `vim` auto-attach the indexes from any cwd.

## What it does

- **`analyze(path)`** — scan a project, return language counts, detected build
  systems (cmake/meson/cargo/npm/yocto/…), and a recommended exclude list.
  Read-only.
- **`index_create(path, languages?, excludes?, output_dir?)`** — build the
  indexes. Auto-detects languages/excludes if not given. Writes
  `<project>/.codeindex/{cscope.out, tags, cscope.files, config.json}`.
- **`index_regen(path)`** — rebuild using the previously saved `config.json`.
- **`index_status(path)`** — list artifacts with sizes and mtimes.
- **`editor_setup(path)`** — generate `<project>/.codeindex/activate.sh`. Source
  it once per shell. After sourcing, every `vim` invocation auto-attaches
  `tags` and the cscope DB regardless of cwd.

## Requirements

- Python 3.10+
- `cscope` and `ctags` (Universal Ctags) on `$PATH`
- For the nvim auto-attach: `cscope_maps.nvim` plugin

## Install

Hand [`INSTALLATION.md`](./INSTALLATION.md) to your coding agent and ask it
to follow the guide end-to-end. It is written to be agent-followable and
**MCP-client-agnostic** — step 4 has one sub-section per client (Claude
Code, Claude Desktop, Cursor, Continue, Windsurf, plus a generic JSON
recipe for anything else), so the same file works no matter which agent
the user is running it from. All steps are idempotent; re-running on an
already-installed machine just updates and reconnects.

Concretely, paste this into your agent:

> "Read INSTALLATION.md from https://github.com/tot0rokr/ctags-indexing-mcp
> and install + register the MCP server in whatever client you are running
> inside."

Manual install is also fine if you prefer; the same commands are in
INSTALLATION.md. After installation, restart your MCP client so it picks up
the new server.

## Typical session

Inside your MCP client (Claude Code, Cursor, etc.), just ask:

> "Index this project at ~/work/foo and set me up so vim auto-attaches."

The agent will call `analyze` → `index_create` → `editor_setup` in sequence.
Then in your shell:

```bash
source ~/work/foo/.codeindex/activate.sh
vim some/file.c   # tags and cscope DB attached automatically
```

To persist across shells, add the `source ...` line to `~/.bashrc` /
`~/.zshrc`.

## What `activate.sh` does

The script defines a shell function `vim` that wraps the real `vim`/`nvim`
binary. It:

1. Detects whether `vim` resolves to neovim (via alias or symlink).
2. Adds `--cmd 'set tags+=<abs path>'` so ctags lookups work from any cwd.
3. Adds `-c 'silent! Cs db add <abs path>'` for neovim with
   `cscope_maps.nvim`, or `-c 'silent! cs add ...'` for real vim.

Because a shell function takes precedence over the `alias vim='nvim'` you may
already have, this composes cleanly.

## `.gitignore`

Add a single line to your project's `.gitignore`:

```
.codeindex/
```

## Limitations

- cscope itself only understands C/C++ (and is happy enough on assembly).
  Python files are indexed by ctags only.
- For TypeScript/Rust/Go projects, LSP (clangd / rust-analyzer / gopls / tsserver)
  gives you a far better experience. This tool does not try to compete there.
- The `vim` wrapper is shell-scoped: source the activation script in every
  shell or put it in your rc file.
