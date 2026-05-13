from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .analyzer import analyze as analyze_project
from .indexer import DEFAULT_OUTPUT_DIRNAME, build_index, index_status
from .editor import generate_activate_script
from .config import save_config, load_config

mcp = FastMCP("ctags-indexing")


def _resolve_output(root: Path, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return (root / DEFAULT_OUTPUT_DIRNAME).resolve()


@mcp.tool()
def analyze(path: str) -> dict:
    """Scan a project directory and report language/file-counts/build-systems and
    a recommended exclude list. Read-only; does not write anything to disk.

    Args:
        path: Absolute or user-home path to the project root.
    """
    root = Path(path).expanduser().resolve()
    return analyze_project(root).to_dict()


@mcp.tool()
def index_create(
    path: str,
    languages: Optional[list[str]] = None,
    excludes: Optional[list[str]] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """Build cscope and ctags indexes for a project. Writes artifacts to
    `<path>/.codeindex/` by default (always scoped to the given project,
    never a global cache). Auto-detects languages and excludes when not
    provided.

    When `path` is a git repository, the relative output directory (e.g.
    `.codeindex/`) is appended to `<path>/.gitignore` if it isn't already
    listed. The returned dict includes `gitignore_status`:
      - "appended"                  : line was added
      - "already_present"           : line already there
      - "not_a_git_repo"            : skipped (no .git in `path`)
      - "skipped_external_output_dir": output_dir is outside `path`

    Args:
        path: Project root directory.
        languages: Subset of {"c","cpp","asm","python"}. Default: auto-detect.
        excludes: Directory basenames to skip. Default: auto-detect.
        output_dir: Where to put cscope/tags. Default: `<path>/.codeindex/`.
    """
    root = Path(path).expanduser().resolve()
    analysis = analyze_project(root)
    langs = languages or analysis.detected_languages
    excl = excludes or analysis.recommended_excludes
    out = _resolve_output(root, output_dir)
    result = build_index(root, langs, excl, out)
    save_config(out, langs, excl)
    return result.to_dict()


@mcp.tool()
def index_regen(path: str, output_dir: Optional[str] = None) -> dict:
    """Rebuild indexes for a project, reusing the previously saved languages
    and excludes from `<output>/config.json`. Falls back to fresh detection
    if no config is found.
    """
    root = Path(path).expanduser().resolve()
    out = _resolve_output(root, output_dir)
    cfg = load_config(out)
    if cfg:
        langs = cfg.get("languages") or []
        excl = cfg.get("excludes") or []
    else:
        a = analyze_project(root)
        langs = a.detected_languages
        excl = a.recommended_excludes
    result = build_index(root, langs, excl, out)
    save_config(out, langs, excl)
    return result.to_dict()


@mcp.tool(name="index_status")
def index_status_tool(path: str, output_dir: Optional[str] = None) -> dict:
    """Report which index artifacts exist and their sizes/mtimes."""
    root = Path(path).expanduser().resolve()
    out = _resolve_output(root, output_dir)
    return index_status(root, out)


@mcp.tool()
def editor_setup(path: str, output_dir: Optional[str] = None) -> dict:
    """Generate `<output>/activate.sh`. Source it once per shell to make any
    `vim` invocation auto-attach tags + cscope DB. Auto-detects whether
    `vim` resolves to neovim (uses cscope_maps.nvim's :Cs) or real vim
    (uses :cs).

    Returns the absolute path and a hint string to print to the user.
    """
    root = Path(path).expanduser().resolve()
    out = _resolve_output(root, output_dir)
    activate = generate_activate_script(out, root)
    return {
        "activate_script": str(activate),
        "source_command": f"source {activate}",
        "persist_hint": (
            f'add this line to ~/.bashrc (or ~/.zshrc) to load on every shell: '
            f'  source {activate}'
        ),
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
