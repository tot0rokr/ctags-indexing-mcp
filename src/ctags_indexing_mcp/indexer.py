from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from .analyzer import LANGUAGE_EXTENSIONS, EXTRA_TEXT_EXTENSIONS

DEFAULT_OUTPUT_DIRNAME = ".codeindex"

CSCOPE_LANGS = {"c", "cpp", "asm"}


@dataclass
class IndexResult:
    root: Path
    output_dir: Path
    files_indexed: int
    cscope_built: bool
    ctags_built: bool
    languages: list[str]
    excluded: list[str]
    warnings: list[str]
    gitignore_status: str = "not_a_git_repo"

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "output_dir": str(self.output_dir),
            "files_indexed": self.files_indexed,
            "cscope_built": self.cscope_built,
            "ctags_built": self.ctags_built,
            "languages": self.languages,
            "excluded": self.excluded,
            "warnings": self.warnings,
            "gitignore_status": self.gitignore_status,
        }


def _is_git_repo(root: Path) -> bool:
    return (root / ".git").exists()


def _ensure_gitignored(root: Path, entry: str) -> str:
    """Append `entry` to <root>/.gitignore if the project is a git repo and the
    entry (or an equivalent variant) is not already listed. Returns one of:
      - "not_a_git_repo"
      - "already_present"
      - "appended"
    """
    if not _is_git_repo(root):
        return "not_a_git_repo"

    gitignore = root / ".gitignore"
    canonical = entry.strip("/")
    variants = {canonical, canonical + "/", "/" + canonical, "/" + canonical + "/"}

    existing = gitignore.read_text().splitlines() if gitignore.is_file() else []
    for line in existing:
        if line.strip() in variants:
            return "already_present"

    needs_leading_nl = bool(existing) and existing[-1] != ""
    with gitignore.open("a") as f:
        if needs_leading_nl:
            f.write("\n")
        f.write(f"{entry}\n")
    return "appended"


def _extensions_for(languages: list[str], include_dts: bool = True) -> list[str]:
    exts: list[str] = []
    for lang in languages:
        exts.extend(LANGUAGE_EXTENSIONS.get(lang, ()))
    if include_dts and any(l in languages for l in ("c", "cpp")):
        exts.extend(EXTRA_TEXT_EXTENSIONS)
    return sorted(set(exts))


def _collect_files(root: Path, exts: list[str], excludes: list[str]) -> list[Path]:
    excluded_set = set(excludes)
    ext_set = set(exts)
    files: list[Path] = []

    def walk(d: Path) -> None:
        try:
            entries = list(d.iterdir())
        except (PermissionError, OSError):
            return
        for entry in entries:
            name = entry.name
            if entry.is_symlink() and entry.is_dir():
                continue
            if entry.is_dir():
                if name in excluded_set:
                    continue
                walk(entry)
            elif entry.is_file():
                if entry.suffix in ext_set:
                    files.append(entry)

    walk(root)
    files.sort()
    return files


def _write_cscope_files_list(files: list[Path], dest: Path) -> None:
    with dest.open("w") as f:
        for p in files:
            f.write(f"{p}\n")


def _run(cmd: list[str], cwd: Path) -> tuple[int, str, str]:
    proc = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True)
    return proc.returncode, proc.stdout, proc.stderr


def build_index(
    root: Path,
    languages: list[str],
    excludes: list[str],
    output_dir: Path | None = None,
) -> IndexResult:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")

    output_dir = (output_dir or (root / DEFAULT_OUTPUT_DIRNAME)).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    warnings: list[str] = []
    exts = _extensions_for(languages)
    if not exts:
        raise ValueError(f"no extensions for languages={languages}")

    files = _collect_files(root, exts, excludes)
    cscope_files_path = output_dir / "cscope.files"

    cscope_inputs = [p for p in files if any(str(p).endswith(e) for e in _extensions_for(
        [l for l in languages if l in CSCOPE_LANGS]
    ))]
    if not cscope_inputs:
        cscope_inputs = files

    _write_cscope_files_list(cscope_inputs, cscope_files_path)

    cscope_built = False
    want_cscope = bool(set(languages) & CSCOPE_LANGS)
    if want_cscope:
        if shutil.which("cscope") is None:
            warnings.append("cscope not found in PATH; skipping cscope DB")
        else:
            rc, out, err = _run(
                ["cscope", "-bqk", "-i", str(cscope_files_path)],
                cwd=output_dir,
            )
            if rc != 0:
                warnings.append(f"cscope exited {rc}: {err.strip() or out.strip()}")
            else:
                cscope_built = True

    ctags_built = False
    if shutil.which("ctags") is None:
        warnings.append("ctags not found in PATH; skipping tags")
    else:
        ctags_input_path = output_dir / "ctags.files"
        _write_cscope_files_list(files, ctags_input_path)
        ctags_cmd = [
            "ctags",
            "--fields=+iaSl",
            "--extras=+q",
            "--c-kinds=+p",
            "--c++-kinds=+p",
            "--langmap=C++:+.hh.hpp.hxx,C:+.S",
            "-f", str(output_dir / "tags"),
            "-L", str(ctags_input_path),
        ]
        rc, out, err = _run(ctags_cmd, cwd=output_dir)
        if rc != 0:
            warnings.append(f"ctags exited {rc}: {err.strip() or out.strip()}")
        else:
            ctags_built = True
        try:
            ctags_input_path.unlink()
        except FileNotFoundError:
            pass

    try:
        rel_output = output_dir.relative_to(root)
        gitignore_status = _ensure_gitignored(root, f"{rel_output}/")
    except ValueError:
        gitignore_status = "skipped_external_output_dir"

    return IndexResult(
        root=root,
        output_dir=output_dir,
        files_indexed=len(files),
        cscope_built=cscope_built,
        ctags_built=ctags_built,
        languages=languages,
        excluded=excludes,
        warnings=warnings,
        gitignore_status=gitignore_status,
    )


def index_status(root: Path, output_dir: Path | None = None) -> dict:
    root = root.resolve()
    output_dir = (output_dir or (root / DEFAULT_OUTPUT_DIRNAME)).resolve()
    artifacts = ["cscope.files", "cscope.out", "cscope.in.out", "cscope.po.out", "tags"]
    status: dict = {
        "root": str(root),
        "output_dir": str(output_dir),
        "exists": output_dir.is_dir(),
        "artifacts": {},
    }
    for name in artifacts:
        p = output_dir / name
        if p.is_file():
            st = p.stat()
            status["artifacts"][name] = {"size": st.st_size, "mtime": st.st_mtime}
        else:
            status["artifacts"][name] = None

    files_list = output_dir / "cscope.files"
    if files_list.is_file():
        with files_list.open() as f:
            status["files_listed"] = sum(1 for _ in f)
    return status
