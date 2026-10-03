from __future__ import annotations

import argparse
import fnmatch
import os
import re
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

SKIP_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".jj",
}

BINARY_SNIFF = 8192


@dataclass
class Rule:
    pattern: str
    replacement: str
    ignore_case: bool = True

    def compile(self) -> re.Pattern[str]:
        flags = re.IGNORECASE if self.ignore_case else 0
        return re.compile(self.pattern, flags)

    def apply(self, text: str) -> tuple[str, int]:
        return self.compile().subn(self.replacement, text)


@dataclass
class RuleFile:
    path: str
    pattern: str
    ignore_case: bool


def parse_rule_line(line: str, source: str) -> Rule | None:
    stripped = line.strip()
    if not stripped or stripped.startswith("#"):
        return None
    ignore_case = True
    if stripped.startswith("case:"):
        ignore_case = False
        stripped = stripped[len("case:") :].strip()
    if "==>" in stripped:
        pattern, replacement = stripped.split("==>", 1)
    else:
        pattern, replacement = stripped, ""
    pattern = pattern.strip()
    replacement = replacement.strip()
    if not pattern:
        raise SystemExit(f"error: empty pattern in {source}")
    return Rule(pattern=pattern, replacement=replacement, ignore_case=ignore_case)


def load_rules(paths: list[str]) -> list[Rule]:
    rules: list[Rule] = []
    for path in paths:
        for lineno, line in enumerate(Path(path).read_text(encoding="utf-8").splitlines(), 1):
            rule = parse_rule_line(line, f"{path}:{lineno}")
            if rule:
                rules.append(rule)
    return rules


def build_rules(args: argparse.Namespace) -> list[Rule]:
    rules: list[Rule] = []
    if args.pattern:
        rules.append(
            Rule(
                pattern=args.pattern,
                replacement=args.replacement or "",
                ignore_case=not args.case_sensitive,
            )
        )
    file_rules = load_rules(args.rules)
    rules.extend(file_rules)
    if not rules:
        raise SystemExit("error: give a PATTERN or --rules FILE")
    return rules


def is_binary(data: bytes) -> bool:
    chunk = data[:BINARY_SNIFF]
    return b"\x00" in chunk


def iter_files(root: Path, skip_dirs: tuple[Path, ...] = ()) -> list[Path]:
    skip_resolved = {p.resolve() for p in skip_dirs}
    if root.resolve() in skip_resolved:
        return []
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirpath_p = Path(dirpath)
        dirnames[:] = [
            d
            for d in dirnames
            if d not in SKIP_DIRS and (dirpath_p / d).resolve() not in skip_resolved
        ]
        for name in filenames:
            files.append(dirpath_p / name)
    return files


def included(path: Path, root: Path, includes: list[str], excludes: list[str]) -> bool:
    try:
        rel = path.relative_to(root)
    except ValueError:
        rel = path
    rel_str = rel.as_posix()
    if includes:
        if not any(fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(path.name, pat) for pat in includes):
            return False
    if any(fnmatch.fnmatch(rel_str, pat) or fnmatch.fnmatch(path.name, pat) for pat in excludes):
        return False
    return True


def scrub_worktree(
    root: Path,
    rules: list[Rule],
    includes: list[str],
    excludes: list[str],
    dry_run: bool,
    skip_dirs: tuple[Path, ...] = (),
) -> tuple[int, int, list[Path]]:
    files_changed = 0
    total_subs = 0
    changed: list[Path] = []
    for path in iter_files(root, skip_dirs):
        if not included(path, root, includes, excludes):
            continue
        data = path.read_bytes()
        if is_binary(data):
            continue
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            continue
        new_text = text
        subs = 0
        for rule in rules:
            new_text, n = rule.apply(new_text)
            subs += n
        if subs == 0:
            continue
        files_changed += 1
        total_subs += subs
        changed.append(path)
        print(f"{path}: {subs} replacement(s)")
        if not dry_run:
            path.write_text(new_text, encoding="utf-8")
    return files_changed, total_subs, changed


def find_filter_repo() -> str:
    exe = shutil.which("git-filter-repo")
    if exe:
        return exe
    raise SystemExit(
        "error: git-filter-repo not found. It is a dependency of this project; "
        "run inside the uv project so it is installed (uv run scrub ...)."
    )


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(repo), *args],
        check=check,
        capture_output=True,
        text=True,
    )


