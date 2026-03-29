#!/usr/bin/env python3
"""
create_panes.py — Zellij pane creator for the zellij-agents skill.

Creates a grid of Claude agent panes in the current Zellij session.
Must be run from inside a Zellij session ($ZELLIJ env var set).

Usage:
    python3 create_panes.py --agents '<JSON>' [--dry-run]

JSON format:
    [{"name": "Backend Dev", "role": "Handle API design and server logic"}, ...]

The main agent pane (top-left, [0,0]) is always the caller's current pane.
Sub-agents are started with --append-system-prompt to inject their role.
"""

import argparse
import json
import math
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


# ─── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Agent:
    name: str
    role: str


# ─── Claude binary detection ──────────────────────────────────────────────────

def find_real_claude() -> str:
    """Return path to the real claude binary, robust to auto-updates."""
    versions_dir = Path.home() / ".local" / "share" / "claude" / "versions"
    if versions_dir.is_dir():
        candidates = [
            p for p in versions_dir.iterdir()
            if p.is_file() and os.access(p, os.X_OK)
        ]
        if candidates:
            return str(max(candidates, key=lambda p: p.stat().st_mtime))

    this_file = Path(__file__).resolve()
    found = shutil.which("claude")
    if found and Path(found).resolve() != this_file:
        return found

    print("ERROR: Cannot locate claude binary. Ensure Claude Code is installed.", file=sys.stderr)
    sys.exit(1)


# ─── Grid layout ──────────────────────────────────────────────────────────────

def calculate_grid(total_panes: int) -> tuple[int, int]:
    """
    Return (rows, cols) for a landscape-biased grid that fits total_panes.

    Selects the arrangement closest to a 1.5 aspect ratio (cols/rows ≈ 1.5)
    while minimising empty cells.

    Examples:
        total=2  → (1, 2)   [main | ag1]
        total=3  → (1, 3)   [main | ag1 | ag2]
        total=4  → (2, 2)
        total=5  → (2, 3)   2×3 grid, 1 empty slot
        total=6  → (2, 3)
        total=7  → (2, 4)   2×4 grid, 1 empty slot
        total=8  → (2, 4)
        total=9  → (3, 3)
        total=10 → (2, 5)
    """
    if total_panes == 1:
        return (1, 1)

    best_cols = math.ceil(math.sqrt(total_panes * 1.5))
    candidates = []
    for cols in range(max(1, best_cols - 1), best_cols + 4):
        rows = math.ceil(total_panes / cols)
        if cols < rows:          # enforce cols >= rows (landscape)
            continue
        empty = rows * cols - total_panes
        ratio_err = abs(cols / rows - 1.5)
        candidates.append((empty, ratio_err, rows, cols))

    if not candidates:
        # Fallback: single row
        return (1, total_panes)

    candidates.sort()
    _, _, rows, cols = candidates[0]
    return rows, cols


def build_grid(agents: list[Agent], rows: int, cols: int) -> list[list[Optional[Agent]]]:
    """Assign agents to grid cells in reading order (left->right, top->bottom)."""
    grid: list[list[Optional[Agent]]] = [[None] * cols for _ in range(rows)]
    for idx, agent in enumerate(agents):
        r, c = divmod(idx, cols)
        if r < rows:
            grid[r][c] = agent
    return grid


def col_height(total: int, cols: int, col_idx: int) -> int:
    """Number of rows occupied in column col_idx for a grid with total agents."""
    return math.ceil((total - col_idx) / cols)


# ─── In-session pane creation ─────────────────────────────────────────────────

def _zellij(*args: str, dry_run: bool = False) -> None:
    cmd = ["zellij"] + list(args)
    if dry_run:
        print(f"  [dry-run] {' '.join(cmd)}")
    else:
        subprocess.run(cmd, check=False)


