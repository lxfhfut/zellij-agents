#!/usr/bin/env python3
"""Tests for create_panes.py — the zellij-agents skill script."""

import json
import os
import subprocess
import sys
from io import StringIO
from unittest import mock

import pytest

# Add scripts dir to path so we can import the module
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "scripts"))

from create_panes import (
    Agent,
    build_grid,
    calculate_grid,
    col_height,
    create_panes_in_session,
    find_real_claude,
    main,
    print_grid_summary,
)


# ─── calculate_grid ──────────────────────────────────────────────────────────


class TestCalculateGrid:
    def test_single_pane(self):
        assert calculate_grid(1) == (1, 1)

    def test_two_panes(self):
        rows, cols = calculate_grid(2)
        assert rows == 1
        assert cols == 2

    def test_three_panes(self):
        rows, cols = calculate_grid(3)
        assert rows == 1
        assert cols == 3

    def test_four_panes(self):
        rows, cols = calculate_grid(4)
        assert rows == 2
        assert cols == 2

    def test_six_panes(self):
        rows, cols = calculate_grid(6)
        assert rows == 2
        assert cols == 3

    def test_nine_panes(self):
        rows, cols = calculate_grid(9)
        assert rows == 3
        assert cols == 3

    def test_cols_gte_rows(self):
        """Grid should always be landscape-biased (cols >= rows)."""
        for n in range(1, 21):
            rows, cols = calculate_grid(n)
            assert cols >= rows, f"Failed for n={n}: rows={rows}, cols={cols}"

    def test_fits_all_panes(self):
        """Grid capacity (rows * cols) must be >= total panes."""
        for n in range(1, 21):
            rows, cols = calculate_grid(n)
            assert rows * cols >= n, f"Failed for n={n}: {rows}x{cols} = {rows*cols} < {n}"

    def test_no_excessive_waste(self):
        """Grid should not have more than cols-1 empty cells."""
        for n in range(2, 21):
            rows, cols = calculate_grid(n)
            empty = rows * cols - n
            assert empty < cols, (
                f"Failed for n={n}: {rows}x{cols} has {empty} empty cells (max {cols-1})"
            )


# ─── build_grid ───────────────────────────────────────────────────────────────


class TestBuildGrid:
    def test_single_agent(self):
        agents = [Agent("A", "role")]
        grid = build_grid(agents, 1, 1)
        assert grid[0][0].name == "A"

    def test_2x2_grid(self):
        agents = [Agent(f"A{i}", "role") for i in range(4)]
        grid = build_grid(agents, 2, 2)
        assert grid[0][0].name == "A0"
        assert grid[0][1].name == "A1"
        assert grid[1][0].name == "A2"
        assert grid[1][1].name == "A3"

    def test_partial_grid_has_none(self):
        """A 2x2 grid with 3 agents should have one None cell."""
        agents = [Agent(f"A{i}", "role") for i in range(3)]
        grid = build_grid(agents, 2, 2)
        assert grid[0][0] is not None
        assert grid[0][1] is not None
        assert grid[1][0] is not None
        assert grid[1][1] is None

    def test_reading_order(self):
        """Agents fill left-to-right, top-to-bottom."""
        agents = [Agent(f"A{i}", "role") for i in range(6)]
        grid = build_grid(agents, 2, 3)
        names = [[grid[r][c].name for c in range(3)] for r in range(2)]
        assert names == [["A0", "A1", "A2"], ["A3", "A4", "A5"]]


# ─── col_height ───────────────────────────────────────────────────────────────


class TestColHeight:
    def test_full_grid(self):
        # 2x3 grid, 6 agents total — every column has 2 rows
        for col in range(3):
            assert col_height(6, 3, col) == 2

    def test_partial_last_row(self):
        # 5 agents in 3 cols: col 0 has 2 rows, col 1 has 2 rows, col 2 has 1 row
        assert col_height(5, 3, 0) == 2
        assert col_height(5, 3, 1) == 2
        assert col_height(5, 3, 2) == 1

    def test_single_column(self):
        assert col_height(3, 1, 0) == 3

    def test_single_row(self):
        for col in range(4):
            assert col_height(4, 4, col) == 1


