from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

LANGUAGE_EXTENSIONS: dict[str, tuple[str, ...]] = {
    "c":      (".c", ".h"),
    "cpp":    (".cc", ".cpp", ".cxx", ".hh", ".hpp", ".hxx"),
    "asm":    (".s", ".S"),
    "python": (".py",),
}

EXTRA_TEXT_EXTENSIONS: tuple[str, ...] = (".dts", ".dtsi")

ALWAYS_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git", ".hg", ".svn",
    "__pycache__", ".mypy_cache", ".pytest_cache", ".ruff_cache",
    "node_modules",
    ".venv", "venv", ".tox",
    ".idea", ".vscode",
    "build", "_build", "dist",
)

BUILD_SYSTEM_MARKERS: dict[str, tuple[str, ...]] = {
    "cmake":   ("CMakeLists.txt",),
    "meson":   ("meson.build",),
    "make":    ("Makefile", "GNUmakefile"),
    "cargo":   ("Cargo.toml",),
    "npm":     ("package.json",),
    "python":  ("pyproject.toml", "setup.py", "setup.cfg"),
    "yocto":   ("conf/layer.conf",),
    "bazel":   ("WORKSPACE", "MODULE.bazel"),
    "go":      ("go.mod",),
}

BUILD_SYSTEM_EXCLUDES: dict[str, tuple[str, ...]] = {
    "cmake": ("build", "cmake-build-debug", "cmake-build-release", "_build"),
    "meson": ("build", "builddir"),
    "make":  ("build",),
    "cargo": ("target",),
    "npm":   ("node_modules", "dist", ".next", ".nuxt"),
    "python": (".eggs", "build", "dist"),
    "bazel":  ("bazel-bin", "bazel-out", "bazel-testlogs"),
    "go":     ("vendor",),
}


@dataclass
class ProjectAnalysis:
    root: Path
    file_counts: dict[str, int] = field(default_factory=dict)
    detected_languages: list[str] = field(default_factory=list)
    build_systems: list[str] = field(default_factory=list)
    recommended_excludes: list[str] = field(default_factory=list)
    total_source_files: int = 0

    def to_dict(self) -> dict:
        return {
            "root": str(self.root),
            "file_counts": self.file_counts,
            "detected_languages": self.detected_languages,
            "build_systems": self.build_systems,
            "recommended_excludes": self.recommended_excludes,
            "total_source_files": self.total_source_files,
        }


def _all_source_extensions() -> set[str]:
    exts: set[str] = set()
    for v in LANGUAGE_EXTENSIONS.values():
        exts.update(v)
    exts.update(EXTRA_TEXT_EXTENSIONS)
    return exts


def _detect_build_systems(root: Path) -> list[str]:
    found: list[str] = []
    for system, markers in BUILD_SYSTEM_MARKERS.items():
        for marker in markers:
            hits = list(root.rglob(marker))
            hits = [h for h in hits if not _is_under_excluded(h.relative_to(root), ALWAYS_EXCLUDE_DIRS)]
            if hits:
                found.append(system)
                break
    return found


def _is_under_excluded(rel: Path, excluded: tuple[str, ...]) -> bool:
    parts = set(rel.parts)
    return bool(parts & set(excluded))


def _parse_gitignore_dirs(root: Path) -> list[str]:
    gi = root / ".gitignore"
    if not gi.is_file():
        return []
    out: list[str] = []
    for line in gi.read_text(errors="replace").splitlines():
        s = line.strip()
        if not s or s.startswith("#") or s.startswith("!"):
            continue
        s = s.lstrip("/").rstrip("/")
        if "*" in s or "?" in s or "[" in s:
            continue
        if "/" in s:
            continue
        out.append(s)
    return out


def analyze(root: Path) -> ProjectAnalysis:
    root = root.resolve()
    if not root.is_dir():
        raise FileNotFoundError(f"not a directory: {root}")

    source_exts = _all_source_extensions()
    counts: dict[str, int] = {}
    excluded = set(ALWAYS_EXCLUDE_DIRS)
    total = 0

    for p in root.rglob("*"):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if _is_under_excluded(rel, tuple(excluded)):
            continue
        ext = p.suffix
        if ext in source_exts:
            counts[ext] = counts.get(ext, 0) + 1
            total += 1

    detected = []
    for lang, exts in LANGUAGE_EXTENSIONS.items():
        if any(counts.get(e, 0) for e in exts):
            detected.append(lang)

    build_systems = _detect_build_systems(root)

    rec_excludes = list(ALWAYS_EXCLUDE_DIRS)
    for bs in build_systems:
        for d in BUILD_SYSTEM_EXCLUDES.get(bs, ()):
            if d not in rec_excludes:
                rec_excludes.append(d)
    for d in _parse_gitignore_dirs(root):
        if d not in rec_excludes and d not in ("src", "include", "lib"):
            rec_excludes.append(d)

    return ProjectAnalysis(
        root=root,
        file_counts=dict(sorted(counts.items(), key=lambda kv: -kv[1])),
        detected_languages=detected,
        build_systems=build_systems,
        recommended_excludes=rec_excludes,
        total_source_files=total,
    )
