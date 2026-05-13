from __future__ import annotations

from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from .analyzer import analyze as analyze_project
from .indexer import build_index, index_status
from .editor import generate_activate_script
from .config import save_config, load_config

mcp = FastMCP("ctags-indexing")


def _resolve_path(path: Optional[str]) -> tuple[Path, str]:
    """Resolve the project root. Returns (root, source) where source is
    "explicit" if the caller passed a path, or "cwd_fallback" if we used the
    server process's own cwd as a last-resort fallback.

    The agent calling this server is expected to figure out the user's project
    root and pass it explicitly. The cwd fallback exists only so the tool
    still does *something* sensible when path is omitted; it may or may not
    point at what the user actually has open."""
    if path:
        return Path(path).expanduser().resolve(), "explicit"
    return Path.cwd().resolve(), "cwd_fallback"


def _resolve_output(root: Path, output_dir: Optional[str]) -> Path:
    if output_dir:
        return Path(output_dir).expanduser().resolve()
    return root


@mcp.tool()
def analyze(path: Optional[str] = None) -> dict:
    """Scan a project directory and report language/file-counts/build-systems
    and a recommended exclude list. Read-only; does not write anything to
    disk.

    IMPORTANT: figure out the user's project root yourself (e.g. from the
    user's current shell, the path of an open file, or a Git toplevel) and
    pass it as `path`. Only omit `path` if you genuinely have no clue — in
    that case the server falls back to its own cwd, which usually mirrors
    the directory the user was in when the MCP client launched the server,
    but is not guaranteed to be the right project. The response includes
    `path_source` ("explicit" or "cwd_fallback") so you can confirm.
    """
    root, source = _resolve_path(path)
    result = analyze_project(root).to_dict()
    result["path_source"] = source
    return result


@mcp.tool()
def index_create(
    path: Optional[str] = None,
    languages: Optional[list[str]] = None,
    excludes: Optional[list[str]] = None,
    output_dir: Optional[str] = None,
) -> dict:
    """Build cscope and ctags indexes for a project. Artifacts are written
    **directly into the project root** by default (cscope.files, cscope.out,
    cscope.in.out, cscope.po.out, tags, codeindex-activate.sh on
    editor_setup, .codeindex.config.json). Never a global cache. The result
    is always per-project — pass a different `path` for a different project.

    IMPORTANT (project root): figure out the user's project root yourself
    (Git toplevel, the directory containing pyproject.toml/CMakeLists.txt,
    the open file's nearest ancestor, etc.) and pass it as `path`. If `path`
    is omitted, the server uses its own cwd as a last-resort fallback —
    convenient when the MCP client spawns the server in the user's working
    directory, but not always correct. The response's `path_source` field
    tells you which one was used.

    .gitignore behavior: when `path` is a git repository, the artifact names
    are appended to `<path>/.gitignore` (idempotent — existing entries are
    left alone). When `output_dir` is given and points at a subdirectory of
    `path`, that subdirectory is gitignored instead. The result has a
    `gitignore` field with `status`/`appended`/`already_present`.

    Args:
        path: Project root. Default: server cwd (fallback).
        languages: Subset of {"c","cpp","asm","python"}. Default: auto-detect.
        excludes: Directory basenames to skip. Default: auto-detect.
        output_dir: Where to put artifacts. Default: `path` itself (root).
    """
    root, source = _resolve_path(path)
    analysis = analyze_project(root)
    langs = languages or analysis.detected_languages
    excl = excludes or analysis.recommended_excludes
    out = _resolve_output(root, output_dir)
    result = build_index(root, langs, excl, out)
    save_config(out, langs, excl)
    result_dict = result.to_dict()
    result_dict["path_source"] = source
    return result_dict


@mcp.tool()
def index_regen(path: Optional[str] = None, output_dir: Optional[str] = None) -> dict:
    """Rebuild indexes for a project, reusing the previously saved languages
    and excludes from `.codeindex.config.json`. Falls back to fresh
    detection if no config is found. Same path-resolution rules as
    index_create."""
    root, source = _resolve_path(path)
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
    result_dict = result.to_dict()
    result_dict["path_source"] = source
    return result_dict


@mcp.tool(name="index_status")
def index_status_tool(path: Optional[str] = None, output_dir: Optional[str] = None) -> dict:
    """Report which index artifacts exist in the project root (or in
    `output_dir` if given) and their sizes/mtimes."""
    root, source = _resolve_path(path)
    out = _resolve_output(root, output_dir)
    result = index_status(root, out)
    result["path_source"] = source
    return result


@mcp.tool()
def editor_setup(path: Optional[str] = None, output_dir: Optional[str] = None) -> dict:
    """Generate `<output>/codeindex-activate.sh`. Source it once per shell to
    make any `vim` invocation auto-attach tags + cscope DB. Auto-detects
    whether `vim` resolves to neovim (uses cscope_maps.nvim's :Cs) or real
    vim (uses :cs). Same path-resolution rules as index_create."""
    root, source = _resolve_path(path)
    out = _resolve_output(root, output_dir)
    activate = generate_activate_script(out, root)
    return {
        "activate_script": str(activate),
        "source_command": f"source {activate}",
        "persist_hint": (
            f"add this line to ~/.bashrc (or ~/.zshrc) to load on every shell:  "
            f"source {activate}"
        ),
        "path_source": source,
    }


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
