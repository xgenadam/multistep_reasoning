import csv
import io
import subprocess
import sys
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from sales import (Group, IngestError, Report, RowError, Sale, build_report, parse_sales,
                   read_sales, to_csv, to_markdown)
from sales.aggregate import FIELDS, aggregate, filter_months, parse_month

HERE = Path(__file__).resolve().parent

GOOD = """date,region,product,units,unit_price
2026-01-05,north,widget,2,5.00
2026-01-20,south,widget,1,5
2026-02-03,north,gadget,3,2.50
2026-02-14,north,widget,1,5.5
2026-03-01,south,gadget,4,0.25
"""


def sales_of(text=GOOD):
    sales, errors = parse_sales(text)
    assert errors == []
    return sales


def run(*args):
    return subprocess.run([sys.executable, '-m', 'sales.cli', *args], cwd=HERE,
                          capture_output=True, text=True, timeout=30)


# ---------------------------------------------------------------- ingest

def test_parse_valid_rows():
    sales = sales_of()
    assert len(sales) == 5
    s = sales[0]
    assert s == Sale(date(2026, 1, 5), 'north', 'widget', 2, Decimal('5.00'))
    assert s.revenue == Decimal('10.00')
    assert isinstance(sales[3].unit_price, Decimal) and sales[3].revenue == Decimal('5.5')


def test_header_any_order_case_and_extra_columns():
    text = ' Units ,PRODUCT,note,Region,unit_price,Date\n3,bolt,x,east,1.10,2026-04-30\n'
    sales = sales_of(text)
    assert sales == [Sale(date(2026, 4, 30), 'east', 'bolt', 3, Decimal('1.10'))]


def test_fields_are_stripped_and_blank_lines_skipped():
    text = 'date,region,product,units,unit_price\n\n 2026-01-02 , west ,  nut , 7 , 0.5 \n\n'
    assert sales_of(text) == [Sale(date(2026, 1, 2), 'west', 'nut', 7, Decimal('0.5'))]


def test_missing_column_and_no_header():
    with pytest.raises(IngestError) as exc:
        parse_sales('date,region,units,unit_price\n2026-01-01,n,1,1\n')
    assert 'product' in str(exc.value)
    assert isinstance(exc.value, ValueError)
    with pytest.raises(IngestError):
        parse_sales('')


@pytest.mark.parametrize('row, field', [
    ('2026-02-30,n,p,1,1.00', 'date'),
    ('20260203,n,p,1,1.00', 'date'),
    ('2026-02-03, ,p,1,1.00', 'region'),
    ('2026-02-03,n,,1,1.00', 'product'),
    ('2026-02-03,n,p,0,1.00', 'units'),
    ('2026-02-03,n,p,1,-1', 'unit_price'),
    ('2026-02-03,n,p,1,5.505', 'unit_price'),
    ('2026-02-03,n,p,1,.5', 'unit_price'),
    ('bad,,,0,x', 'date'),
    ('2026-02-03,n,p,1', 'row'),
    ('2026-02-03,n,p,1,1,extra', 'row'),
])
def test_row_errors(row, field):
    sales, errors = parse_sales('date,region,product,units,unit_price\n' + row + '\n')
    assert sales == []
    assert len(errors) == 1
    assert isinstance(errors[0], RowError)
    assert errors[0].line == 2
    assert errors[0].message.startswith(field + ': ')


def test_error_line_numbers_count_header_and_blank_lines():
    text = ('date,region,product,units,unit_price\n2026-01-01,n,p,1,1\n\n'
            '2026-01-01,n,p,x,1\n2026-01-02,s,p,2,2\n2026-13-01,n,p,1,1\n')
    sales, errors = parse_sales(text)
    assert len(sales) == 2
    assert [e.line for e in errors] == [4, 6]


