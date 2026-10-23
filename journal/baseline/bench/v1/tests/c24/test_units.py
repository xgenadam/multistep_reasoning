import pytest

from units import DimensionError, UnitError, convert

approx = pytest.approx


@pytest.mark.parametrize('value, src, dst, expected', [
    (1, 'km', 'm', 1000),
    (12, 'in', 'ft', 1),
    (1, 'mi', 'km', 1.609344),
    (3, 'ft', 'yd', 1),
    (1, 'lb', 'oz', 16),
    (2500, 'g', 'kg', 2.5),
    (1, 't', 'lb', 1000 / 0.45359237),
    (90, 'min', 'h', 1.5),
    (1, 'day', 's', 86400),
    (250, 'ms', 's', 0.25),
])
def test_simple_units(value, src, dst, expected):
    assert convert(value, src, dst) == approx(expected)


def test_returns_float():
    out = convert(1, 'm', 'm')
    assert isinstance(out, float) and out == 1.0


def test_speed():
    assert convert(36, 'km/h', 'm/s') == approx(10)
    assert convert(60, 'mi/h', 'km/h') == approx(96.56064)
    assert convert(1, 'm/s', 'ft/min') == approx(60 / 0.3048)


def test_powers_scale_and_dimension():
    assert convert(1, 'km^2', 'm^2') == approx(1e6)
    assert convert(1, 'm^3', 'cm^3') == approx(1e6)
    assert convert(1, 'm/s^2', 'km/h^2') == approx(12960)


def test_force_like_units():
    assert convert(1, 'kg*m/s^2', 'g*cm/s^2') == approx(1e5)
    assert convert(2, 'lb*ft/s^2', 'kg*m/s^2') == approx(2 * 0.45359237 * 0.3048)


def test_left_to_right():
    assert convert(5, 'm/s*s', 'm') == approx(5)
    assert convert(1, 'm/s/s', 'm/s^2') == approx(1)
    assert convert(1, 'km*h/h', 'm') == approx(1000)


def test_dimension_mismatch():
    for src, dst in [('m', 's'), ('m', 'm^2'), ('m/s', 'm'), ('kg*m', 'kg'), ('m/s*s', 'm/s')]:
        with pytest.raises(DimensionError):
            convert(1, src, dst)


def test_unit_errors():
    for bad in ['', 'furlong', 'KM', 'm//s', 'm^', 'm^0', 'm^-1', 'm s', 'km /h', '*m', 'm/', 'm^1.5']:
        with pytest.raises(UnitError):
            convert(1, bad, 'm')


def test_error_classes_are_value_errors():
    assert issubclass(UnitError, ValueError)
    assert issubclass(DimensionError, ValueError)
    assert not issubclass(UnitError, DimensionError)


def test_unknown_unit_beats_dimension_check():
    with pytest.raises(UnitError):
        convert(1, 'm', 'parsec')
