@AGENTS.md

# Claude-specific additions

## Skills (procedural, on-demand)

When the task matches, load the relevant skill BEFORE editing:

| Task | Skill |
|---|---|
| Add a new aspect ratio (e.g. Instagram portrait) | `.claude/skills/add-aspect-ratio/SKILL.md` |
| Add a new CLI flag to `clipgen.py` | `.claude/skills/add-cli-flag/SKILL.md` |
| Add a `GeneratedClip` field (Python + TS) | `.claude/skills/add-clip-field/SKILL.md` |
| Edit the Gemini prompt template | `.claude/skills/edit-prompt-template/SKILL.md` |
| Debug a speaker-tracking regression | `.claude/skills/debug-speaker-tracking/SKILL.md` |

Each skill is "one file, one job, one verb" — read it once, do the procedure, ship.

## PreToolUse: verify before destructive ops

- ALWAYS read `.claude/settings.local.json` on a new session — it lists the per-project allowlist.
- PREFER the `bash` tool with `workdir` over `cd … &&` chains.
- NEVER run `git push --force`, `git reset --hard`, `git clean -fd`, or `rm -rf` without the user typing the exact command in chat.

## Verification expectations

Claude Code's auto-memory system loads only the first ~200 lines of any markdown file. The root `AGENTS.md` is sized to fit (90 lines). If you find yourself writing a 400-line `AGENTS.md`, you are doing it wrong — move depth to a skill or subdirectory file.

## Recursive CLAUDE.md discovery

Claude Code walks **upward** from CWD and merges all `CLAUDE.md` and `AGENTS.md` files it finds. So when working in `frontend/`, you get:
- `frontend/AGENTS.md` (Next.js 16 specifics)
- `AGENTS.md` (root constitution)

Both apply. The closer one wins on conflicts. Don't duplicate rules across files; if a rule applies in both, keep it in the root and reference it from the subdirectory file.
