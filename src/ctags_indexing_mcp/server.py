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
def index_create(
    path: Optional[str] = None,
    languages: Optional[list[str]] = None,
    excludes: Optional[list[str]] = None,
    output_dir: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """Analyze a project AND build cscope/ctags indexes in one call.

    The response always includes an `analysis` block (language counts,
    detected build systems, recommended exclude list, total source files).
    When `dry_run=True`, only the analysis is returned and nothing is
    written to disk — useful for previewing what would be indexed without
    paying the time/space cost.

    Artifacts are written **directly into the project root** by default
    (cscope.files, cscope.out, cscope.in.out, cscope.po.out, tags,
    .codeindex.config.json — plus codeindex-activate.sh when you later
    call editor_setup). Never a global cache. Per-project — pass a
    different `path` for a different project.

    IMPORTANT (project root): figure out the user's project root yourself
    (Git toplevel, the directory containing pyproject.toml/CMakeLists.txt,
    the open file's nearest ancestor, etc.) and pass it as `path`. If
    `path` is omitted, the server falls back to its own cwd — convenient
    when the MCP client spawns the server in the user's working directory,
    but not always correct. The response's `path_source` field tells you
    which one was used.

    .gitignore behavior (dry_run=False only): when `path` is a git
    repository, the artifact names are appended to `<path>/.gitignore`
    (idempotent — existing entries are left alone). When `output_dir` is
    given and points at a subdirectory of `path`, that subdirectory is
    gitignored instead. The result has a `gitignore` field with
    `status`/`appended`/`already_present`.

    Args:
        path: Project root. Default: server cwd (fallback).
        languages: Subset of {"c","cpp","asm","python"}. Default: auto-detect.
        excludes: Directory basenames to skip. Default: auto-detect.
        output_dir: Where to put artifacts. Default: `path` itself (root).
        dry_run: If True, run the analysis only and return without writing
            cscope/ctags/config/.gitignore. Default: False.
    """
    root, source = _resolve_path(path)
    analysis = analyze_project(root)
    response: dict = {
        "root": str(root),
        "path_source": source,
        "analysis": analysis.to_dict(),
        "dry_run": dry_run,
    }
    if dry_run:
        return response

    langs = languages or analysis.detected_languages
    excl = excludes or analysis.recommended_excludes
    out = _resolve_output(root, output_dir)
    result = build_index(root, langs, excl, out)
    save_config(out, langs, excl)
    response.update(result.to_dict())
    return response


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
