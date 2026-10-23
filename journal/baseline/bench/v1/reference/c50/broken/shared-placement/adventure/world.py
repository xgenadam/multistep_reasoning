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


@dataclass(frozen=True)
class Room:
    id: str
    name: str
    description: str
    exits: dict = field(default_factory=dict)
    items: tuple = ()


class World:
    def __init__(self, start: str, rooms: dict, items: dict):
        self.start = start
        self.rooms = rooms
        self.items = items
        self.placement = {rid: list(room.items) for rid, room in rooms.items()}

    @classmethod
    def from_dict(cls, data: dict) -> 'World':
        items = {}
        for item_id, spec in (data.get('items') or {}).items():
            try:
                items[item_id] = Item(item_id, spec['name'], spec['description'],
                                      bool(spec.get('portable', True)))
            except (KeyError, TypeError) as e:
                raise WorldError(f'item {item_id!r} is incomplete') from e
        raw_rooms = data.get('rooms') or {}
        rooms, placed = {}, set()
        for room_id, spec in raw_rooms.items():
            if not isinstance(spec, dict) or 'name' not in spec or 'description' not in spec:
                raise WorldError(f'room {room_id!r} needs a name and a description')
            exits = dict(spec.get('exits') or {})
            for direction, target in exits.items():
                if direction not in DIRECTIONS:
                    raise WorldError(f'room {room_id!r}: bad direction {direction!r}')
                if target not in raw_rooms:
                    raise WorldError(f'room {room_id!r}: exit to unknown room {target!r}')
            room_items = tuple(spec.get('items') or ())
            for item_id in room_items:
                if item_id not in items:
                    raise WorldError(f'room {room_id!r}: unknown item {item_id!r}')
                if item_id in placed:
                    raise WorldError(f'item {item_id!r} is listed more than once')
                placed.add(item_id)
            rooms[room_id] = Room(room_id, spec['name'], spec['description'], exits, room_items)
        start = data.get('start')
        if start not in rooms:
            raise WorldError(f'start {start!r} is not a room')
        return cls(start, rooms, items)