def test_read_sales_utf8_bom(tmp_path):
    path = tmp_path / 'in.csv'
    path.write_bytes(b'\xef\xbb\xbf' + 'date,region,product,units,unit_price\n'
                     '2026-01-01,M\xc3\xbcnchen,caf\xc3\xa9,1,2\n'.encode('latin-1'))
    sales, errors = read_sales(path)
    assert errors == [] and sales[0].region == 'München' and sales[0].product == 'café'


# ---------------------------------------------------------------- aggregate

def test_aggregate_by_month():
    groups = aggregate(sales_of(), ('month',))
    assert groups == [Group(('2026-01',), 3, 2, Decimal('15.00')),
                      Group(('2026-02',), 4, 2, Decimal('13.00')),
                      Group(('2026-03',), 4, 1, Decimal('1.00'))]


def test_aggregate_key_order_follows_by():
    groups = aggregate(sales_of(), ('product', 'region'))
    assert [g.key for g in groups] == [('gadget', 'north'), ('gadget', 'south'),
                                       ('widget', 'north'), ('widget', 'south')]
    assert groups[2] == Group(('widget', 'north'), 3, 2, Decimal('15.50'))


@pytest.mark.parametrize('by', [(), ('day',), ('month', 'month')])
def test_aggregate_bad_by(by):
    with pytest.raises(ValueError):
        aggregate(sales_of(), by)


def test_months_filter_and_parse():
    sales = sales_of()
    assert len(filter_months(sales, '2026-02', '2026-02')) == 2
    assert len(filter_months(sales, start='2026-02')) == 3
    assert len(filter_months(sales, end='2026-01')) == 2
    assert parse_month('2026-12') == '2026-12'
    for bad in ('2026-13', '2026-1', '26-01', '2026-00'):
        with pytest.raises(ValueError):
            parse_month(bad)
    assert FIELDS == ('month', 'region', 'product')


def test_build_report_total():
    report = build_report(sales_of(), ('region',))
    assert isinstance(report, Report)
    assert report.by == ('region',)
    assert report.total == Group((), 11, 5, Decimal('29.00'))


# ---------------------------------------------------------------- writers

def test_csv_writer_table():
    out = to_csv(build_report(sales_of(), ('month',)))
    assert out == ('month,units,orders,revenue,share\n'
                   '2026-01,3,2,15.00,51.7%\n'
                   '2026-02,4,2,13.00,44.8%\n'
                   '2026-03,4,1,1.00,3.4%\n'
                   'TOTAL,11,5,29.00,100.0%\n')


def test_markdown_writer_table():
    out = to_markdown(build_report(sales_of(), ('region', 'product')))
    assert out == ('| region | product | units | orders | revenue | share |\n'
                   '| --- | --- | ---: | ---: | ---: | ---: |\n'
                   '| north | gadget | 3 | 1 | 7.50 | 25.9% |\n'
                   '| north | widget | 3 | 2 | 15.50 | 53.4% |\n'
                   '| south | gadget | 4 | 1 | 1.00 | 3.4% |\n'
                   '| south | widget | 1 | 1 | 5.00 | 17.2% |\n'
                   '| TOTAL |  | 11 | 5 | 29.00 | 100.0% |\n')


def test_share_rounds_half_up_in_both_writers():
    text = ('date,region,product,units,unit_price\n'
            '2026-01-01,a,p,1,1.00\n2026-01-01,b,p,1,15.00\n')
    report = build_report(sales_of(text), ('region',))
    assert '6.3%' in to_csv(report) and '93.8%' in to_csv(report)
    assert '| a | 1 | 1 | 1.00 | 6.3% |' in to_markdown(report)


def test_zero_revenue_and_empty_report():
    text = 'date,region,product,units,unit_price\n2026-01-01,a,p,3,0\n'
    report = build_report(sales_of(text), ('month',))
    assert to_csv(report) == ('month,units,orders,revenue,share\n2026-01,3,1,0.00,0.0%\n'
                              'TOTAL,3,1,0.00,0.0%\n')
    empty = build_report([], ('month', 'region'))
    assert to_markdown(empty).splitlines()[2:] == ['| TOTAL |  | 0 | 0 | 0.00 | 0.0% |']


