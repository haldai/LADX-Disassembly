# Work Log

## 2026-06-15

- Built out the LADX-based `zelda_env` work on branch `codex-add-zelda-env`; latest pushed commits are `552c30fa` and `2c5cd5a6`.
- Improved `examples/manual_debug_viewer.py`: PyBoy runs in the main process, Tk debug windows render in a separate process, stale debug frames are dropped, and tile/object summaries are shown under the tile map.
- Updated semantic state extraction to schema v2: primary reward-facing paths are now `state["map"]` and `state["sprites"]`; old `world/player/inventory/entities/room` paths remain as compatibility aliases.
- Added best-effort `OBJECT_*` name parsing, sprite categories, compact state recording via `InfoStateRecorder(state_mode="compact")`, and tests for the wrapper.
- Moved reusable save states into `save_states/`, deleted tracked screenshots, and ignored future `screenshots/*.png`.
- Added `AGENTS.md`: this repo is a working base for a new Zelda RL/debug environment, not upstream LADX work; do not create PRs unless explicitly requested.
- Updated docs: `docs/state_schema.md`, `docs/zelda_env_readme.md`, and `docs/ai_agent_env_plan.md` now reflect schema v2, save state layout, and completed/backlog phases.

Next likely work:

- Register Gymnasium ID `Zelda-LADX-v0`.
- Add real ROM/save-state smoke tests guarded by marker or environment variable.
- Add `games/ladx/static_data.py` for cached static room objects and initial entities.
- Move default reward logic from compatibility aliases to v2 `map`/`sprites` paths.
- Add a small trajectory-recording CLI around `InfoStateRecorder(state_mode="compact")`.