# ─── print_grid_summary ──────────────────────────────────────────────────────


class TestPrintGridSummary:
    def test_output_contains_agent_names(self, capsys):
        agents = [
            Agent("Main Agent", "orchestrate"),
            Agent("Backend", "api"),
            Agent("Frontend", "ui"),
            Agent("QA", "test"),
        ]
        grid = build_grid(agents, 2, 2)
        print_grid_summary(grid, 2, 2)
        output = capsys.readouterr().out
        assert "[Main Agent]" in output
        assert "Backend" in output
        assert "Frontend" in output
        assert "QA" in output

    def test_output_shows_grid_dimensions(self, capsys):
        agents = [Agent(f"A{i}", "role") for i in range(6)]
        grid = build_grid(agents, 2, 3)
        print_grid_summary(grid, 2, 3)
        output = capsys.readouterr().out
        assert "2x3" in output

    def test_empty_cell_shown(self, capsys):
        agents = [Agent(f"A{i}", "role") for i in range(3)]
        grid = build_grid(agents, 2, 2)
        print_grid_summary(grid, 2, 2)
        output = capsys.readouterr().out
        assert "(empty)" in output


# ─── find_real_claude ─────────────────────────────────────────────────────────


class TestFindRealClaude:
    def test_finds_claude_on_path(self):
        with mock.patch("create_panes.shutil.which", return_value="/usr/local/bin/claude"):
            with mock.patch("create_panes.Path.is_dir", return_value=False):
                result = find_real_claude()
                assert result == "/usr/local/bin/claude"

    def test_exits_if_not_found(self):
        with mock.patch("create_panes.shutil.which", return_value=None):
            with mock.patch("create_panes.Path.is_dir", return_value=False):
                with pytest.raises(SystemExit) as exc_info:
                    find_real_claude()
                assert exc_info.value.code == 1


# ─── create_panes_in_session (dry-run) ───────────────────────────────────────


class TestCreatePanesInSession:
    def _make_grid(self, n_sub_agents):
        main = Agent("Main Agent", "orchestrate")
        subs = [Agent(f"Agent {i+1}", f"role {i+1}") for i in range(n_sub_agents)]
        all_agents = [main] + subs
        rows, cols = calculate_grid(len(all_agents))
        grid = build_grid(all_agents, rows, cols)
        return grid, rows, cols

    def test_dry_run_1_agent(self, capsys):
        grid, rows, cols = self._make_grid(1)
        create_panes_in_session(grid, rows, cols, "/usr/bin/claude", dry_run=True)
        output = capsys.readouterr().out
        assert "[dry-run]" in output
        assert "rename-pane" in output
        assert "Agent 1" in output

    def test_dry_run_3_agents(self, capsys):
        grid, rows, cols = self._make_grid(3)
        create_panes_in_session(grid, rows, cols, "/usr/bin/claude", dry_run=True)
        output = capsys.readouterr().out
        # Should have commands for all 3 sub-agents
        for i in range(1, 4):
            assert f"Agent {i}" in output
        # Should have right and down directions
        assert "right" in output
        assert "down" in output

    def test_dry_run_renames_main_pane(self, capsys):
        grid, rows, cols = self._make_grid(1)
        create_panes_in_session(
            grid, rows, cols, "/usr/bin/claude",
            main_agent_name="My Main", dry_run=True,
        )
        output = capsys.readouterr().out
        assert "My Main" in output

    def test_dry_run_focus_returns_to_main(self, capsys):
        """After creating panes, focus should return to [0,0] via move-focus commands."""
        grid, rows, cols = self._make_grid(3)  # 2x2 grid
        create_panes_in_session(grid, rows, cols, "/usr/bin/claude", dry_run=True)
        output = capsys.readouterr().out
        # Should contain move-focus left to return to column 0
        assert "move-focus" in output
        assert "left" in output


