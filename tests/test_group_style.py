"""Tests for myRef.group_style."""

import pytest

from PyQt6.QtCore import Qt

from myRef import group_style


def test_from_data_defaults():
    assert group_style.from_data(None) == group_style.DEFAULTS
    assert group_style.from_data({'color': '#ff000000'}) == \
        group_style.DEFAULTS


def test_from_data_valid_values():
    data = {'border_color': '#ff112233', 'border_width': 5,
            'border_style': 'dash_dot', 'title_color': '#80ffffff',
            'title_size': 30}
    style = group_style.from_data(data)
    assert style['border_color'] == '#ff112233'
    assert style['border_width'] == 5.0
    assert style['border_style'] == 'dash_dot'
    assert style['title_color'] == '#80ffffff'
    assert style['title_size'] == 30.0


@pytest.mark.parametrize('key,value', [
    ('border_color', 'not a color'),
    ('border_color', 12),
    ('border_width', 'thick'),
    ('border_width', True),
    ('border_width', float('nan')),
    ('border_style', 'wobbly'),
    ('title_size', None),
])
def test_from_data_invalid_values_fall_back(key, value):
    assert group_style.from_data({key: value})[key] == \
        group_style.DEFAULTS[key]


def test_clean_value_clamps():
    assert group_style.clean_value('border_width', -3) == 0
    assert group_style.clean_value('border_width', 10**6) == \
        group_style.MAX_BORDER_WIDTH
    assert group_style.clean_value('title_size', 10**6) == \
        group_style.MAX_TITLE_SIZE


def test_clean_value_unknown_key():
    with pytest.raises(KeyError):
        group_style.clean_value('foo', 1)


def test_to_data_only_non_defaults():
    style = group_style.default_style()
    assert group_style.to_data(style) == {}
    style['border_width'] = 7.0
    assert group_style.to_data(style) == {'border_width': 7.0}


@pytest.mark.parametrize('value,expected', [
    (0.5, 0.5), (2, 1.0), (-1, 0.0), ('x', 1.0), (None, 1.0)])
def test_clean_opacity(value, expected):
    assert group_style.clean_opacity(value) == expected


def test_border_pen_none_without_width():
    style = group_style.default_style()
    style['border_width'] = 0
    assert group_style.border_pen(style) is None


@pytest.mark.parametrize('name', list(group_style.BORDER_STYLES))
def test_border_pen_styles(qapp, name):
    style = group_style.default_style()
    style['border_style'] = name
    style['border_width'] = 3
    pen = group_style.border_pen(style)
    assert pen.widthF() == 3
    if group_style.BORDER_STYLES[name] is None:
        assert pen.style() == Qt.PenStyle.SolidLine
    else:
        assert pen.dashPattern() == group_style.BORDER_STYLES[name]


def test_title_font(qapp):
    style = group_style.default_style()
    style['title_size'] = 20
    assert group_style.title_font(style).pixelSize() == 20
    style['title_size'] = 0
    assert group_style.title_font(style) is None
