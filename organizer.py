#!/usr/bin/env python3
"""
File Organizer Bot
==================

A cross‑platform bot that tidies a folder automatically using rules (by extension, name patterns,
size, and creation date). Works as a one‑shot command **or** a background watcher.

This script is based on the specification described in the project README. It supports
customizable categorization rules, date bucketing, exclusion patterns, dry‑run and undo
operations, and optional real‑time watching of the source directory via the watchdog library.

Usage:

    python organizer.py --config config.yaml            # one‑shot organization
    python organizer.py --config config.yaml --dry      # preview actions
    python organizer.py --config config.yaml --undo     # undo last run
    python organizer.py --config config.yaml --watch    # watch mode (requires watchdog)

"""

import argparse
import os
import re
import shutil
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    from rich import print  
    from rich.table import Table  
    from rich.console import Console  
except Exception:
   
    pass

import yaml  

try:
    from watchdog.observers import Observer  
    from watchdog.events import FileSystemEventHandler  
    WATCHDOG_AVAILABLE = True
except Exception:
    WATCHDOG_AVAILABLE = False


MOVE_LOG = ".moves.log"


@dataclass
class Rule:
    """Represents an advanced rule for classifying files."""

    name: str
    regex: Optional[re.Pattern]
    exts: Optional[List[str]]
    min_mb: Optional[float]
    max_mb: Optional[float]
    to_category: Optional[str]


def load_config(cfg_path: Path) -> dict:
    """Load and normalize the YAML configuration file."""
    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f) or {}
    
    if "extensions" in cfg:
        cfg["extensions"] = {k: [x.lower() for x in v] for k, v in cfg["extensions"].items()}
    return cfg


def compile_rules(cfg: dict) -> List[Rule]:
    """Compile advanced rules from the configuration into Rule objects."""
    rules: List[Rule] = []
    for raw in cfg.get("rules", []) or []:
        pattern = re.compile(raw.get("if_name_regex")) if raw.get("if_name_regex") else None
        exts = [x.lower() for x in raw.get("if_ext_in", [])] or None
        rules.append(
            Rule(
                name=raw.get("name", "unnamed"),
                regex=pattern,
                exts=exts,
                min_mb=raw.get("min_size_mb"),
                max_mb=raw.get("max_size_mb"),
                to_category=raw.get("to_category"),
            )
        )
    return rules


def size_mb(p: Path) -> float:
    """Return the size of a file in megabytes. Returns 0.0 if file is missing."""
    try:
        return p.stat().st_size / (1024 * 1024)
    except FileNotFoundError:
        return 0.0


def matches_rule(p: Path, rule: Rule) -> bool:
    """Check whether a file matches an advanced rule."""
    if rule.regex and not rule.regex.search(p.name):
        return False
    if rule.exts:
        if p.suffix.lower().lstrip(".") not in rule.exts:
            return False
    s = size_mb(p)
    if rule.min_mb is not None and s < rule.min_mb:
        return False
    if rule.max_mb is not None and s > rule.max_mb:
        return False
    return True


def pick_category(p: Path, cfg: dict, rules: List[Rule]) -> str:
    """Determine the destination category for a file based on rules and extension mapping."""
    
    for r in rules:
        if matches_rule(p, r) and r.to_category:
            return r.to_category

    ext = p.suffix.lower().lstrip(".")
    ext_map: Dict[str, List[str]] = cfg.get("extensions", {})
    for cat, exts in ext_map.items():
        if ext in exts:
            return cat
   
    return cfg.get("unknown_category", "Other")


def with_date_bucket(base: Path, category: str, cfg: dict, p: Path) -> Path:
    """Add date bucketing to the destination path based on configuration."""
    mode = cfg.get("bucket_mode", "none")
    dest = base / category
    try:
        ts = p.stat().st_mtime
    except FileNotFoundError:
        ts = datetime.now().timestamp()
    dt = datetime.fromtimestamp(ts)
    if mode == "year":
        dest = dest / f"{dt:%Y}"
    elif mode == "year_month":
        dest = dest / f"{dt:%Y}" / f"{dt:%m}"
    return dest


def dedup_path(dest: Path) -> Path:
    """Generate a unique destination path if the target file already exists."""
    if not dest.exists():
        return dest
    stem = dest.stem
    suffix = dest.suffix
    parent = dest.parent
    i = 1
    while True:
        candidate = parent / f"{stem} ({i}){suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def should_exclude(p: Path, cfg: dict) -> bool:
    """Check whether a file should be skipped based on exclusion patterns."""
    patterns = [re.compile(x) for x in (cfg.get("exclude_regex") or [])]
    return any(rx.search(p.name) for rx in patterns)


