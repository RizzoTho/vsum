# Project contract

- This repository root is the installable vsum skill. `SKILL.md` is the agent entrypoint; `scripts/vsum.py` is the single runtime implementation; `references/READABLE.md` owns the article-writing contract.
- Invoke the script by absolute path from the calling task workspace. Resolve bundled resources relative to the script, and relative output paths from the task workspace. Do not depend on a globally installed `vsum` command.
- Persistent preferences belong to the skill installation's `.env`. Precedence is run arguments > process environment > installation `.env` > defaults. Never source configuration as shell code or read an unrelated workspace `.env`.
- `init` writes preferences without overwriting existing configuration. `doctor` reports local dependency and configuration readiness; neither command downloads media or installs dependencies.
- Preserve the distinction between materials ready, article finalized, remote delivery, and Git commit. The agent writes articles; the script acquires materials and validates submitted files.
- README files introduce current usage to new users. Migration history belongs in the English-only `CHANGELOG.md`. Keep documentation aligned with behavior.
- Create a branch before substantial restructuring. Fail visibly and retain diagnostic context rather than swallowing errors.
- Run the offline pytest suite for runtime changes. Verify installation relocation and calling-workspace output behavior when changing package layout or configuration. Live platform tests are separate and must be reported separately.
