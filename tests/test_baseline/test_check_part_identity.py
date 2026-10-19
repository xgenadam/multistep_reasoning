"""P0-3 (D-014): an artifact follow-up keeps the prior turn's parts."""

import pytest


def _part(pid):
    return {'id': pid, 'kind': 'section', 'body': f'{pid} body'}


def _op(kind, **fields):
    return {'op': {'type': kind, **fields}, 'origin_task': 't'}


PRIOR_LOG = [_op('add_part', id='intro'), _op('add_part', id='body')]
PRIOR = {'snapshot': {'parts': [_part('intro'), _part('body')], 'op_log': PRIOR_LOG}}


def _turn(final_ids, ops):
    return {'snapshot': {'parts': [_part(i) for i in final_ids], 'op_log': PRIOR_LOG + ops}}


@pytest.mark.parametrize('final_ids, ops, lost', [
    # Add-only: a new section beside the old ones.
    (['intro', 'body', 'migration'], [_op('add_part', id='migration')], []),
    # Update in place, after scratch parts were added and deleted.
    (['intro', 'body'], [_op('add_part', id='scratch'), _op('update_part', id='body'),
                         _op('delete_part', id='scratch')], []),
    # Merged into a surviving part, including through a second merge.
    (['intro'], [_op('merge_parts', ids=['intro', 'body'])], []),
    (['new'], [_op('add_part', id='new'), _op('merge_parts', ids=['body', 'intro']),
               _op('merge_parts', ids=['new', 'body'])], []),
    # Rebuild: old parts deleted, their text re-added under a new id.
    (['report'], [_op('add_part', id='report'), _op('delete_part', id='intro'),
                  _op('delete_part', id='body')], ['intro', 'body']),
    # Merged, then the survivor deleted.
    ([], [_op('merge_parts', ids=['intro', 'body']), _op('delete_part', id='intro')],
     ['intro', 'body']),
], ids=['add-only', 'update-in-place', 'merged', 'merge-chain', 'rebuild', 'merge-then-delete'])
def test_lost_prior_parts(check, final_ids, ops, lost):
    assert check.lost_prior_parts(_turn(final_ids, ops), PRIOR) == lost


def test_unknown_without_snapshots(check):
    assert check.lost_prior_parts({'document': {}}, {'document': {}}) is None


def test_only_followups_of_artifact_scenarios_are_checked(check):
    rebuild = _turn(['report'], [_op('delete_part', id='intro'), _op('delete_part', id='body'),
                                 _op('add_part', id='report')])
    name = "follow-up keeps the prior turn's parts (P0-3)"
    scored = check.score_scenario('s3', {'followup_keeps_parts': True}, rebuild, PRIOR, True)
    assert [c[1] for c in scored if c[0] == name] == [False]
    # A first turn, or a scenario without the key (a chat follow-up), is not.
    assert not [c for c in check.score_scenario('s3', {'followup_keeps_parts': True},
                                                rebuild, None, False) if c[0] == name]
    assert not [c for c in check.score_scenario('chat', {}, rebuild, PRIOR, True)
                if c[0] == name]
