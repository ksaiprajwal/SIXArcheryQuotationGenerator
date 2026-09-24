"""Run from repository root: PYTHONPATH=. python examples/generate_samples.py"""
from pathlib import Path
from billing import new_document, item
from pdf_renderer import generate_pdf

for kind in ('Quotation', 'Bill'):
    d = new_document(kind)
    d.update(number='Q-26-DEMO' if kind == 'Quotation' else 'B-26-DEMO',
             buyer='Example Archery Academy', address='Sports Training Centre\nHyderabad, Telangana',
             state='Telangana', state_code='36',
             top_note='Kind attention: Head Coach | Equipment for the junior training programme',
             notes='Transportation cost extra.\nThank you for choosing Shoot In X Archery.')
    d['company'].update(gstin='DEMO GSTIN', address='Example shop address', phone='Example phone', bank='Example bank details')
    d['items'] = []
    for name, qty, price in [('Recurve training bow - 68 inch, right hand', 2, 18000),
                             ('Carbon arrows - matched set of 12', 3, 4500),
                             ('Arm guard and finger tab kit', 5, 850)]:
        product = item()
        product.update(name=name, quantity=qty, price=price, hsn='95069990')
        d['items'].append(product)
    Path(f'examples/sample-{kind.lower()}.pdf').write_bytes(generate_pdf(d))