def move_file(src: Path, dest: Path, dry: bool, moved: List[Tuple[Path, Path]]):
    """Move a file to its destination, handling deduplication and tracking moves."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    final = dedup_path(dest)
    if dry:
        print(f"[yellow]DRY[/yellow] {src} → {final}")
    else:
        shutil.move(str(src), str(final))
        moved.append((final, src))  
        print(f"[green]MOVED[/green] {src} → {final}")


def save_move_log(base: Path, moved: List[Tuple[Path, Path]]):
    """Save the list of moves to a log file for undo."""
    if not moved:
        return
    log = base / MOVE_LOG
    with open(log, "w", encoding="utf-8") as f:
        for newp, oldp in moved:
            f.write(f"{newp}\t{oldp}\n")


def undo_last(base: Path):
    """Undo the last one‑shot organization by reading the move log."""
    log = base / MOVE_LOG
    if not log.exists():
        print("[red]Nothing to undo.[/red]")
        return
    lines = log.read_text(encoding="utf-8").splitlines()
    undone = 0
    for line in lines:
        try:
            newp, oldp = line.split("\t", 1)
            newp, oldp = Path(newp), Path(oldp)
            oldp.parent.mkdir(parents=True, exist_ok=True)
            if newp.exists():
                shutil.move(str(newp), str(oldp))
                undone += 1
                print(f"[cyan]UNDO[/cyan] {newp} → {oldp}")
        except Exception as e:
            print(f"[red]UNDO error:[/red] {e}")
    log.unlink(missing_ok=True)
    print(f"[bold]Undone:[/bold] {undone} files")


def organize_once(cfg: dict, dry: bool = False) -> int:
    """Perform a single organization run based on the configuration."""
    src = Path(cfg["source_dir"]).expanduser()
    tgt = Path(cfg["target_dir"]).expanduser()

    rules = compile_rules(cfg)
    moved: List[Tuple[Path, Path]] = []

    count = 0
    for entry in src.iterdir():
        p = entry
        if not p.is_file():
            continue
        if should_exclude(p, cfg):
            continue
        cat = pick_category(p, cfg, rules)
        dest_dir = with_date_bucket(tgt, cat, cfg, p)
        dest = dest_dir / p.name
        move_file(p, dest, dry, moved)
        count += 1

    if not dry:
        save_move_log(tgt, moved)
    return count


class _Handler(FileSystemEventHandler):
    """Internal handler for watchdog events in watch mode."""

    def __init__(self, cfg: dict, dry: bool = False):
        super().__init__()
        self.cfg = cfg
        self.dry = dry
        self.rules = compile_rules(cfg)
        self.tgt = Path(cfg["target_dir"]).expanduser()

    def on_created(self, event):
        if event.is_directory:
            return
        p = Path(event.src_path)
        if should_exclude(p, self.cfg):
            return
        cat = pick_category(p, self.cfg, self.rules)
        dest_dir = with_date_bucket(self.tgt, cat, self.cfg, p)
        dest = dest_dir / p.name
        move_file(p, dest, self.dry, moved=[])  


def run_watch(cfg: dict, dry: bool = False):
    """Run the bot in continuous watch mode using the watchdog library."""
    if not WATCHDOG_AVAILABLE:
        print("[red]watchdog not installed. Run: pip install watchdog[/red]")
        sys.exit(2)
    src = Path(cfg["source_dir"]).expanduser()
    handler = _Handler(cfg, dry)
    obs = Observer()
    obs.schedule(handler, str(src), recursive=False)
    obs.start()
    print(f"[bold]Watching[/bold] {src} — press Ctrl+C to stop.")
    try:
        while True:
            obs.join(1)
    except KeyboardInterrupt:
        obs.stop()
    obs.join()


def main() -> None:
    """Entry point of the script; parse arguments and dispatch actions."""
    ap = argparse.ArgumentParser(description="File Organizer Bot")
    ap.add_argument(
        "--config", default="config.yaml", help="Path to config.yaml"
    )
    ap.add_argument(
        "--dry", action="store_true", help="Preview actions without moving"
    )
    ap.add_argument(
        "--watch", action="store_true", help="Watch source directory in real time"
    )
    ap.add_argument(
        "--undo", action="store_true", help="Undo the last run (one‑shot mode)"
    )
    args = ap.parse_args()

    cfg = load_config(Path(args.config))

    if args.undo:
        undo_last(Path(cfg["target_dir"]).expanduser())
        return

    if args.watch:
        run_watch(cfg, args.dry)
    else:
        count = organize_once(cfg, args.dry)
        print(f"[bold]Processed:[/bold] {count} files")


if __name__ == "__main__":
    main()
