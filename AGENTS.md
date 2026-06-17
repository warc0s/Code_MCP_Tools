# Repository Guidelines

## Workflow

- Before applying any change, review the related context and affected flows to detect regressions.

## Engineering Principles

- **Work doggedly.** Stay autonomous while progress is possible; if you stop, explain why.
- **Work smart.** When debugging, step back, consider root causes, and add logging to validate assumptions.
- **Check your work.** Test every new block and, in long-running processes, review logs after 30s to confirm progress.
- **Be cautious with terminal commands.** Only launch commands that terminate by themselves; persistent commands must use `nohup` or another wrapper, and avoid hanging scripts.
- **Total robustness.** Every solution must explicitly account for edge cases and operational failures; prioritize clear, defensive messages for dependencies, network, or unexpected inputs.
- **Avoid patches.** Do not disable referential integrity or other engine guarantees as a quick fix. Prefer schema invariants and explicit schema changes.
- **Development without data attachment.** At this stage, compatibility with old DBs is not maintained. If a schema change requires it, recreate the DB and index; assume there is no relevant data to preserve.
- **Clear migrations.** When appropriate, add idempotent migrations; while in development, prefer simplicity: recreate artifacts before adding toggles or fragile workarounds.

## Validation And Tests

- For every new feature, add a test in `test/` that covers it and run it with `pytest`.
- Iterate until functional: if tests or UI checks fail, fix and repeat the cycle (code -> pytest) until stable.
- Minimum expected coverage: include at least one happy path test and one relevant edge case.

## Operational Memory (Items)

- `memory`: design decisions, invariants, hard conventions (naming, patterns that must not be broken), architectural rationale, brief mental maps, and detected antipatterns. Use it for shortcuts the agent should remember before touching code.
- `doc`: manuals or long flows (architecture, APIs, protocols, deployment steps), reproducible examples, command lists; edit with `patch_doc` (diffs) to keep history clean.
- `bug`: reproducible incidents or suspected P0s; document environment, exact steps, and expected/observed behavior; add meta with:
  - `severity` (`high|medium|low`), `reproduction` (exact steps), `expected`, `root_cause`
  - optional: `logs_excerpt`, `fix_summary`, `fixed_in_commit`, `resolution_criteria` (list), `related_files` (list)
- `todo`: actionable tasks; meta with `kind` (`bug_fix|refactor|feature|chore`), `acceptance_criteria` (list), `dependencies` (list), `priority` (`p0|p1|p2`). Split it if the task grows.
  - optional: `related_files` (list of paths/URLs)

## Coding Style And Naming Conventions

- Use 4-space indentation, snake_case, and uppercase constants; keep logs concise.
- Add typing and targeted docstrings; extract helpers before nesting logic.
- Configure through YAML or environment; avoid hardcoded secrets.

## Commit And Pull Request Guidelines

- Use Conventional Commits in English, present imperative, and no final punctuation when possible (for example `fix: harden project deletion guard`, `test: cover rebuild progress updates`).
- Group cohesive changes per commit, including required configs or artifacts.
- PRs describe problem, solution, tests, and risks (env vars, index rebuild) and involve the RAG owner when applicable.
- If remote connectivity is missing, do not rewrite or amend local commits: stop and notify the user before attempting pulls or pushes.

## Final Rules And Reminders

- Always respond in Spanish.
- You are in a conda environment, so you should be able to run the application without issues. If you add a new import required by the app, you may install it, but remember to add it to `requirements.txt`. If too many packages are missing, the user may have forgotten to activate the conda environment before calling you; ask in that case.
- Create or edit the current guides (`Extra/Guias/...`), or create new ones if the topic is too different, for every implemented change worth documenting.
- Before starting any task, collect all available repository information: review and read **all** guides in `Extra/Guias/`, inspect relevant files, and confirm the current state before proposing or executing changes.
- Always iterate through reproducible tests and do not stop until the task is fully functional. If unsure or blocked, ask the user.
- Every implementation must include a new test in `test/` and is not ready until tests are green (run `pytest`).
- Once the user-requested task is complete and verified stable/valid, ask the user whether to run `git add .` and commit with a clear summary of what was added. Never push; the user does that. Always wait for approval.
- Do not run git commands (`add`, `commit`, `reset`, `revert`, etc.) unless the user explicitly asks.
- When adding new functions in `utils`, implement them in the most appropriate existing `.py` file or create a new one if none fits.
- Never identify yourself as responsible or mention agent names (for example, Codex); focus on actions and results.
- The application runs from `app.py`, and imports live in `utils`. Respect this.
- Try to keep files under two thousand lines of code.
- Visible UI text and code comments must be in English. Guide documents should also be kept in English for this repository.

## External Expert Agent (Internet Access)

- The user has an external agent with internet access that you can request at any time. Use it when expert analysis can save time or avoid outdated decisions. Write a clear prompt, share it with the user to send, and wait for the response before applying changes.

- When to request it
  - Architecture and design decisions (patterns, boundaries, API contracts).
  - Serious comparisons of solutions/libraries/MCP servers and their trade-offs.
  - Security (policies, whitelists/flags, resource limits, audits).
  - Cross-platform concerns (WSL, macOS, Windows/ConPTY), TTY, signals, performance/robustness.
  - Dependency choices and roadmaps (avoid obsolete architectures from the start).

- How to use it
  - Write a clear prompt with context and constraints and give it to the user to send to this agent; wait for its response before changing code.
  - Ask for actionable deliverables: executive summary, comparison, step-by-step plan, and recommendations.
  - Do not hesitate to request it if it can save hours of research and avoid overengineering.

- Best practices
  - Clearly define context, goals, constraints, and success criteria.
  - Request risks, alternatives, and “do not do” guidance with justification.
  - Document decisions and next steps briefly and actionably.
  - Use it for impactful doubts; avoid mechanical consultations.
- Robust solutions, not patches: do not accept disabling FKs to operate; if cleanup is required, update the schema, recreate the DB if necessary, and validate with tests.
- Do not run `python app.py` or start the application yourself: assume the user has it running.
