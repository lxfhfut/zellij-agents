---
name: zellij-agents
description: |
  Use this skill when the user wants to create, spawn, or set up a team of agents
  for parallel or delegated work. Also trigger when the user mentions multi-agent
  workflows, worker agents, specialist agents, or agent panes.
  REQUIRES: The user MUST be running inside a Zellij session ($ZELLIJ env var set).
  If the user is NOT in a Zellij session, do NOT proceed and do NOT fall back to
  inline agents — just tell them to start Zellij first, then run Claude Code inside it.
  TRIGGER on any of: "team of agents", "team of N agents", "create a team",
  "create agents", "create agent team", "spawn agents", "multi-agent", "delegate
  to agents", "parallel agents", "agent panes", "zellij agents", "/zellij-agents",
  "set up agents", "agents to work on", "agents with roles", "each agent",
  "clean up agents", "close agents", "dismiss agents", "tear down agents",
  "stop agents", "remove agents", "kill agents", "close panes".
---

# zellij-agents

Create a team of Claude agents, each in its own named Zellij terminal pane.

> **MANDATORY**: Before doing ANYTHING else, you MUST run the Zellij check command
> in Step 1 using the Bash tool. Do NOT respond with text, do NOT create agents,
> do NOT use the Agent tool — until you have confirmed the user is inside Zellij
> by running the bash command and reading its output.

## When to Use

**IMPORTANT**: This skill **only works when you are already running inside a Zellij session**.
The `ZELLIJ` environment variable must be set.

Trigger this skill when the user:
- Asks to create a team of agents (e.g. "create a team of 3 agents", "team of agents to work on X")
- Mentions agents with specific roles or specializations
- Wants to delegate subtasks to specialized agents or parallel workers
- Mentions multi-agent workflows, spawning Claude instances, or agent panes
- Asks to clean up, close, dismiss, or tear down agents or agent panes
- Uses `/zellij-agents` explicitly

If the user is NOT in a Zellij session, reject the skill invocation and STOP.
Do NOT fall back to using the Agent tool or inline agents as an alternative.
Simply tell the user to:
1. Open a terminal
2. Start a Zellij session: `zellij`
3. Open Claude Code or claude CLI inside Zellij
4. Then request the agent team again

## Workflow

**CRITICAL**: You MUST follow these steps in order. Do NOT skip steps. Do NOT
respond with text alone — you MUST use the Bash tool to execute Step 1 before
doing anything else. Never pretend agents were created without actually running
the commands below.

### Step 1: Check if in Zellij Session (MANDATORY — MUST RUN THIS COMMAND)

You MUST run this exact Bash command first — no exceptions:

```bash
test -n "$ZELLIJ" && echo "IN_ZELLIJ" || echo "NOT_IN_ZELLIJ"
```

**If the output is NOT_IN_ZELLIJ**: Reject the skill and STOP. Do NOT fall back
to inline agents (the Agent tool), do NOT spawn any agents, do NOT proceed with
any other steps, do NOT pretend agents were created. Simply display this message
and do nothing else:
> "This skill requires you to be inside a Zellij session. Please:
> 1. Open a terminal
> 2. Run: `zellij`
> 3. Start Claude Code or `claude` CLI inside the Zellij session
> 4. Then request the agent team again"

**If the output is IN_ZELLIJ**: Proceed to Step 2.

### Step 2: Understand the Goal

Infer from context what the user is trying to accomplish. If ambiguous, ask:
> "What are you working on? I'll suggest how to structure the agent team."

### Step 3: Propose Agent Team and Confirm

Based on the task context, propose named agents with concise role descriptions.

Example:

```
Proposed team (3 agents in Zellij panes):
• Backend Dev  — API design, database, business logic
• Frontend Dev — React components, UI/UX, styling
• QA Engineer  — test writing, review, quality checks

I'll create these as new panes in the current Zellij session. OK? [Y/n]
```

Keep role descriptions short (one line). Agent names become Zellij pane titles.
Once the user confirms, proceed directly to create panes — do NOT ask again.

### Step 4: Create Zellij Panes

Build the JSON agent list and call the script. Use the absolute path.

Panes are added to the current Zellij session:

```bash
SKILL_DIR="$HOME/.claude/skills/zellij-agents"

python3 "$SKILL_DIR/scripts/create_panes.py" \
  --agents '[
    {"name": "Backend Dev", "role": "Handle API design, database, and server logic"},
    {"name": "Frontend Dev", "role": "Build React components and UI"},
    {"name": "QA Engineer",  "role": "Write tests and review output"}
  ]'
```

**JSON schema**: `[{"name": "<pane title>", "role": "<one-sentence role description>"}, ...]`

Wait for the script output. On success it prints the layout grid and a confirmation line.

### Step 5: Summarize

After panes are created, summarize:
```
Created 3 agent panes:
• Backend Dev  — [0,1] API design, database, server logic
• Frontend Dev — [0,2] React components and UI
• QA Engineer  — [1,0] Test writing and review

You (Main Agent) are in the top-left pane. Coordinate by navigating to each agent's pane and sending instructions.
```

### Step 6: Cleanup (when requested)

When the user asks to clean up, dismiss, or tear down the agent team:

1. Ask: "Do you want me to close the agent panes?"
2. If yes, close **only the sub-agent panes** — NEVER close the main agent's pane (the current pane).
3. From the main agent pane, cycle through sub-agent panes and close each one:
   ```bash
   # Repeat once per sub-agent (N times for N sub-agents):
   zellij action focus-next-pane && sleep 0.2 && zellij action close-pane
   ```
   Each iteration: `focus-next-pane` moves away from the main pane to a sub-agent,
   then `close-pane` closes it and returns focus to an adjacent pane (main or another sub-agent).
   Repeat until all sub-agent panes are gone.
   **IMPORTANT**: Never run `close-pane` without first doing `focus-next-pane` — that would close the main agent's own pane.
4. After cleanup, confirm which panes were closed and that the main agent pane remains active.

## Layout Reference

The script automatically selects a landscape-biased grid (cols ≥ rows):

```
1 sub-agent  →  1×2:   [Main | Ag1]
2 sub-agents →  1×3:   [Main | Ag1 | Ag2]
3 sub-agents →  2×2:   [Main | Ag1]  ← 2×2 grid, main top-left
                        [Ag2  | Ag3]
4 sub-agents →  1×5 or 2×3 — depends on score (2×3 typical)
5 sub-agents →  2×3:   [Main | Ag1 | Ag2]
                        [Ag3  | Ag4 | Ag5]
8 sub-agents →  3×3:   [Main | Ag1 | Ag2]
                        [Ag3  | Ag4 | Ag5]
                        [Ag6  | Ag7 | Ag8]
```

Main agent is always top-left [0,0]. All panes are equal size.

## Notes

- Sub-agents start as fresh `claude` sessions with their role injected via `--append-system-prompt`
- Pane names match the agent's name — visible in Zellij's tab/pane bar
- The script requires Python 3; Zellij must already be running with the `ZELLIJ` env var set
- New panes are added to the current Zellij session and tab
- This skill will reject if the user is not running inside a Zellij session
