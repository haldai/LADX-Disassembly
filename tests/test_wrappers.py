import json

from zelda_env.wrappers import InfoStateRecorder


class DummyEnv:
    def reset(self):
        return "obs", {"state": _state(), "reward_terms": {}, "events": {"action": None}}

    def step(self, action):
        return "obs", 1.0, False, False, {"state": _state(), "reward_terms": {"x": 1}, "events": {"action": action}}

    def close(self):
        pass


def test_info_state_recorder_compact_mode_uses_v2_state(tmp_path):
    path = tmp_path / "runs" / "trace.jsonl"
    env = InfoStateRecorder(DummyEnv(), path, state_mode="compact")

    env.reset()
    env.step(2)
    env.close()

    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(lines) == 2
    state = lines[0]["info"]["state"]
    assert state["map"]["location"]["room"] == 0x92
    assert state["sprites"]["player"]["type_name"] == "LINK"
    assert state["sprites"]["active"][0]["type_name"] == "ENTITY_OCTOROK"
    assert "raw" not in state


def _state():
    return {
        "meta": {"schema_version": 2},
        "map": {"location": {"room": 0x92}, "object_summary": [{"hex": "04", "count": 3}]},
        "sprites": {
            "player": {"type_name": "LINK", "x": 1, "y": 2},
            "active": [{"slot": 0, "type_name": "ENTITY_OCTOROK", "x": 8, "y": 9}],
            "by_category": {"enemy": ["slot_00"]},
        },
        "progress": {"rupees": 0},
        "effects": {"active_projectile_count": 0},
        "raw": {"entity_tables": {"type": [9]}},
    }