def create_panes_in_session(
    grid: list[list[Optional[Agent]]],
    real_claude: str,
    main_agent_name: str = "Main Agent",
    dry_run: bool = False,
) -> None:
    """
    Add agent panes to the current Zellij session.

    Phase 1: fill first row by splitting right from main.
    Phase 2: fill subsequent rows right-to-left, returning focus to [0,0].
    """
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    total = sum(1 for r in grid for c in r if c is not None)

    def system_prompt(agent: Agent) -> str:
        return (
            f"You are {agent.name}. {agent.role}. "
            "You are part of a coordinated multi-agent team. "
            "The main agent (top-left pane) will coordinate your work."
        )

    def run_agent_pane(agent: Agent, direction: str) -> None:
        _zellij("run", "-d", direction, "-n", agent.name, "--close-on-exit",
                "--", real_claude, "--append-system-prompt", system_prompt(agent),
                dry_run=dry_run)
        # Claude Code overrides the -n name via terminal title escape sequences,
        # so explicitly rename the pane (focus is on the newly created pane).
        if not dry_run:
            time.sleep(0.3)
        _zellij("action", "rename-pane", agent.name, dry_run=dry_run)

    # Rename the current (main) pane so it matches the grid label
    _zellij("action", "rename-pane", main_agent_name, dry_run=dry_run)

    # Phase 1: first row (col 1 ... cols-1) — split right from main
    for c in range(1, cols):
        agent = grid[0][c]
        if agent is None:
            continue
        run_agent_pane(agent, "right")

    # Phase 2: remaining rows, right->left
    for c in range(cols - 1, -1, -1):
        c_height = col_height(total, cols, c)
        created_down = 0

        for r in range(1, c_height):
            agent = grid[r][c]
            if agent is None:
                continue
            run_agent_pane(agent, "down")
            created_down += 1

        # Return to top of column
        for _ in range(created_down):
            _zellij("action", "move-focus", "up", dry_run=dry_run)

        # Move to previous column
        if c > 0:
            _zellij("action", "move-focus", "left", dry_run=dry_run)


# ─── Pretty-print the planned grid ───────────────────────────────────────────

def print_grid_summary(grid: list[list[Optional[Agent]]]) -> None:
    rows = len(grid)
    cols = len(grid[0]) if grid else 0
    print(f"\nAgent layout: {rows}x{cols} grid\n")
    col_width = 20
    sep = ("+" + "-" * col_width) * cols + "+"
    print(sep)
    for r in range(rows):
        row_str = "|"
        for c in range(cols):
            agent = grid[r][c]
            if agent is None:
                cell = "(empty)"
            elif r == 0 and c == 0:
                cell = "[Main Agent]"
            else:
                cell = agent.name
            row_str += f" {cell:<{col_width - 1}}|"
        print(row_str)
        print(sep)
    print()


# ─── Entry point ──────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Create Claude agent panes in the current Zellij session.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument(
        "--agents", required=True,
        help='JSON array: [{"name": "...", "role": "..."}, ...]',
    )
    p.add_argument(
        "--dry-run", action="store_true",
        help="Print the zellij commands without executing.",
    )
    return p.parse_args()


def main() -> None:
    args = parse_args()

    # Verify we are inside a Zellij session
    if not os.environ.get("ZELLIJ"):
        print("ERROR: Not inside a Zellij session. $ZELLIJ is not set.", file=sys.stderr)
        print("Start a Zellij session first, then run Claude Code inside it.", file=sys.stderr)
        sys.exit(1)

    # Parse agent definitions
    try:
        raw = json.loads(args.agents)
    except json.JSONDecodeError as e:
        print(f"ERROR: Invalid JSON in --agents: {e}", file=sys.stderr)
        sys.exit(1)

    sub_agents = [Agent(name=a["name"], role=a["role"]) for a in raw]
    if not sub_agents:
        print("ERROR: --agents must contain at least one agent.", file=sys.stderr)
        sys.exit(1)

    main_agent = Agent(name="Main Agent", role="Orchestrate the team")
    all_agents = [main_agent] + sub_agents
    total = len(all_agents)

    # Calculate grid
    rows, cols = calculate_grid(total)
    grid = build_grid(all_agents, rows, cols)

    print_grid_summary(grid)

    real_claude = find_real_claude()

    print(f"Adding {len(sub_agents)} agent pane(s) to current Zellij session...")
    create_panes_in_session(grid, real_claude,
                            main_agent_name=main_agent.name,
                            dry_run=args.dry_run)
    print(f"✓ Created {len(sub_agents)} agent pane(s).")


if __name__ == "__main__":
    main()
