"""World definition, loaded from a plain dict and never changed afterwards."""

from __future__ import annotations

from dataclasses import dataclass, field

DIRECTIONS = ('north', 'south', 'east', 'west', 'up', 'down')


class WorldError(ValueError):
    pass


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    description: str
    portable: bool = True
    treasure: int = 0


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    description: str
    exits: dict = field(default_factory=dict)
    items: tuple = ()
    locks: dict = field(default_factory=dict)


class World:
    def __init__(self, start: str, rooms: dict, items: dict):
        self.start = start
        self.rooms = rooms
        self.items = items

    @classmethod
    def from_dict(cls, data: dict) -> 'World':
        items = {}
        for item_id, spec in (data.get('items') or {}).items():
            try:
                treasure = spec.get('treasure', 0)
                items[item_id] = Item(item_id, spec['name'], spec['description'],
                                      bool(spec.get('portable', True)), treasure)
            except (KeyError, TypeError, AttributeError) as e:
                raise WorldError(f'item {item_id!r} is incomplete') from e
            if not isinstance(treasure, int) or isinstance(treasure, bool) or treasure < 0:
                raise WorldError(f'item {item_id!r}: treasure must be an int >= 0')
        raw_rooms = data.get('rooms') or {}
        rooms, placed = {}, set()
        for room_id, spec in raw_rooms.items():
            if not isinstance(spec, dict) or 'name' not in spec or 'description' not in spec:
                raise WorldError(f'room {room_id!r} needs a name and a description')
            exits, locks = {}, {}
            for direction, target in (spec.get('exits') or {}).items():
                if direction not in DIRECTIONS:
                    raise WorldError(f'room {room_id!r}: bad direction {direction!r}')
                if isinstance(target, dict):
                    if 'to' not in target or 'key' not in target:
                        raise WorldError(f'room {room_id!r}: a locked exit needs to and key')
                    if target['key'] not in items:
                        raise WorldError(f'room {room_id!r}: unknown key {target["key"]!r}')
                    locks[direction] = target['key']
                    target = target['to']
                if not isinstance(target, str) or target not in raw_rooms:
                    raise WorldError(f'room {room_id!r}: exit to unknown room {target!r}')
                exits[direction] = target
            room_items = tuple(spec.get('items') or ())
            for item_id in room_items:
                if item_id not in items:
                    raise WorldError(f'room {room_id!r}: unknown item {item_id!r}')
                if item_id in placed:
                    raise WorldError(f'item {item_id!r} is listed more than once')
                placed.add(item_id)
            rooms[room_id] = Room(room_id, spec['name'], spec['description'], exits, room_items,
                                 locks)
        start = data.get('start')
        if start not in rooms:
            raise WorldError(f'start {start!r} is not a room')
        return cls(start, rooms, items)
