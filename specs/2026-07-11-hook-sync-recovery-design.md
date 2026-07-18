# Rizagent hook sync recovery

## Goal

Recover the diverged `master`, publish the complete `vsum-cli` and `meta-skill` packages, and stop the Codex PostToolUse hook from accumulating local sync commits after a non-fast-forward push failure.

## Current evidence

- Local `master` is 27 commits ahead and 1 commit behind `origin/master`.
- Commit `aba7ae2` contains `.agents/scripts/vsum`, its regression test, and the generated clipping.
- `.agents/skills/vsum-cli/` is ignored by the explicit skill whitelist.
- `.agents/skills/meta-skill/` is already whitelisted and tracked.
- The hook log records repeated `non-fast-forward` failures after making local commits.

## One-time recovery

1. Preserve the current clipping change in a narrow commit.
2. Fetch `origin` and verify the observed remote divergence again.
3. Rebase local `master` onto `origin/master`.
4. Stop immediately on conflicts and report the exact paths; never select a side automatically.
5. Push only after the rebase, worktree, and history checks pass.

## Repository boundary

Add explicit `.gitignore` exceptions for `.agents/skills/vsum-cli/` and its contents. Keep the existing explicit exceptions for `.agents/skills/meta-skill/`. Verification must prove both skill packages are tracked and visible in the pushed `origin/master` tree.

## Hook behavior

Before a threshold-triggered commit or pending-commit push, fetch `origin` and calculate ahead/behind against the branch upstream.

- `behind == 0`: continue with the existing narrow stage, commit, and push flow.
- `behind > 0`: do not stage, commit, rebase, merge, or push. Write the counts to `rizagent-git-sync.log`, return a visible `systemMessage`, and exit nonzero.
- fetch or push failure: preserve local state, log the full Git error, and exit nonzero.

The hook must never auto-rebase because PostToolUse is not a safe place to rewrite local history or resolve conflicts.

## Verification

- Deterministic tests cover clean, ahead-only, behind-only, and diverged states.
- A hook dry-run reports branch and divergence without mutation.
- `git status`, `git branch -vv`, and `git log origin/master..HEAD` confirm the recovered state.
- `git ls-tree origin/master` contains `.agents/scripts/vsum`, `.agents/skills/vsum-cli/SKILL.md`, and `.agents/skills/meta-skill/SKILL.md`.
- The latest hook log entry shows either a successful push or a deliberate behind-state stop, never a silent failure.