def test_writers_escape_and_quote():
    text = ('date,region,product,units,unit_price\n'
            '2026-01-01,"north, east",a|b,1,2\n')
    report = build_report(sales_of(text), ('region', 'product'))
    rows = list(csv.reader(io.StringIO(to_csv(report))))
    assert rows[1][:2] == ['north, east', 'a|b']
    assert '"north, east"' in to_csv(report)
    assert '| north, east | a\\|b | 1 |' in to_markdown(report)


# ---------------------------------------------------------------- CLI

@pytest.fixture
def infile(tmp_path):
    path = tmp_path / 'sales.csv'
    path.write_text(GOOD)
    return path


def test_cli_default_csv_by_month(infile):
    r = run(str(infile))
    assert r.returncode == 0, r.stderr
    assert r.stdout == to_csv(build_report(sales_of(), ('month',)))


def test_cli_markdown_by_two_fields_with_month_range(infile):
    r = run(str(infile), '--by', 'product,month', '--format', 'md', '--from', '2026-02',
            '--to', '2026-03')
    assert r.returncode == 0, r.stderr
    lines = r.stdout.splitlines()
    assert lines[0] == '| product | month | units | orders | revenue | share |'
    assert lines[2:] == ['| gadget | 2026-02 | 3 | 1 | 7.50 | 53.6% |',
                         '| gadget | 2026-03 | 4 | 1 | 1.00 | 7.1% |',
                         '| widget | 2026-02 | 1 | 1 | 5.50 | 39.3% |',
                         '| TOTAL |  | 8 | 3 | 14.00 | 100.0% |']


def test_cli_output_file(infile, tmp_path):
    out = tmp_path / 'report.csv'
    r = run(str(infile), '--by', 'region', '--output', str(out))
    assert r.returncode == 0 and r.stdout == ''
    assert out.read_text(encoding='utf-8').splitlines()[-1] == 'TOTAL,11,5,29.00,100.0%'


def test_cli_row_errors_warn_but_report(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text(GOOD + '2026-03-02,north,widget,0,5\nnot-a-date,x,y,1,1\n')
    r = run(str(path))
    assert r.returncode == 0
    errs = r.stderr.splitlines()
    assert len(errs) == 2
    assert errs[0].startswith('line 7: units: ') and errs[1].startswith('line 8: date: ')
    assert r.stdout.splitlines()[-1] == 'TOTAL,11,5,29.00,100.0%'


def test_cli_strict_writes_nothing(tmp_path):
    path = tmp_path / 'bad.csv'
    path.write_text(GOOD + '2026-03-02,north,widget,0,5\n')
    out = tmp_path / 'r.md'
    r = run(str(path), '--strict', '--output', str(out))
    assert r.returncode == 1
    assert not out.exists()
    assert r.stderr.startswith('line 7: units: ')
    r2 = run(str(path), '--strict')
    assert r2.returncode == 1 and r2.stdout == ''


@pytest.mark.parametrize('extra', [
    ['--by', 'month,day'], ['--by', 'region,region'], ['--from', '2026-13'],
    ['--from', '2026-03', '--to', '2026-01'],
])
def test_cli_usage_errors(infile, extra):
    r = run(str(infile), *extra)
    assert r.returncode == 2
    assert r.stdout == ''
    assert r.stderr.startswith('error:')


def test_cli_missing_file_and_missing_column(tmp_path):
    r = run(str(tmp_path / 'nope.csv'))
    assert r.returncode == 2 and r.stderr.startswith('error:')
    path = tmp_path / 'nocol.csv'
    path.write_text('date,region,units,unit_price\n')
    r = run(str(path))
    assert r.returncode == 2 and r.stderr.startswith('error:') and r.stdout == ''
