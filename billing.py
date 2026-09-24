"""Document model and money calculations, independent of the UI."""
from copy import deepcopy
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

DEFAULT_COMPANY = {
    'name': 'SHOOT IN X ARCHERY',
    'tagline': 'Archery sport items, sports goods, gifts & novelties',
    # Configure private shop details through Streamlit secrets (COMPANY_*).
    'address': '', 'phone': '', 'gstin': '', 'bank': '',
}


def item():
    return {'id': uuid4().hex, 'name': '', 'hsn': '', 'quantity': 1.0, 'price': 0.0}

def new_document(kind='Quotation', company=None):
    return {'id': uuid4().hex, 'version': 0, 'number': '', 'kind': kind,
            'date': date.today().isoformat(), 'buyer': '', 'address': '',
            'buyer_gstin': '', 'state': '', 'state_code': '', 'dispatch': '',
            'top_note': '', 'notes': 'Transportation cost extra.',
            'items': [item()], 'taxes': {'CGST': 6.0, 'SGST': 6.0},
            'company': deepcopy(company or DEFAULT_COMPANY), 'signed': False}

def money(value):
    n = Decimal(str(value))
    if not n.is_finite():
        raise ValueError('Enter a valid finite amount.')
    return n.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

def totals(doc):
    lines = [money(Decimal(str(p['quantity'])) * Decimal(str(p['price']))) for p in doc['items']]
    subtotal = sum(lines, Decimal('0.00'))
    taxes = {name: money(subtotal * Decimal(str(rate)) / 100) for name, rate in doc['taxes'].items()}
    return lines, subtotal, taxes, subtotal + sum(taxes.values(), Decimal('0.00'))

def validate(doc):
    if not doc['buyer'].strip():
        raise ValueError('Please enter the customer name.')
    date.fromisoformat(doc['date'])
    if not doc['items']:
        raise ValueError('Please add at least one item.')
    for i, p in enumerate(doc['items'], 1):
        if not p['name'].strip():
            raise ValueError(f'Please enter a name for item {i}.')
        if money(p['quantity']) <= 0 or money(p['price']) < 0:
            raise ValueError(f'Check the quantity and rate for item {i}.')
    if 'IGST' in doc['taxes'] and ({'CGST', 'SGST'} & doc['taxes'].keys()):
        raise ValueError('Choose IGST or CGST / SGST, not both together.')
    for name, rate in doc['taxes'].items():
        if name not in ('CGST', 'SGST', 'IGST') or not 0 <= money(rate) <= 100:
            raise ValueError('Check the tax rates.')
    totals(doc)

def duplicate(doc, kind=None):
    result = deepcopy(doc)
    result.update(id=uuid4().hex, version=0, number='', date=date.today().isoformat(), kind=kind or doc['kind'])
    return result
