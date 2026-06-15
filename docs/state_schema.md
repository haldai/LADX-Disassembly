# Zelda Environment State Schema

The agent observation is pixels only. Semantic state is returned through
`info["state"]` for reward functions, diagnostics, curriculum design, and
trajectory analysis.

## Top-Level Sections

- `meta`: game, platform, backend, frame, ROM version, schema version.
- `map`: current map/room location plus runtime room object/tile data.
- `sprites`: player and entity sprite state, grouped for reward functions.
- `progress`: long-term quest, dungeon, collection, and save-file progress.
- `effects`: short-term buffs, debuffs, timers, invincibility, charge states.
- `flags`: game-specific flags that are useful but not yet promoted to stable fields.
- `raw`: raw or near-raw memory values for debugging and schema evolution.

Compatibility aliases currently remain available as `world`, `player`,
`inventory`, `entities`, and `room`. New reward and curriculum code should use
`map` and `sprites`.

## Sprite Schema

`sprites.player` is Link represented as the player sprite. It includes position,
movement, health, magic/resources, and nested `inventory` so policies and reward
functions can read player-owned state from one place.

Runtime entity slots are exposed in two forms:

- `sprites.slots.slot_00` through `sprites.slots.slot_0F`: stable per-slot
  dictionaries, including disabled slots.
- `sprites.active`: active entity dictionaries for quick iteration.
- `sprites.by_category`: active slot IDs grouped by coarse category such as
  `enemy`, `projectile`, `item`, `npc`, and `object`.

The coarse `category` field is a reward-facing helper derived from known entity
constant names. Game-specific raw state remains available in `raw`.

## LADX Mapping

- `sprites.player.x`: `hLinkPositionX`
- `sprites.player.y`: `hLinkPositionY`
- `sprites.player.health.current`: `wHealth`
- `sprites.player.health.max`: `wMaxHearts`
- `sprites.player.magic.current`: `None`
- `sprites.player.resources.magic_powder`: `wMagicPowderCount`
- `sprites.player.inventory`: nested inventory/equipment/resources state
- `map.location.map_id`: `hMapId`
- `map.location.room`: `hMapRoom`
- `map.location.is_indoor`: `wIsIndoor`
- `inventory.items`: `wInventoryItems`
- `sprites.slots.slot_XX.type`: `wEntitiesTypeTable[slot]`
- `sprites.slots.slot_XX.type_name`: parsed from `src/constants/entities.asm`
- `sprites.slots.slot_XX.status`: `wEntitiesStatusTable[slot]`
- `sprites.slots.slot_XX.x`: `wEntitiesPosXTable[slot]`
- `sprites.slots.slot_XX.y`: `wEntitiesPosYTable[slot]`
- `effects.active_projectile_count`: `wActiveProjectileCount`
- `effects.latest_shot_arrow_entity_slot`: `wLatestShotArrowEntityIndex`
- `map.room.objects_runtime`: `wRoomObjects`
- `map.object_summary`: per-object ID counts with best-effort `OBJECT_*` names
- `raw.entity_tables`: raw snapshots of the per-slot LADX entity tables that
  are currently mapped by the extractor.

LADX projectiles such as arrows, moblin arrows, bombs, hookshot chain segments,
magic-rod fireballs, and enemy projectiles are represented as regular entity
slots in `wEntities*Table`. Reward code should therefore inspect
`sprites.active` / `sprites.by_category.projectile` plus the projectile counters
in `effects`, instead of expecting a separate projectile list.

## ALTTP Compatibility Target

ALTTP means *The Legend of Zelda: A Link to the Past* / Zelda 3. Future SNES
support should map its documented RAM addresses into the same public schema:

- `player.x`: `$7E0022`
- `player.y`: `$7E0020`
- `player.health.current`: `$7EF36D`
- `player.magic.current`: `$7EF36E`
- `entities[*].type`: `$0E20[slot]`
- `entities[*].status`: `$0DD0[slot]`
- `entities[*].x`: `$0D10/$0D30[slot]`
- `entities[*].y`: `$0D00/$0D20[slot]`

ALTTP-specific fields should start in `flags` or `raw` before being promoted to
stable reward-facing paths.
