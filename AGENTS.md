# Agent Notes

## Project Intent

This checkout is not being used to prepare upstream changes for the original
LADX disassembly project. It is a working base for a new Zelda RL/debug
environment built on top of the disassembly assets and symbols.

The repository and branch may contain local experiment files, emulator states,
screenshots, and other generated artifacts while this environment is being
developed.

## GitHub Workflow

- Do not open pull requests against `haldai/LADX-Disassembly` or any upstream
  LADX disassembly repository unless the user explicitly asks for a PR.
- When asked to sync work to GitHub, commit and push only the requested files.
- Treat emulator state files, RAM dumps, screenshots, ROM outputs, and other
  generated artifacts as local unless the user explicitly asks to include them.
- Prefer preserving a dirty working tree over cleaning or reverting unrelated
  files.
