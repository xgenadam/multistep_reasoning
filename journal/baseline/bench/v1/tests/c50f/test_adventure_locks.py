import copy
import json

import pytest

from adventure import Command, Game, ParseError, SaveError, World, WorldError, parse

DATA = {
    'start': 'hall',
    'rooms': {
        'hall': {'name': 'Hall', 'description': 'Echoing.',
                 'exits': {'north': {'to': 'vault', 'key': 'key'},
                           'up': {'to': 'attic', 'key': 'key'},
                           'east': 'study', 'down': {'to': 'crypt', 'key': 'bone'}},
                 'items': ['key']},
        'study': {'name': 'Study', 'description': 'Books.', 'exits': {'west': 'hall'},
                  'items': ['bone', 'gem']},
        'vault': {'name': 'Vault', 'description': 'Cold.',
                  'exits': {'south': {'to': 'hall', 'key': 'key'}}, 'items': ['crown']},
        'attic': {'name': 'Attic', 'description': 'Low.', 'exits': {'down': 'hall'}},
        'crypt': {'name': 'Crypt', 'description': 'Bones.', 'exits': {'up': 'hall'}},
    },
    'items': {
        'key': {'name': 'iron key', 'description': 'Heavy.'},
        'bone': {'name': 'bone', 'description': 'Old.'},
        'gem': {'name': 'green gem', 'description': 'Shiny.', 'treasure': 25},
        'crown': {'name': 'crown', 'description': 'Gold.', 'treasure': 100},
    },
}


@pytest.fixture
def world():
    return World.from_dict(copy.deepcopy(DATA))


@pytest.fixture
def game(world):
    return Game(world)


def play(game, *cmds):
    return [game.do(c) for c in cmds]


def test_world_locks_and_treasure(world):
    hall = world.rooms['hall']
    assert hall.exits == {'north': 'vault', 'up': 'attic', 'east': 'study', 'down': 'crypt'}
    assert hall.locks == {'north': 'key', 'up': 'key', 'down': 'bone'}
    assert world.rooms['study'].locks == {}
    assert world.items['gem'].treasure == 25 and world.items['key'].treasure == 0


@pytest.mark.parametrize('mutate', [
    lambda d: d['rooms']['study']['exits'].update(south={'to': 'hall'}),
    lambda d: d['rooms']['study']['exits'].update(south={'key': 'key'}),
    lambda d: d['rooms']['study']['exits'].update(south={'to': 'moon', 'key': 'key'}),
    lambda d: d['rooms']['study']['exits'].update(south={'to': 'hall', 'key': 'spoon'}),
    lambda d: d['items']['gem'].update(treasure=-1),
    lambda d: d['items']['gem'].update(treasure='lots'),
])
def test_world_lock_errors(mutate):
    data = copy.deepcopy(DATA)
    mutate(data)
    with pytest.raises(WorldError):
        World.from_dict(data)


def test_parse_use_and_score():
    assert parse('use the iron key') == Command('use', 'iron key')
    assert parse('SCORE') == Command('score', None)
    for line, message in [('use', 'Use what?'), ('use a', 'Use what?'),
                          ('score now', "I don't understand that.")]:
        with pytest.raises(ParseError) as exc:
            parse(line)
        assert str(exc.value) == message


def test_locked_exit_blocks_without_a_move(game):
    assert game.do('n') == 'The way north is locked.'
    assert game.room == 'hall' and game.moves == 0
    assert game.do('west') == "You can't go that way."


def test_look_marks_locked_exits(game):
    assert game.do('look').splitlines()[2] == \
        'Exits: north (locked), east, up (locked), down (locked).'


def test_use_unlocks_every_matching_exit_here(game):
    assert play(game, 'take key', 'use iron key') == ['Taken: iron key.', 'Unlocked: north, up.']
    assert game.do('look').splitlines()[2] == 'Exits: north, east, up, down (locked).'
    assert game.do('use key') == 'Nothing here to use the iron key on.'
    assert game.do('n').startswith('Vault\n')


def test_use_needs_item_in_inventory(game):
    assert game.do('use key') == "You aren't carrying that."
    assert game.do('use sword') == "You aren't carrying that."
    game.do('take key')
    game.do('e')
    assert game.do('use key') == 'Nothing here to use the iron key on.'


def test_unlock_is_one_sided(game):
    play(game, 'take key', 'use key', 'north')
    assert game.do('look').splitlines()[2] == 'Exits: south (locked).'
    assert game.do('s') == 'The way south is locked.'
    assert game.do('use key') == 'Unlocked: south.'
    assert game.do('s').startswith('Hall\n')


def test_score_visits_and_treasure(game):
    assert game.do('score') == 'Your score is 0.'
    play(game, 'e')
    assert game.score == 10
    play(game, 'take gem', 'drop gem', 'take gem', 'w', 'e')
    assert game.score == 35
    play(game, 'take bone', 'w', 'use bone', 'd', 'up', 'take key', 'use key', 'n',
         'take crown')
    assert game.do('score') == 'Your score is 155.'


def test_start_room_scores_nothing(game):
    play(game, 'e', 'w')
    assert game.score == 10


def test_save_version_2_fields(game):
    play(game, 'take key', 'use key', 'n', 'take crown')
    data = json.loads(game.save())
    assert data['version'] == 2
    assert data['unlocked'] == [['hall', 'north'], ['hall', 'up']]
    assert data['visited'] == ['hall', 'vault']
    assert data['scored'] == ['crown']
    assert data['score'] == 110
    assert data['moves'] == 1


def test_round_trip_keeps_locks_and_score(world, game):
    play(game, 'take key', 'use key', 'e', 'take gem', 'drop gem')
    restored = Game.load(world, game.save())
    assert restored.score == game.score == 35
    for cmd in ['take gem', 'w', 'n', 'score', 'look', 's', 'use key', 's', 'down']:
        assert restored.do(cmd) == game.do(cmd), cmd


def test_version_1_save_loads(world):
    old = {'version': 1, 'room': 'study', 'inventory': ['key'],
           'items': {'study': ['gem'], 'hall': []}, 'moves': 3}
    g = Game.load(world, json.dumps(old))
    assert g.room == 'study' and g.score == 0 and g.inventory == ['key']
    assert g.do('w').startswith('Hall\n')
    assert g.score == 0                      # hall and study already count as visited
    assert g.do('n') == 'The way north is locked.'
    play(g, 'use key', 'n')
    assert g.score == 10
    assert json.loads(g.save())['visited'] == ['hall', 'study', 'vault']


def v2(**changes):
    data = {'version': 2, 'room': 'hall', 'inventory': [], 'items': {'hall': ['key']},
            'moves': 0, 'unlocked': [], 'visited': ['hall'], 'scored': [], 'score': 0}
    data.update(changes)
    return json.dumps(data)


def test_version_2_save_loads(world):
    g = Game.load(world, v2(unlocked=[['hall', 'north']], visited=['hall', 'vault'],
                            scored=['gem'], score=42))
    assert g.score == 42
    assert g.do('n').startswith('Vault\n')
    assert g.score == 42


@pytest.mark.parametrize('text', [
    v2(version=3),
    json.dumps({k: v for k, v in json.loads(v2()).items() if k != 'scored'}),
    v2(unlocked=[['hall', 'east']]),
    v2(unlocked=[['moon', 'north']]),
    v2(visited=['moon']),
    v2(scored=['sword']),
    v2(score=-5),
    v2(room='moon'),
])
def test_version_2_load_errors(world, text):
    with pytest.raises(SaveError):
        Game.load(world, text)
