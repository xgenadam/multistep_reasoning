"""plan_screen.py: round 0 of the meta-prompt tournament (plans only)."""


def test_variants_and_plan_metrics():
    from tests.test_baseline.conftest import load_baseline_module
    ps = load_baseline_module('plan_screen')
    assert ps.parse_variant('H=self_critique') == ('H', 'self_critique', {})
    name, dec, opts = ps.parse_variant('FS=meta:frozen:journal/design/meta-prompts/x.txt')
    assert (name, dec, opts['meta_prompt']) == ('FS', 'meta', 'frozen') and opts['meta_prompt_file'].endswith('x.txt')
    assert ps.parse_variant('DS=meta:dynamic')[2] == {'meta_prompt': 'dynamic'}
    tasks = [{'name': 'Write wordcount.py', 'objective': 'the whole file'},
             {'name': 'Add error handling', 'objective': 'to wordcount.py'},
             {'name': 'Format the table', 'objective': 'aligned columns'}]
    m = ps.plan_metrics(tasks, ['wordcount.py'])
    assert m == {'sub_tasks': 3, 'files': 1, 'sub_tasks_per_file': 3.0, 'mentions_per_file': {'wordcount.py': 2},
                 'naming_no_file': 1, 'fallback': False}
