import random

import pytest

from rle import decode, encode

BS = '\\'


def test_examples_from_the_spec():
    assert encode('aaab') == '3ab'
    assert encode('a1') == 'a' + BS + '1'
    assert encode('111') == '3' + BS + '1'
    assert encode(BS) == BS + BS
    assert encode('x' * 12 + '22') == '12x2' + BS + '2'
    assert encode('') == ''


def test_single_characters_have_no_count():
    assert encode('abc') == 'abc'
    assert encode('abba') == 'a2ba'


def test_long_runs_and_multi_digit_counts():
    assert encode('z' * 100) == '100z'
    assert encode('a' * 10 + 'b') == '10ab'


def test_every_digit_escaped():
    assert encode('0123456789') == ''.join(BS + d for d in '0123456789')
    assert encode('5' * 10) == '10' + BS + '5'


def test_backslash_runs():
    assert encode(BS * 3 + 'n') == '3' + BS + BS + 'n'


def test_other_characters_written_as_themselves():
    assert encode('  \n\n\t') == '2 2\n\t'
    assert encode('éé日') == '2é日'
    assert encode('--++') == '2-2+'


def test_decode_examples():
    assert decode('3ab') == 'aaab'
    assert decode('12x2' + BS + '2') == 'x' * 12 + '22'
    assert decode(BS + BS) == BS
    assert decode('') == ''


def test_decode_accepts_split_runs():
    assert decode('2a2a') == 'aaaa'
    assert decode('aa') == 'aa'
    assert decode('2' + BS + '1' + BS + '1') == '111'


def test_decode_rejects_bad_counts():
    for data in ['1a', '0a', '02a', '01' + BS + '1', '00x']:
        with pytest.raises(ValueError):
            decode(data)


def test_decode_rejects_dangling_counts():
    for data in ['3', 'a12', '2a3']:
        with pytest.raises(ValueError):
            decode(data)


def test_decode_rejects_bad_escapes():
    for data in [BS + 'a', 'ab' + BS, '3' + BS, BS + 'n', BS]:
        with pytest.raises(ValueError):
            decode(data)


def test_type_errors():
    for bad in [None, b'aa', 3, ['a']]:
        with pytest.raises(TypeError):
            encode(bad)
        with pytest.raises(TypeError):
            decode(bad)


def test_round_trip_random():
    rng = random.Random(10)
    alphabet = 'ab12' + BS + ' \né'
    for _ in range(500):
        text = ''.join(rng.choice(alphabet) * rng.choice([1, 1, 2, 3, 11])
                       for _ in range(rng.randrange(0, 12)))
        data = encode(text)
        assert decode(data) == text
        assert encode(decode(data)) == data


def test_encode_output_is_maximal():
    rng = random.Random(11)
    for _ in range(200):
        text = ''.join(rng.choice('aab0') for _ in range(rng.randrange(1, 30)))
        data = encode(text)
        expected = []
        i = 0
        while i < len(text):
            j = i
            while j < len(text) and text[j] == text[i]:
                j += 1
            w = BS + text[i] if text[i] in '0123456789' + BS else text[i]
            expected.append((str(j - i) if j - i > 1 else '') + w)
            i = j
        assert data == ''.join(expected)
