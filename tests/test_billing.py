from copy import deepcopy
import pytest
from billing import new_document, totals, validate, duplicate
from storage import Store, ConflictError
from pdf_renderer import generate_pdf

def example():
    d = new_document()
    d['buyer'] = 'Example Archery Academy'
    d['items'][0].update(name='Recurve arrows', hsn='95069990', quantity=3, price=100.25)
    return d

def test_tax_rounding_and_modes():
    d = example()
    assert str(totals(d)[3]) == '336.85'
    d['taxes'] = {'IGST':12}
    assert str(totals(d)[3]) == '336.84'  # Per-component rounding differs by one paisa.
    d['taxes'] = {}
    assert str(totals(d)[3]) == '300.75'

def test_tax_conflict_and_zero_rate():
    d = example()
    d['taxes'] = {'CGST':6, 'IGST':12}
    with pytest.raises(ValueError): validate(d)
    d['taxes'] = {}
    d['items'][0]['price'] = 0
    validate(d)

@pytest.mark.parametrize('value', [float('nan'), float('inf'), -1])
def test_invalid_amounts(value):
    d = example()
    d['items'][0]['price'] = value
    with pytest.raises(ValueError): validate(d)

def test_saved_pdf_history_conflict_and_restart(tmp_path):
    path = tmp_path / 'test.sqlite'
    s = Store(local_path=path)
    d, pdf = s.save(example(), generate_pdf)
    assert pdf.startswith(b'%PDF')
    assert Store(local_path=path).get(d['id'])[0] == d
    stale = deepcopy(d)
    d['top_note'] = 'Revised for coach'
    revised, new_pdf = s.save(d, generate_pdf)
    assert revised['number'] == d['number'] and revised['version'] == 2
    assert s.get(d['id'], 1)[1] == pdf
    assert s.get(d['id'])[1] == new_pdf
    with pytest.raises(ConflictError): s.save(stale, generate_pdf)
    assert len(s.versions(d['id'])) == 2
    assert len(s.list('academy')) == 1
    assert s.list('unmatched') == []
    assert s.list('%') == []
    assert s.list(kind='Bill') == []

def test_render_failure_does_not_save(tmp_path):
    s = Store(local_path=tmp_path / 'test.sqlite')
    def broken(d): raise RuntimeError('renderer failed')
    with pytest.raises(RuntimeError): s.save(example(), broken)
    assert not s.list()

def test_duplicate_preserves_source():
    d = example()
    d['number'] = 'Q-1'
    d['version'] = 1
    cp = duplicate(d, 'Bill')
    assert cp['id'] != d['id'] and not cp['number'] and cp['version'] == 0
    cp['items'][0]['name'] = 'Changed'
    assert d['items'][0]['name'] == 'Recurve arrows'

def test_pagination(tmp_path):
    s = Store(local_path=tmp_path / 'test.sqlite')
    for _ in range(23): s.save(example(), lambda d: b'pdf')
    assert len(s.list()) == 20
    assert len(s.list(page=1)) == 3
    assert not ({d['id'] for d,_ in s.list()} & {d['id'] for d,_ in s.list(page=1)})
