import copy
import json

import pytest

from adventure import (Command, Game, Item, ParseError, Room, SaveError, World, WorldError,
                       parse)

DATA = {
    'start': 'hall',
    'rooms': {
        'hall': {'name': 'Great Hall', 'description': 'A draughty hall.',
                 'exits': {'north': 'library', 'down': 'cellar', 'east': 'garden'},
                 'items': ['lamp', 'statue']},
        'library': {'name': 'Library', 'description': 'Dusty shelves.',
                    'exits': {'south': 'hall'}, 'items': ['book']},
        'cellar': {'name': 'Cellar', 'description': 'Damp and dark.',
                   'exits': {'up': 'hall'}},
        'garden': {'name': 'Garden', 'description': 'Overgrown.'},
    },
    'items': {
        'lamp': {'name': 'Brass Lamp', 'description': 'A dented brass lamp.'},
        'statue': {'name': 'statue', 'description': 'Far too heavy.', 'portable': False},
        'book': {'name': 'red book', 'description': 'A book bound in red leather.'},
        'ghost': {'name': 'ghost', 'description': 'Not placed anywhere.'},
    },
}

HALL = ('Great Hall\nA draughty hall.\nExits: north, east, down.\n'
        'You see: Brass Lamp, statue.')


@pytest.fixture
def world():
    return World.from_dict(copy.deepcopy(DATA))


@pytest.fixture
def game(world):
    return Game(world)


# ---------------------------------------------------------------- world

def test_world_structure(world):
    assert world.start == 'hall'
    assert set(world.rooms) == {'hall', 'library', 'cellar', 'garden'}
    hall = world.rooms['hall']
    assert isinstance(hall, Room)
    assert hall.items == ('lamp', 'statue') and hall.exits['down'] == 'cellar'
    assert world.rooms['garden'].exits == {} and world.rooms['garden'].items == ()
    assert world.items['lamp'] == Item('lamp', 'Brass Lamp', 'A dented brass lamp.', True)
    assert world.items['statue'].portable is False


def bad(mutate):
    data = copy.deepcopy(DATA)
    mutate(data)
    with pytest.raises(WorldError) as exc:
        World.from_dict(data)
    assert isinstance(exc.value, ValueError)


@pytest.mark.parametrize('mutate', [
    lambda d: d.update(start='attic'),
    lambda d: d['rooms']['hall'].pop('description'),
    lambda d: d['rooms']['hall']['exits'].update(northeast='garden'),
    lambda d: d['rooms']['hall']['exits'].update(west='attic'),
    lambda d: d['rooms']['garden'].update(items=['book']),
])
def test_world_errors(mutate):
    bad(mutate)


# ---------------------------------------------------------------- parser

@pytest.mark.parametrize('line, expected', [
    ('  D ', Command('go', 'down')),
    ('go   U', Command('go', 'up')),
    ('take the Brass  Lamp', Command('take', 'brass lamp')),
    ('get a book', Command('take', 'book')),
    ('drop an the lamp', Command('drop', 'lamp')),
    ('look', Command('look', None)),
    ('look at the statue', Command('look', 'statue')),
    ('I', Command('inventory', None)),
])
def test_parse_commands(line, expected):
    assert parse(line) == expected


@pytest.mark.parametrize('line, message', [
    ('', 'Say something.'),
    ('Dance wildly', 'I don\'t know the word "dance".'),
    ('go', 'Go where?'),
    ('go to the Moon', '"to moon" is not a direction.'),
    ('take the', 'Take what?'),
    ('look at', 'Examine what?'),
    ('north quickly', "I don't understand that."),
])
def test_parse_errors(line, message):
    with pytest.raises(ParseError) as exc:
        parse(line)
    assert str(exc.value) == message
    assert isinstance(exc.value, ValueError)


# ---------------------------------------------------------------- game

def test_initial_look_and_state(game):
    assert game.do('look') == HALL
    assert (game.room, game.inventory, game.moves) == ('hall', [], 0)
    assert game.items_in('hall') == ['lamp', 'statue']


def test_go_moves_and_describes(game):
    assert game.do('n') == 'Library\nDusty shelves.\nExits: south.\nYou see: red book.'
    assert game.room == 'library' and game.moves == 1
    assert game.do('west') == "You can't go that way."
    assert game.moves == 1
    game.do('s')
    assert game.do('e') == 'Garden\nOvergrown.\nExits: none.'
    assert game.moves == 3


