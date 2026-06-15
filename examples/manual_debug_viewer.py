"""Manual PyBoy runner with live LADX room tile/object and state windows.

This entry point intentionally uses PyBoy directly instead of the Gymnasium
wrapper so a human can play in the main emulator window while the side windows
show interpretable state.
"""

from __future__ import annotations

import argparse
import json
import queue
import time
import tkinter as tk
from multiprocessing import Event, Process, Queue
from pathlib import Path
from tkinter import scrolledtext
from typing import Any

from pyboy import PyBoy

from zelda_env.games.ladx.state_extractor import LadxStateExtractor
from zelda_env.games.ladx.symbols import SymbolTable, default_ladx_symbol_table


ROOM_COLS = 16
ROOM_ROWS = 8
VISIBLE_COLS = 10
CELL_SIZE = 32
DEFAULT_DEBUG_UPDATE_MS = 100
DEFAULT_STATE_UPDATE_MS = 100
QUEUE_POLL_MS = 16


class PyBoyMemoryAdapter:
    """Expose PyBoy memory through the small backend surface used by extractors."""

    platform = "gbc"
    buttons = ("UP", "DOWN", "LEFT", "RIGHT", "A", "B", "START", "SELECT")

    def __init__(self, pyboy: PyBoy) -> None:
        self.pyboy = pyboy

    def reset(self) -> None: ...

    def close(self) -> None: ...

    def press(self, buttons) -> None: ...

    def release_all(self) -> None: ...

    def advance(self, frames: int) -> None:
        for _ in range(frames):
            self.pyboy.tick()

    def read_u8(self, address: int) -> int:
        return int(self.pyboy.memory[address]) & 0xFF

    def read_u16(self, address: int, *, endian: str = "little") -> int:
        return int.from_bytes(self.read_bytes(address, 2), endian)

    def read_bytes(self, address: int, length: int) -> bytes:
        return bytes(self.read_u8(address + offset) for offset in range(length))

    def save_state(self) -> bytes:
        raise NotImplementedError

    def load_state(self, data: bytes) -> None:
        raise NotImplementedError

    def screen_rgb(self):
        return self.pyboy.screen.ndarray[:, :, :3].copy()


class TileMapWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("LADX room tile/object mapping")
        width = ROOM_COLS * CELL_SIZE
        height = ROOM_ROWS * CELL_SIZE
        self.canvas = tk.Canvas(self.window, width=width, height=height, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        self.text = scrolledtext.ScrolledText(self.window, width=76, height=10, font=("TkFixedFont", 10))
        self.text.pack(fill="both", expand=True)
        self._rects: list[int] = []
        self._labels: list[int] = []
        self._tiles: list[int | None] = [None] * (ROOM_COLS * ROOM_ROWS)
        self._last_summary_text = ""

        for row in range(ROOM_ROWS):
            for col in range(ROOM_COLS):
                x0 = col * CELL_SIZE
                y0 = row * CELL_SIZE
                outline = "#333333" if col < VISIBLE_COLS else "#aaaaaa"
                self._rects.append(
                    self.canvas.create_rectangle(
                        x0,
                        y0,
                        x0 + CELL_SIZE,
                        y0 + CELL_SIZE,
                        fill="#ffffff",
                        outline=outline,
                    )
                )
                self._labels.append(
                    self.canvas.create_text(
                        x0 + CELL_SIZE // 2,
                        y0 + CELL_SIZE // 2,
                        text="",
                        fill="#000000",
                        font=("TkFixedFont", 9),
                    )
                )

    def update(self, objects_runtime: list[int] | None, object_summary: list[dict[str, Any]] | None = None) -> None:
        if not objects_runtime:
            return
        for row in range(ROOM_ROWS):
            for col in range(ROOM_COLS):
                offset = row * ROOM_COLS + col
                tile = objects_runtime[offset] if offset < len(objects_runtime) else 0xFF
                if self._tiles[offset] == tile:
                    continue
                self._tiles[offset] = tile
                color = _tile_color(tile, col >= VISIBLE_COLS)
                self.canvas.itemconfigure(self._rects[offset], fill=_hex_color(color))
                self.canvas.itemconfigure(self._labels[offset], text=f"{tile:02X}", fill=_text_color(color))
        self._update_summary(object_summary or [])

    def _update_summary(self, object_summary: list[dict[str, Any]]) -> None:
        lines = ["Tile/Object types in current room:"]
        for entry in object_summary:
            lines.append(
                f"{entry.get('hex', '??')}: {entry.get('name', 'UNKNOWN')} "
                f"count={entry.get('count', 0)}"
            )
        text = "\n".join(lines)
        if text == self._last_summary_text:
            return
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self._last_summary_text = text


class SpriteMapWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("LADX sprite/entity mapping")
        width = ROOM_COLS * CELL_SIZE
        height = ROOM_ROWS * CELL_SIZE
        self.canvas = tk.Canvas(self.window, width=width, height=height, bg="white", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True)
        for row in range(ROOM_ROWS):
            for col in range(ROOM_COLS):
                x0 = col * CELL_SIZE
                y0 = row * CELL_SIZE
                fill = "#f8f8f8" if col < VISIBLE_COLS else "#e0e0e0"
                outline = "#333333" if col < VISIBLE_COLS else "#aaaaaa"
                self.canvas.create_rectangle(x0, y0, x0 + CELL_SIZE, y0 + CELL_SIZE, fill=fill, outline=outline)
        self.text = scrolledtext.ScrolledText(self.window, width=64, height=10, font=("TkFixedFont", 10))
        self.text.pack(fill="both", expand=True)
        self._last_text = ""

    def update(self, entities: list[dict[str, Any]], player: dict[str, Any]) -> None:
        active_entities = [entity for entity in entities if entity.get("enabled")]
        self.canvas.delete("overlay")

        labels_by_cell: dict[tuple[int, int], list[tuple[str, tuple[int, int, int]]]] = {}
        player_col = max(0, min(ROOM_COLS - 1, int(player.get("x") or 0) // 16))
        player_row = max(0, min(ROOM_ROWS - 1, int(player.get("y") or 0) // 16))
        labels_by_cell.setdefault((player_row, player_col), []).append(("LINK", (34, 139, 34)))

        for entity in active_entities:
            x = int(entity.get("x") or 0)
            y = int(entity.get("y") or 0)
            col = max(0, min(ROOM_COLS - 1, x // 16))
            row = max(0, min(ROOM_ROWS - 1, y // 16))
            entity_type = int(entity.get("type") or 0)
            label = f"{entity.get('slot', 0):X}:{entity_type:02X}"
            labels_by_cell.setdefault((row, col), []).append((label, _sprite_color(entity_type)))

        for (row, col), label_entries in labels_by_cell.items():
            x0 = col * CELL_SIZE
            y0 = row * CELL_SIZE
            text = "\n".join(label for label, _color in label_entries[:3])
            if len(label_entries) > 3:
                text += "\n+"
            fill = _hex_color(_blend_colors([color for _label, color in label_entries]))
            text_fill = _text_color(_blend_colors([color for _label, color in label_entries]))
            self.canvas.create_rectangle(
                x0 + 1,
                y0 + 1,
                x0 + CELL_SIZE - 1,
                y0 + CELL_SIZE - 1,
                fill=fill,
                outline="",
                tags=("overlay",),
            )
            self.canvas.create_text(
                x0 + CELL_SIZE // 2,
                y0 + CELL_SIZE // 2,
                text=text,
                fill=text_fill,
                font=("TkFixedFont", 8),
                tags=("overlay",),
            )

        lines = []
        for entity in active_entities:
            slot = int(entity.get("slot") or 0)
            entity_type = int(entity.get("type") or 0)
            name = entity.get("type_name") or "UNKNOWN"
            status = entity.get("status_name") or entity.get("status")
            lines.append(
                f"{slot:02X}: type={entity_type:02X} {name} "
                f"status={status} pos=({entity.get('x')},{entity.get('y')},{entity.get('z')})"
            )

        text = "\n".join(lines) if lines else "No active entities"
        if text != self._last_text:
            self.text.configure(state="normal")
            self.text.delete("1.0", "end")
            self.text.insert("1.0", text)
            self.text.configure(state="disabled")
            self._last_text = text


class StateWindow:
    def __init__(self, root: tk.Tk) -> None:
        self.window = tk.Toplevel(root)
        self.window.title("LADX semantic state")
        self.text = scrolledtext.ScrolledText(self.window, width=78, height=34, font=("TkFixedFont", 10))
        self.text.pack(fill="both", expand=True)
        self._last_text = ""

    def update(self, state: dict[str, Any]) -> None:
        compact = _compact_state(state)
        text = json.dumps(compact, indent=2, ensure_ascii=False)
        if text == self._last_text:
            return
        self.update_text(text)

    def update_text(self, text: str) -> None:
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", text)
        self.text.configure(state="disabled")
        self._last_text = text


class DebugViewerApp:
    def __init__(self, state_queue: Any, stop_event: Any, state_update_ms: int) -> None:
        self.state_queue = state_queue
        self.stop_event = stop_event
        self.state_update_ms = state_update_ms
        self.last_state_update = 0.0
        self.closed = False

        self.root = tk.Tk()
        self.root.withdraw()
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.tile_window = TileMapWindow(self.root)
        self.sprite_window = SpriteMapWindow(self.root)
        self.state_window = StateWindow(self.root)
        self.tile_window.window.protocol("WM_DELETE_WINDOW", self.close)
        self.sprite_window.window.protocol("WM_DELETE_WINDOW", self.close)
        self.state_window.window.protocol("WM_DELETE_WINDOW", self.close)

    def run(self) -> None:
        self.root.after(0, self._poll_queue)
        self.root.mainloop()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.stop_event.set()
        try:
            self.root.destroy()
        except tk.TclError:
            pass

    def _poll_queue(self) -> None:
        if self.closed:
            return
        if self.stop_event.is_set():
            self.close()
            return

        latest_state: dict[str, Any] | None = None
        while True:
            try:
                state = self.state_queue.get_nowait()
            except queue.Empty:
                break
            if state is None:
                self.close()
                return
            latest_state = state

        if latest_state is not None:
            self._update(latest_state)

        self.root.after(QUEUE_POLL_MS, self._poll_queue)

    def _update(self, state: dict[str, Any]) -> None:
        try:
            if "__error__" in state:
                self.state_window.update_text(f"Error while updating debug viewer:\n{state['__error__']}")
                return

            now = time.monotonic()
            map_state = state.get("map", {})
            room = map_state.get("room") or state.get("room", {})
            sprites = state.get("sprites", {})
            self.tile_window.update(room.get("objects_runtime"), map_state.get("object_summary"))
            self.sprite_window.update(
                sprites.get("active") or state.get("entities", []),
                sprites.get("player") or state.get("player", {}),
            )
            if self.state_update_ms > 0 and (now - self.last_state_update) * 1000 >= self.state_update_ms:
                self.state_window.update(state)
                self.last_state_update = now
        except tk.TclError:
            self.close()
        except Exception as exc:
            self.state_window.update_text(f"Error while updating debug viewer:\n{exc!r}")


def _run_debug_viewer(state_queue: Any, stop_event: Any, state_update_ms: int) -> None:
    app = DebugViewerApp(state_queue, stop_event, state_update_ms)
    app.run()


class ManualDebugApp:
    def __init__(self, args: argparse.Namespace) -> None:
        self.debug_update_ms = args.debug_update_ms
        self.state_update_ms = args.state_update_ms
        self.state_queue = Queue(maxsize=2)
        self.stop_event = Event()
        self.viewer_process = Process(
            target=_run_debug_viewer,
            args=(self.state_queue, self.stop_event, self.state_update_ms),
            daemon=True,
        )
        self.viewer_process.start()

        kwargs: dict[str, Any] = {"window": args.window}
        if args.sym_path:
            kwargs["symbols"] = args.sym_path
        self.pyboy = PyBoy(args.rom_path, **kwargs)
        self.pyboy.set_emulation_speed(args.speed)
        if args.initial_state_path:
            with Path(args.initial_state_path).open("rb") as fh:
                self.pyboy.load_state(fh)
        symbols = SymbolTable.from_sym_file(args.sym_path) if args.sym_path else default_ladx_symbol_table(args.repo_root)
        self.extractor = LadxStateExtractor(symbols, repo_root=args.repo_root)
        self.backend = PyBoyMemoryAdapter(self.pyboy)
        self.closed = False
        self.last_debug_update = 0.0

    def run(self) -> None:
        try:
            while not self.closed and not self.stop_event.is_set() and self.viewer_process.is_alive():
                running = self.pyboy.tick()
                now = time.monotonic()
                if (now - self.last_debug_update) * 1000 >= self.debug_update_ms:
                    try:
                        self._send_state(self.extractor.extract(self.backend))
                    except Exception as exc:
                        self._send_state({"__error__": repr(exc)})
                    self.last_debug_update = now
                if running is False:
                    break
        finally:
            self.close()

    def close(self) -> None:
        if self.closed:
            return
        self.closed = True
        self.stop_event.set()
        self._send_state(None)
        try:
            self.pyboy.stop()
        finally:
            self.viewer_process.join(timeout=1.0)
            if self.viewer_process.is_alive():
                self.viewer_process.terminate()
                self.viewer_process.join(timeout=1.0)

    def _send_state(self, state: dict[str, Any] | None) -> None:
        try:
            self.state_queue.put_nowait(state)
        except queue.Full:
            try:
                self.state_queue.get_nowait()
            except queue.Empty:
                pass
            try:
                self.state_queue.put_nowait(state)
            except queue.Full:
                pass


def _tile_color(tile: int, padding: bool) -> tuple[int, int, int]:
    if tile == 0xFF:
        return (230, 230, 230) if padding else (248, 248, 248)
    if padding:
        return (220, 220, 220)
    # Stable pseudo-palette keyed by tile/object type.
    return (
        50 + ((tile * 53) % 170),
        50 + ((tile * 97) % 170),
        50 + ((tile * 193) % 170),
    )


def _sprite_color(entity_type: int) -> tuple[int, int, int]:
    # Stable high-contrast pseudo-palette keyed by entity type.
    return (
        45 + ((entity_type * 71) % 170),
        45 + ((entity_type * 131) % 170),
        45 + ((entity_type * 197) % 170),
    )


def _blend_colors(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    if not colors:
        return (248, 248, 248)
    return (
        sum(color[0] for color in colors) // len(colors),
        sum(color[1] for color in colors) // len(colors),
        sum(color[2] for color in colors) // len(colors),
    )


def _hex_color(color: tuple[int, int, int]) -> str:
    return f"#{color[0]:02x}{color[1]:02x}{color[2]:02x}"


def _text_color(color: tuple[int, int, int]) -> str:
    luminance = (0.299 * color[0]) + (0.587 * color[1]) + (0.114 * color[2])
    return "#000000" if luminance > 150 else "#ffffff"


def _compact_state(state: dict[str, Any]) -> dict[str, Any]:
    sprites = state.get("sprites", {})
    player = sprites.get("player") or state.get("player", {})
    active_entities = sprites.get("active") or [entity for entity in state.get("entities", []) if entity.get("enabled")]
    entities = [
        {
            "slot": entity.get("slot"),
            "type": entity.get("type"),
            "type_name": entity.get("type_name"),
            "category": entity.get("category"),
            "status": entity.get("status"),
            "x": entity.get("x"),
            "y": entity.get("y"),
            "z": entity.get("z"),
            "health": entity.get("health"),
        }
        for entity in active_entities
    ]
    map_state = state.get("map", {})
    room = map_state.get("room") or state.get("room", {})
    return {
        "meta": state.get("meta", {}),
        "map": {
            "location": map_state.get("location") or state.get("world", {}),
            "object_summary": map_state.get("object_summary", []),
        },
        "sprites": {
            "player": player,
            "active": entities,
            "by_category": sprites.get("by_category", {}),
        },
        "progress": state.get("progress", {}),
        "effects": state.get("effects", {}),
        "room_grid": _room_grid(room.get("objects_runtime") or []),
    }


def _room_grid(objects_runtime: list[int]) -> list[list[str]]:
    rows: list[list[str]] = []
    for row in range(ROOM_ROWS):
        values = []
        for col in range(VISIBLE_COLS):
            offset = row * ROOM_COLS + col
            tile = objects_runtime[offset] if offset < len(objects_runtime) else 0xFF
            values.append(f"{tile:02X}")
        rows.append(values)
    return rows


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run LADX in PyBoy with live semantic debug windows.")
    parser.add_argument("--rom-path", default="azle.gbc")
    parser.add_argument("--sym-path", default="azle.sym")
    parser.add_argument("--initial-state-path")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--window", default="SDL2", help="PyBoy window backend, usually SDL2.")
    parser.add_argument("--speed", type=float, default=1.0, help="PyBoy emulation speed multiplier.")
    parser.add_argument(
        "--debug-update-ms",
        type=int,
        default=DEFAULT_DEBUG_UPDATE_MS,
        help="Refresh interval for the side debug windows.",
    )
    parser.add_argument(
        "--state-update-ms",
        type=int,
        default=DEFAULT_STATE_UPDATE_MS,
        help="Refresh interval for the semantic JSON window. Use 0 to disable JSON refresh.",
    )
    return parser.parse_args()


def main() -> int:
    app = ManualDebugApp(parse_args())
    app.run()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
