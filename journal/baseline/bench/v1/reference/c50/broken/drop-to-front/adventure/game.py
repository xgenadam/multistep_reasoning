"""Game state, command handling, and JSON save/load."""

from __future__ import annotations

import json

from .parser import ParseError, parse
from .world import DIRECTIONS, World

SAVE_VERSION = 1


class SaveError(ValueError):
    pass


class Game:
    def __init__(self, world: World):
        self.world = world
        self._room = world.start
        self._inventory: list[str] = []
        self._items = {rid: list(room.items) for rid, room in world.rooms.items()}
        self._moves = 0

    # ------------------------------------------------------------ state

    @property
    def room(self) -> str:
        return self._room

    @property
    def inventory(self) -> list[str]:
        return list(self._inventory)

    @property
    def moves(self) -> int:
        return self._moves

    def items_in(self, room_id: str) -> list[str]:
        return list(self._items[room_id])

    def _name(self, item_id: str) -> str:
        return self.world.items[item_id].name

    def _match(self, ids, arg: str) -> str | None:
        for item_id in ids:
            if arg == item_id or arg == self._name(item_id).lower():
                return item_id
        return None

    # ------------------------------------------------------------ commands

    def describe(self) -> str:
        room = self.world.rooms[self._room]
        exits = [d for d in DIRECTIONS if d in room.exits]
        lines = [room.name, room.description,
                 f'Exits: {", ".join(exits)}.' if exits else 'Exits: none.']
        here = self._items[self._room]
        if here:
            lines.append(f'You see: {", ".join(self._name(i) for i in here)}.')
        return '\n'.join(lines)

    def do(self, line: str) -> str:
        try:
            cmd = parse(line)
        except ParseError as e:
            return str(e)
        return getattr(self, f'_do_{cmd.verb}')(cmd.arg)

    def _do_look(self, arg):
        if arg is None:
            return self.describe()
        item = self._match(self._items[self._room], arg) or self._match(self._inventory, arg)
        if item is None:
            return f'You see no {arg} here.'
        return self.world.items[item].description

    def _do_go(self, direction):
        room = self.world.rooms[self._room]
        if direction not in room.exits:
            return "You can't go that way."
        self._room = room.exits[direction]
        self._moves += 1
        return self.describe()

    def _do_take(self, arg):
        here = self._items[self._room]
        item = self._match(here, arg)
        if item is not None:
            if not self.world.items[item].portable:
                return f"You can't take the {self._name(item)}."
            here.remove(item)
            self._inventory.append(item)
            return f'Taken: {self._name(item)}.'
        held = self._match(self._inventory, arg)
        if held is not None:
            return f'You already have the {self._name(held)}.'
        return f'You see no {arg} here.'

    def _do_drop(self, arg):
        item = self._match(self._inventory, arg)
        if item is None:
            return "You aren't carrying that."
        self._inventory.remove(item)
        self._items[self._room].insert(0, item)
        return f'Dropped: {self._name(item)}.'

    def _do_inventory(self, _arg):
        if not self._inventory:
            return 'You are carrying nothing.'
        return f'You are carrying: {", ".join(self._name(i) for i in self._inventory)}.'

    # ------------------------------------------------------------ save / load

    def save(self) -> str:
        return json.dumps({'version': SAVE_VERSION, 'room': self._room,
                           'inventory': list(self._inventory),
                           'items': {rid: list(ids) for rid, ids in self._items.items()},
                           'moves': self._moves})

    @classmethod
    def load(cls, world: World, text: str) -> 'Game':
        try:
            data = json.loads(text)
        except (TypeError, ValueError) as e:
            raise SaveError('not a JSON save') from e
        if not isinstance(data, dict):
            raise SaveError('a save must be a JSON object')
        for key in ('version', 'room', 'inventory', 'items', 'moves'):
            if key not in data:
                raise SaveError(f'missing {key!r}')
        if data['version'] != SAVE_VERSION:
            raise SaveError(f'unsupported save version {data["version"]!r}')
        game = cls(world)
        game._room, game._inventory, game._items, game._moves = _check_state(world, data)
        return game


def _check_state(world: World, data: dict):
    room = data['room']
    if not isinstance(room, str) or room not in world.rooms:
        raise SaveError(f'unknown room {room!r}')
    if not isinstance(data['inventory'], list) or not isinstance(data['items'], dict):
        raise SaveError('inventory must be a list and items an object')
    seen: set[str] = set()

    def check_ids(ids):
        if not isinstance(ids, list):
            raise SaveError('item lists must be lists')
        for item_id in ids:
            if not isinstance(item_id, str) or item_id not in world.items:
                raise SaveError(f'unknown item {item_id!r}')
            if item_id in seen:
                raise SaveError(f'item {item_id!r} appears more than once')
            seen.add(item_id)
        return list(ids)

    inventory = check_ids(data['inventory'])
    items = {rid: [] for rid in world.rooms}
    for rid, ids in data['items'].items():
        if rid not in world.rooms:
            raise SaveError(f'unknown room {rid!r}')
        items[rid] = check_ids(ids)
    moves = data['moves']
    if not isinstance(moves, int) or isinstance(moves, bool) or moves < 0:
        raise SaveError('moves must be a non-negative integer')
    return room, inventory, items, moves