def test_take_by_id_or_name_and_messages(game):
    assert game.do('take brass lamp') == 'Taken: Brass Lamp.'
    assert game.inventory == ['lamp']
    assert game.items_in('hall') == ['statue']
    assert game.do('take lamp') == 'You already have the Brass Lamp.'
    assert game.do('take statue') == "You can't take the statue."
    assert game.do('take book') == 'You see no book here.'
    assert game.do('take ghost') == 'You see no ghost here.'


def test_drop_goes_to_end_of_room(game):
    game.do('take lamp')
    game.do('north')
    game.do('take book')
    assert game.inventory == ['lamp', 'book']
    game.do('s')
    assert game.do('drop lamp') == 'Dropped: Brass Lamp.'
    assert game.items_in('hall') == ['statue', 'lamp']
    assert game.do('look').endswith('You see: statue, Brass Lamp.')
    assert game.do('drop lamp') == "You aren't carrying that."
    assert game.do('drop sword') == "You aren't carrying that."


def test_inventory_text(game):
    assert game.do('i') == 'You are carrying nothing.'
    game.do('take lamp')
    game.do('n')
    game.do('get red book')
    assert game.do('inventory') == 'You are carrying: Brass Lamp, red book.'


def test_look_at_items(game):
    assert game.do('look at statue') == 'Far too heavy.'
    game.do('take lamp')
    game.do('north')
    assert game.do('x lamp') == 'A dented brass lamp.'
    assert game.do('examine red book') == 'A book bound in red leather.'
    assert game.do('look at statue') == 'You see no statue here.'


def test_do_returns_parse_errors(game):
    assert game.do('') == 'Say something.'
    assert game.do('xyzzy') == 'I don\'t know the word "xyzzy".'
    assert game.room == 'hall' and game.moves == 0


def test_games_are_independent(world):
    a, b = Game(world), Game(world)
    a.do('take lamp')
    assert b.items_in('hall') == ['lamp', 'statue']
    assert world.rooms['hall'].items == ('lamp', 'statue')
    assert Game(world).do('look') == HALL


def test_inventory_and_items_in_are_copies(game):
    game.inventory.append('book')
    game.items_in('hall').clear()
    assert game.inventory == [] and game.items_in('hall') == ['lamp', 'statue']


# ---------------------------------------------------------------- save / load

def test_save_format(game):
    game.do('take lamp')
    game.do('n')
    data = json.loads(game.save())
    assert data == {'version': 1, 'room': 'library', 'inventory': ['lamp'],
                    'items': {'hall': ['statue'], 'library': ['book'], 'cellar': [],
                              'garden': []},
                    'moves': 1}


def test_load_round_trip_continues_identically(world, game):
    for cmd in ['take lamp', 'n', 'take book', 's', 'drop book', 'd']:
        game.do(cmd)
    restored = Game.load(world, game.save())
    assert (restored.room, restored.inventory, restored.moves) == ('cellar', ['lamp'], 3)
    assert restored.items_in('hall') == ['statue', 'book']
    for cmd in ['up', 'take book', 'inventory', 'look']:
        assert restored.do(cmd) == game.do(cmd)


def test_load_missing_room_key_means_empty(world):
    text = json.dumps({'version': 1, 'room': 'garden', 'inventory': ['book'],
                       'items': {'hall': ['lamp']}, 'moves': 7})
    g = Game.load(world, text)
    assert g.items_in('hall') == ['lamp'] and g.items_in('library') == []
    assert g.moves == 7 and g.inventory == ['book']


def good_save():
    return {'version': 1, 'room': 'hall', 'inventory': [], 'items': {'hall': ['lamp']},
            'moves': 0}


@pytest.mark.parametrize('text', [
    'not json',
    json.dumps({**good_save(), 'version': 2}),
    json.dumps({k: v for k, v in good_save().items() if k != 'moves'}),
    json.dumps({**good_save(), 'room': 'attic'}),
    json.dumps({**good_save(), 'inventory': ['sword']}),
    json.dumps({**good_save(), 'inventory': ['lamp']}),
])
def test_load_errors(world, text):
    with pytest.raises(SaveError) as exc:
        Game.load(world, text)
    assert isinstance(exc.value, ValueError)
