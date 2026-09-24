from copy import deepcopy
from io import BytesIO
from decimal import Decimal
from pypdf import PdfReader
import pytest
from billing import new_document, item
from pdf_renderer import generate_pdf, amount_in_words


def document(count=2):
    d = new_document('Bill')
    d.update(buyer='Example customer', number='DEMO-123')
    d['items'] = []
    for index in range(count):
        p = item()
        p.update(name=f'Equipment item {index+1}', quantity=1, price=100, hsn='95069990')
        d['items'].append(p)
    return d


def test_fourteen_rows_and_page_overflow():
    one = PdfReader(BytesIO(generate_pdf(document(14))))
    assert len(one.pages) == 1
    assert 'Equipment item 14' in one.pages[0].extract_text()
    two = PdfReader(BytesIO(generate_pdf(document(15))))
    assert len(two.pages) == 2
    first, last = (page.extract_text() for page in two.pages)
    assert 'Equipment item 15' in last and 'Equipment item 15' not in first
    assert 'CARRY FWD' in first and 'G. TOTAL' not in first
    assert 'G. TOTAL' in last and 'CGST 6%' in last
    assert 'DESCRIPTION OF GOODS' in first and 'DESCRIPTION OF GOODS' in last


def test_printed_fields_selected_taxes_and_logo():
    d = document()
    d.update(buyer_gstin='CUSTOMER-GSTIN', freight='At actual cost', top_note='For the coaching team')
    d['company']['gstin'] = 'SHOP-GSTIN'
    d['taxes'] = {'IGST': 12}
    reader = PdfReader(BytesIO(generate_pdf(d)))
    text = reader.pages[0].extract_text()
    for value in ['SHOP-GSTIN', 'CUSTOMER-GSTIN', 'At actual cost', 'For the coaching team', 'IGST 12%', 'BANK DETAILS']:
        assert value in text
    assert 'CGST' not in text and 'SGST' not in text
    assert len(reader.pages[0].images) == 1  # The real shop archer/letterhead asset.
    d['taxes'] = {}
    text = PdfReader(BytesIO(generate_pdf(d))).pages[0].extract_text()
    assert 'TAX INVOICE' not in text and 'IGST' not in text


def test_indian_currency_words():
    assert amount_in_words(0) == 'Zero Rupees Only'
    assert amount_in_words(Decimal('45333.12')) == 'Forty Five Thousand Three Hundred Thirty Three Rupees and Twelve Paise Only'
    assert amount_in_words(100001) == 'One Lakh One Rupees Only'
    assert amount_in_words(10000000) == 'One Crore Rupees Only'
    assert amount_in_words(Decimal('1.995')) == 'Two Rupees Only'


def test_long_notes_preserved_on_appendix():
    d = document()
    d['notes'] = '\n'.join(f'Note {i}: Delivery instructions to retain in the document.' for i in range(150))
    reader = PdfReader(BytesIO(generate_pdf(d)))
    assert len(reader.pages) > 2
    text = '\n'.join(page.extract_text() for page in reader.pages)
    assert 'See attached notes and terms.' in text
    for i in range(150):
        assert f'Note {i}:' in text


def test_long_description_wraps_without_loss():
    d = document()
    description = 'A long equipment description with size, colour and configuration. ' * 10
    d['items'][0]['name'] = description
    reader = PdfReader(BytesIO(generate_pdf(d)))
    text = ' '.join(page.extract_text() for page in reader.pages)
    assert ' '.join(description.split()) in ' '.join(text.split())