def write_replace_file(rules: list[Rule], path: Path, prefix: str) -> None:
    lines: list[str] = []
    for rule in rules:
        pattern = rule.pattern
        if not rule.ignore_case:
            pattern = f"(?-i){pattern}"
        lines.append(f"regex:{pattern}==>{prefix}{rule.replacement}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def rewrite_history(
    repo: Path,
    rules: list[Rule],
    messages: bool,
    force: bool,
) -> None:
    filter_repo = find_filter_repo()
    top = Path(git(repo, "rev-parse", "--show-toplevel").stdout.strip())
    if top != repo:
        repo = top

    dirty = git(repo, "status", "--porcelain").stdout.strip()
    if dirty:
        raise SystemExit(
            "error: commit or stash your changes before rewriting history"
        )

    origin_url: str | None = None
    origin = git(repo, "remote", "get-url", "origin", check=False)
    if origin.returncode == 0:
        origin_url = origin.stdout.strip()

    with tempfile.TemporaryDirectory(prefix="scrub-") as tmp:
        tmpdir = Path(tmp)
        text_file = tmpdir / "replace-text.txt"
        write_replace_file(rules, text_file, prefix="")
        cmd = [filter_repo, "--force", "--replace-text", str(text_file)]
        if messages:
            msg_file = tmpdir / "replace-message.txt"
            write_replace_file(rules, msg_file, prefix="")
            cmd += ["--replace-message", str(msg_file)]
        if not force:
            print("Rewriting git history (content and messages)...")
        result = subprocess.run(cmd, cwd=str(repo), text=True)
        if result.returncode != 0:
            raise SystemExit(f"error: git-filter-repo failed with code {result.returncode}")

    if origin_url:
        git(repo, "remote", "add", "origin", origin_url, check=False)
        print(f"restored remote origin -> {origin_url}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="scrub",
        description="Regex scrubber for file contents and git history.",
    )
    parser.add_argument("pattern", nargs="?", help="regex to find")
    parser.add_argument("replacement", nargs="?", help="replacement text")
    parser.add_argument(
        "--rules",
        action="append",
        default=[],
        metavar="FILE",
        help="rules file: one 'regex ==> replacement' per line (# comments)",
    )
    parser.add_argument("--path", default=".", help="root directory (default: .)")
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="only files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--case-sensitive",
        action="store_true",
        help="match case (default is case-insensitive)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show changes only")
    parser.add_argument(
        "--history",
        action="store_true",
        help="also rewrite git history (contents + messages)",
    )
    parser.add_argument(
        "--no-messages",
        action="store_true",
        help="with --history, do not touch commit messages",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="allow history rewrite on a non-fresh repo",
    )
    args = parser.parse_args(argv)

    rules = build_rules(args)
    root = Path(args.path).resolve()

    print(f"Rules: {len(rules)}  Root: {root}")
    files_changed, total_subs, _ = scrub_worktree(
        root, rules, args.include, args.exclude, args.dry_run
    )
    verb = "would change" if args.dry_run else "changed"
    print(f"Worktree: {verb} {files_changed} file(s), {total_subs} replacement(s)")

    if args.history and not args.dry_run:
        rewrite_history(root, rules, messages=not args.no_messages, force=args.force)
        print("History rewrite complete. Force-push to update the remote.")
    elif args.history:
        print("History rewrite skipped (dry run).")

    return 0


def polish_main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="polish",
        description="Apply the built-in polish rules to file contents.",
    )
    parser.add_argument("--path", default=".", help="root directory (default: .)")
    parser.add_argument(
        "--rules",
        action="append",
        default=[],
        metavar="FILE",
        help="extra rules file: one 'regex ==> replacement' per line",
    )
    parser.add_argument(
        "--include",
        action="append",
        default=[],
        metavar="GLOB",
        help="only files matching this glob (repeatable)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        metavar="GLOB",
        help="skip files matching this glob (repeatable)",
    )
    parser.add_argument("--dry-run", action="store_true", help="show changes only")
    args = parser.parse_args(argv)

    package_dir = Path(__file__).resolve().parent
    bundled = package_dir / "polish_rules.txt"
    rules = load_rules([str(bundled), *args.rules])
    root = Path(args.path).resolve()

    print(f"Polish rules: {len(rules)}  Root: {root}")
    files_changed, total_subs, _ = scrub_worktree(
        root,
        rules,
        args.include,
        args.exclude,
        args.dry_run,
        skip_dirs=(package_dir,),
    )
    verb = "would change" if args.dry_run else "changed"
    print(f"Polish: {verb} {files_changed} file(s), {total_subs} replacement(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