# ─── main() — entry point ────────────────────────────────────────────────────


class TestMain:
    def test_rejects_without_zellij_env(self):
        """Script must exit with code 1 when $ZELLIJ is not set."""
        env = os.environ.copy()
        env.pop("ZELLIJ", None)
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", '[{"name":"A","role":"r"}]'],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode == 1
        assert "Not inside a Zellij session" in result.stderr

    def test_rejects_empty_agents(self):
        """Script must exit with code 1 when --agents is an empty array."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", "[]"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode == 1
        assert "at least one agent" in result.stderr

    def test_rejects_invalid_json(self):
        """Script must exit with code 1 for malformed JSON."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", "not json"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode == 1
        assert "Invalid JSON" in result.stderr

    def test_dry_run_succeeds_with_zellij_set(self):
        """Dry-run should succeed when ZELLIJ is set and agents are valid."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        agents = json.dumps([{"name": "Test Agent", "role": "testing"}])
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", agents, "--dry-run"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode == 0
        assert "Test Agent" in result.stdout
        assert "dry-run" in result.stdout

    def test_dry_run_multiple_agents(self):
        """Dry-run with multiple agents should show grid and all agent names."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        agents = json.dumps([
            {"name": "Alpha", "role": "first"},
            {"name": "Beta", "role": "second"},
            {"name": "Gamma", "role": "third"},
        ])
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", agents, "--dry-run"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode == 0
        assert "Alpha" in result.stdout
        assert "Beta" in result.stdout
        assert "Gamma" in result.stdout
        assert "2x2" in result.stdout  # 4 total panes (main + 3) = 2x2

    def test_agents_missing_name_field(self):
        """Script should fail if agent JSON is missing required fields."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        agents = json.dumps([{"role": "no name field"}])
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", agents, "--dry-run"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode != 0

    def test_agents_missing_role_field(self):
        """Script should fail if agent JSON is missing required fields."""
        env = os.environ.copy()
        env["ZELLIJ"] = "1"
        agents = json.dumps([{"name": "no role field"}])
        result = subprocess.run(
            [sys.executable, "-m", "create_panes", "--agents", agents, "--dry-run"],
            capture_output=True, text=True, env=env,
            cwd=os.path.join(os.path.dirname(__file__), "..", "scripts"),
        )
        assert result.returncode != 0


# ─── Integration-style grid tests ────────────────────────────────────────────


class TestGridIntegration:
    """End-to-end grid calculations matching the documented layout reference."""

    EXPECTED = {
        # (sub_agents, expected_rows, expected_cols)
        1: (1, 2),   # 2 total → 1×2
        2: (1, 3),   # 3 total → 1×3
        3: (2, 2),   # 4 total → 2×2
        5: (2, 3),   # 6 total → 2×3
        8: (3, 3),   # 9 total → 3×3
    }

    @pytest.mark.parametrize("n_sub,expected", EXPECTED.items())
    def test_documented_layouts(self, n_sub, expected):
        total = n_sub + 1  # +1 for main agent
        rows, cols = calculate_grid(total)
        assert (rows, cols) == expected, (
            f"{n_sub} sub-agents ({total} total): expected {expected}, got ({rows}, {cols})"
        )

    def test_main_agent_always_at_0_0(self):
        """Main agent should always be at grid position [0][0]."""
        for n in range(1, 10):
            main = Agent("Main", "main")
            subs = [Agent(f"S{i}", "sub") for i in range(n)]
            all_agents = [main] + subs
            rows, cols = calculate_grid(len(all_agents))
            grid = build_grid(all_agents, rows, cols)
            assert grid[0][0].name == "Main", f"Failed for {n} sub-agents"
