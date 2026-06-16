"""Gymnasium wrappers for diagnostics and trajectory capture."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class InfoStateRecorder:
    """Record action, reward, and semantic state to JSONL.

    This wrapper intentionally does not alter observations. The agent still sees
    pixels only; the recorder persists `info["state"]` for offline analysis.
    """

    def __init__(self, env, output_path: str | Path, *, state_mode: str = "full") -> None:
        if state_mode not in {"full", "compact"}:
            raise ValueError("state_mode must be 'full' or 'compact'")
        self.env = env
        self.output_path = Path(output_path)
        self.output_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_mode = state_mode
        self._file = self.output_path.open("a", encoding="utf-8")

    def reset(self, *args, **kwargs):
        observation, info = self.env.reset(*args, **kwargs)
        self._write({"type": "reset", "info": info})
        return observation, info

    def step(self, action: int):
        observation, reward, terminated, truncated, info = self.env.step(action)
        self._write(
            {
                "type": "step",
                "action": int(action),
                "reward": float(reward),
                "terminated": bool(terminated),
                "truncated": bool(truncated),
                "info": info,
            }
        )
        return observation, reward, terminated, truncated, info

    def render(self):
        return self.env.render()

    def close(self) -> None:
        try:
            self._file.close()
        finally:
            self.env.close()

    def __getattr__(self, name: str) -> Any:
        return getattr(self.env, name)

    def _write(self, event: dict[str, Any]) -> None:
        event = self._format_event(event)
        self._file.write(json.dumps(event, ensure_ascii=True, separators=(",", ":")) + "\n")
        self._file.flush()

    def _format_event(self, event: dict[str, Any]) -> dict[str, Any]:
        if self.state_mode == "full":
            return event

        formatted = dict(event)
        info = formatted.get("info")
        if not isinstance(info, dict):
            return formatted
        formatted["info"] = dict(info)
        state = info.get("state")
        if isinstance(state, dict):
            formatted["info"]["state"] = compact_v2_state(state)
        return formatted


def compact_v2_state(state: dict[str, Any]) -> dict[str, Any]:
    """Return a smaller reward/debug-oriented state snapshot.

    The compact form keeps the v2 `map` and `sprites` shape but drops raw memory
    tables and disabled sprite slots, which keeps JSONL trajectories manageable.
    """

    sprites = state.get("sprites", {})
    player = sprites.get("player") or state.get("player", {})
    active = sprites.get("active") or [entity for entity in state.get("entities", []) if entity.get("enabled")]
    map_state = state.get("map", {})

    return {
        "meta": state.get("meta", {}),
        "map": {
            "location": map_state.get("location") or state.get("world", {}),
            "object_summary": map_state.get("object_summary", []),
        },
        "sprites": {
            "player": player,
            "active": [_compact_entity(entity) for entity in active],
            "by_category": sprites.get("by_category", {}),
        },
        "progress": state.get("progress", {}),
        "effects": state.get("effects", {}),
    }


def _compact_entity(entity: dict[str, Any]) -> dict[str, Any]:
    return {
        "slot": entity.get("slot"),
        "category": entity.get("category"),
        "type": entity.get("type"),
        "type_name": entity.get("type_name"),
        "status": entity.get("status"),
        "status_name": entity.get("status_name"),
        "x": entity.get("x"),
        "y": entity.get("y"),
        "z": entity.get("z"),
        "speed_x": entity.get("speed_x"),
        "speed_y": entity.get("speed_y"),
        "health": entity.get("health"),
    }
