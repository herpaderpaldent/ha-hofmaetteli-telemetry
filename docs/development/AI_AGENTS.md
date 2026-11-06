# Working with AI coding agents

This repository is set up for [Claude Code](https://docs.claude.com/en/docs/claude-code/overview). Its instructions
live in `AGENTS.md`, which `CLAUDE.md` imports; what follows is the workflow around it and where its configuration is
kept.

## Human Review and Transparency

An agent prepares a draft; that does not establish that the integration is understood, tested, or ready to
publish. Before merging, review the diff and accurately record which checks, automated tests, and real-device tests were
performed. If review is partial or some behavior could not be tested, document that limitation instead of implying full
verification.

Extensive AI assistance is acceptable for a community custom integration. See [`AI_POLICY.md`](../../AI_POLICY.md) for
the project's approach to AI use, transparency, and informed user choice. Do not use this workflow for autonomous
contributions to an Open Home Foundation repository, where the official OHF AI Policy applies.

## Reviewing an agent's changes

When Claude Code hands you a branch or a draft pull request:

1. **Open the branch** in the dev container, locally or in Codespaces (see [CODESPACES.md](CODESPACES.md)).
2. **Start Home Assistant** with `./script/develop`; port 8123 is forwarded.
3. **Test the integration**
   - Run the relevant automated tests with `script/test`
   - Add the integration through the Home Assistant UI and check that the entities appear correctly
   - Test with the real telemetry server and a second Home Assistant where it matters
   - Check the logs: `config/home-assistant.log` or live in the terminal
4. **Iterate** by asking Claude for changes, or adjust and commit to the branch yourself.

Review every iteration before merging, keep the pull request's verification notes accurate, and split large changes
into several pull requests.

## Configuration

| What                    | Where                                                                                                                             |
| ----------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| Project permissions     | [`.claude/settings.json`](../../.claude/settings.json)                                                                            |
| Dev container policy    | [`.devcontainer/claude-code/managed-settings.json`](../../.devcontainer/claude-code/managed-settings.json), installed into `/etc` |
| Lifecycle hooks         | [`.agents/hooks/`](../../.agents/hooks/), registered in `.claude/settings.json`                                                   |
| Skills                  | [`.agents/skills/`](../../.agents/skills/README.md), reached through the `.claude/skills/` symlink                                |
| Path-scoped style rules | [`.agents/instructions/`](../../.agents/instructions/), reached through the `.claude/rules/instructions` symlink                  |
| Slash commands          | [`.claude/commands/`](../../.claude/commands/)                                                                                    |
| Home Assistant preview  | [`.claude/launch.json`](../../.claude/launch.json)                                                                                |

Protected paths — files an agent may not edit, such as its own settings, the hooks and the workflows — are listed in
the managed settings, the project `.claude/settings.json` and both copies of VS Code's `chat.tools.edits.autoApprove`.
The managed settings apply only inside the dev container; the project settings carry the same protection to a local or
cloud session. `script/skills-check` fails when the lists disagree.

These agent lifecycle hooks are unrelated to `script/hooks/`, which customizes the repository's validation scripts.

### Session start

Claude Code runs [`session-start.sh`](../../.agents/hooks/session-start.sh) when a session begins, so a checkout works
without the dev container. Nothing slow happens in front of the session: in a Claude Code cloud session, which starts
on a fresh machine each time, it runs `script/setup/bootstrap` in the background, which installs mise from its GitHub
release (checksum-verified); everywhere else it checks the tools [`mise.toml`](../../mise.toml) pins in the background
and reports a checkout that still needs `script/setup/bootstrap`. Both scripts record their state, with the PID, in
`.local/<script>.status`, so a run in progress is waited for and a dead one is not mistaken for it. Every later command
of the session applies `mise env` — the pinned tools and the Home Assistant venv.

### Previewing Home Assistant

[`.claude/launch.json`](../../.claude/launch.json) tells the Claude desktop app how to start Home Assistant
(`script/develop`, port 8123) for its browser pane, so Claude can look at the UI it is changing. A Claude Code cloud
session has no such preview; there, `script/ha` is how an agent inspects the running instance.

### Push gate

Every push, by a person or an agent, goes through [`script/push-gate`](../../script/push-gate), which prek installs
as git's pre-push hook. It accepts only the checked-out HEAD of a clean worktree and runs `script/lint-check` and
`script/type-check` on it. Git hands the hook only the first ref of a push, so the shared agent hook adds what the
gate cannot see. It reads the git commands a shell call actually runs, including those inside `bash -c`, `$(…)` and
subshells, and blocks `--no-verify` and `core.hooksPath`, pushes of several refs, tags or deletions, and pushes from a
repository whose `.pre-commit-config.yaml` does not install the hook. Commit messages, here-documents and searches
that merely mention such a push pass. A person who needs any of that pushes with `--no-verify` deliberately.
`script/setup/bootstrap` runs `prek install`, so the hook exists in every bootstrapped clone.

### Work reaches `main` through a pull request

The `main` ruleset takes every change through a pull request, squash-merged by default — what it requires and how to
relax it is in [REPOSITORY_SETUP.md](REPOSITORY_SETUP.md). That suits agent work: a branch's working commits never
reach `main`, each change can be reverted as a whole, and release-please reads exactly one commit per change. Open a
pull request as a draft while an agent still pushes to it; [`ha-issue-triage`](../../.agents/skills/ha-issue-triage/SKILL.md)
(the `/issues` command) walks a backlog the same way, one branch and pull request per issue.

## Resources

- [Claude Code settings](https://docs.claude.com/en/docs/claude-code/settings)
- [Claude Code hooks](https://docs.claude.com/en/docs/claude-code/hooks)
- [Agent Skills](https://docs.claude.com/en/docs/claude-code/skills)
