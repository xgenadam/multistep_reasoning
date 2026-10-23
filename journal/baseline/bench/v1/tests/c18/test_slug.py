import pytest

from slug import slugify


@pytest.mark.parametrize('text, expected', [
    ('Hello, World!', 'hello-world'),
    ('  Leading and trailing  ', 'leading-and-trailing'),
    ("Don't Stop", 'dont-stop'),
    ('It’s here', 'its-here'),
    ('Crème Brûlée', 'creme-brulee'),
    ('ﬁnal Ⅳ', 'final-iv'),
    ('a--b__c  d', 'a-b-c-d'),
    ('Version 2.0 (beta)', 'version-2-0-beta'),
    ('日本語 title', 'title'),
])
def test_basic_transformations(text, expected):
    assert slugify(text) == expected


@pytest.mark.parametrize('text', ['', '!!!', '日本語', "'"])
def test_empty_becomes_untitled(text):
    assert slugify(text) == 'untitled'


def test_cut_at_word_boundary():
    assert slugify('the quick brown fox', max_len=12) == 'the-quick'
    assert slugify('the quick brown fox', max_len=15) == 'the-quick-brown'
    assert slugify('the quick brown fox', max_len=19) == 'the-quick-brown-fox'


def test_long_first_word_is_hard_cut():
    assert slugify('supercalifragilistic word', max_len=5) == 'super'


def test_max_len_default_is_50():
    out = slugify(' '.join(['word'] * 20))
    assert len(out) <= 50
    assert out == '-'.join(['word'] * 10)


def test_max_len_below_one_raises():
    with pytest.raises(ValueError):
        slugify('x', max_len=0)


def test_unique_suffixes():
    assert slugify('Hello', existing={'hello'}) == 'hello-2'
    assert slugify('Hello', existing={'hello', 'hello-2', 'hello-3'}) == 'hello-4'
    assert slugify('Hello', existing={'hello-2'}) == 'hello'


def test_untitled_is_made_unique_too():
    assert slugify('???', existing=['untitled']) == 'untitled-2'


def test_suffix_respects_max_len():
    existing = {'the-quick'}
    assert slugify('the quick brown fox', max_len=12, existing=existing) == 'the-quick-2'
    out = slugify('the quick brown fox', max_len=10, existing=existing)
    assert out == 'the-2'
    assert len(out) <= 10


def test_suffix_shortens_from_full_base():
    # base is 'alpha-beta-gamma'; max_len 14 gives 'alpha-beta'; with '-2' the
    # base must fit in 12 characters, which is still 'alpha-beta'.
    assert slugify('alpha beta gamma', max_len=14, existing={'alpha-beta'}) == 'alpha-beta-2'
    # with '-10' (3 chars) the base must fit in 11: still 'alpha-beta'
    taken = {'alpha-beta'} | {f'alpha-beta-{n}' for n in range(2, 10)}
    assert slugify('alpha beta gamma', max_len=13, existing=taken) == 'alpha-beta-10'


def test_existing_not_modified():
    existing = ['a']
    slugify('a', existing=existing)
    assert existing == ['a']
