# zellij-agents

A Claude Code skill that creates multi-agent teams in [Zellij](https://zellij.dev/) terminal panes. Each agent gets its own named pane with a role-injected system prompt, laid out in a landscape-biased grid.

```
+-------------+-------------+-------------+
| Main Agent  | Backend Dev | Frontend Dev|
|  (you)      |             |             |
+-------------+-------------+-------------+
| QA Engineer | DevOps Eng  | Tech Writer |
|             |             |             |
+-------------+-------------+-------------+
          5 sub-agents -> 2x3 grid
```

## Prerequisites

- [Claude Code](https://claude.ai/code) CLI installed and working
- [Zellij](https://zellij.dev/) terminal multiplexer
- Python 3.6+ (stdlib only — no pip installs needed)

### Installing Zellij

**macOS** (Homebrew):
```bash
brew install zellij
```

**Linux** (package manager):
```bash
# Arch
pacman -S zellij

# Nix
nix-env -i zellij

# Cargo (any platform)
cargo install --locked zellij
```

**Pre-built binary**:
```bash
# Download the latest release for your platform from:
# https://github.com/zellij-org/zellij/releases
```

Verify installation:
```bash
zellij --version
```

## Installation

Clone the skill into Claude Code's skills directory:

```bash
git clone https://github.com/lxfhfut/zellij-agents ~/.claude/skills/zellij-agents
```

Claude Code auto-discovers skills in `~/.claude/skills/`.

## Usage

**Important**: You must be running Claude Code **inside a Zellij session**. The skill will not work outside of Zellij and will not fall back to inline agents.

### Quick start

1. Open a terminal and start Zellij:
   ```bash
   zellij
   ```
2. Launch Claude Code inside the Zellij session:
   ```bash
   claude
   ```
3. Ask for an agent team:
   > "Create a team of 3 agents for building a web app"

### Automatic trigger

Describe what you're building. Claude will detect agent-team scenarios and offer to set one up:

> "I need to build a full-stack app — can you set up agents for this?"

> "Let's parallelize this work with a few specialist agents."

### Slash command

```
/zellij-agents
```

### What happens

1. Claude checks that you're inside a Zellij session (`$ZELLIJ` env var)
2. Claude proposes a named team based on your task context
3. You confirm or adjust the agents and their roles
4. `create_panes.py` creates new panes in the current Zellij session
5. Each sub-agent starts a fresh `claude` session with its role injected

## Layout Examples

| Sub-agents | Grid | Layout                          |
|-----------|------|---------------------------------|
| 1         | 1x2  | `[Main \| Ag1]`                |
| 2         | 1x3  | `[Main \| Ag1 \| Ag2]`        |
| 3         | 2x2  | 2x2 grid, main top-left        |
| 5         | 2x3  | 2 rows x 3 cols, 1 empty slot  |
| 6         | 2x3  | Full 2x3 grid                  |
| 8         | 3x3  | Full 3x3 grid                  |

- Main agent always at **top-left [0,0]**
- All panes are **equal size**
- Grid favours **more columns than rows** (landscape terminal aspect ratio)

## How Agents Are Prompted

Each sub-agent pane starts a fresh `claude` session with:

```
--append-system-prompt "You are <Name>. <Role>. You are part of a coordinated
multi-agent team. The main agent (top-left pane) will coordinate your work."
```

Pane titles in Zellij match the agent name so you can identify them at a glance.

## Direct Script Usage

The script must be run from inside a Zellij session (`$ZELLIJ` must be set):

```bash
# Create agents in the current Zellij session:
python3 ~/.claude/skills/zellij-agents/scripts/create_panes.py \
  --agents '[
    {"name": "Backend Dev",  "role": "Handle API design and server logic"},
    {"name": "Frontend Dev", "role": "Build React components and UI"},
    {"name": "QA Engineer",  "role": "Write tests and review output"}
  ]'

# Preview without executing:
python3 ~/.claude/skills/zellij-agents/scripts/create_panes.py \
  --agents '[...]' --dry-run
```

## Cleanup

Ask Claude to clean up the agent team:

> "Close the agent panes"
> "Dismiss the agents"

This closes only the sub-agent panes and keeps your main agent pane active.

## Running Tests

```bash
cd ~/.claude/skills/zellij-agents
python3 -m pytest tests/ -v
```

## Project Structure

| File | Purpose |
|------|---------|
| `SKILL.md` | Skill instructions loaded by Claude Code |
| `scripts/create_panes.py` | Grid algorithm + Zellij pane creation |
| `tests/test_create_panes.py` | Unit and integration tests |

## License

Apache 2.0 — see [LICENSE.txt](LICENSE.txt).
