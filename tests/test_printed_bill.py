from copy import deepcopy
from io import BytesIO
from decimal import Decimal
import pdfplumber
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


def test_rows_continue_and_totals_follow_final_item():
    one = PdfReader(BytesIO(generate_pdf(document(14))))
    assert len(one.pages) == 1
    assert 'Equipment item 14' in one.pages[0].extract_text()
    two = PdfReader(BytesIO(generate_pdf(document(20))))
    assert len(two.pages) == 2
    first, last = (page.extract_text() for page in two.pages)
    assert 'Equipment item 20' in last and 'Equipment item 20' not in first
    assert 'CARRY FWD' in first and 'G. TOTAL' not in first
    assert 'G. TOTAL' in last and 'CGST 6%' in last
    assert 'DESCRIPTION OF GOODS' in first and 'DESCRIPTION OF GOODS' in last
    for index in range(1, 21):
        assert first.count(f'Equipment item {index}\n') + last.count(f'Equipment item {index}\n') == 1


def test_top_message_and_optional_metadata_stay_within_customer_box():
    d = document()
    d['top_note'] = 'For the coaching team'
    plain = generate_pdf(d)
    with pdfplumber.open(BytesIO(plain)) as pdf:
        page = pdf.pages[0]
        buyer_y = page.search('Example customer')[0]['top']
        message_y = page.search('For the coaching team')[0]['top']
        heading_y = page.search('DESCRIPTION OF GOODS')[0]['top']
        assert buyer_y < message_y < heading_y
    plain_text = PdfReader(BytesIO(plain)).pages[0].extract_text()
    assert 'State' not in plain_text
    assert 'Despatch Through' not in plain_text and 'Freight' not in plain_text
    assert plain_text.splitlines().count('GSTIN') == 0  # No empty buyer GSTIN box.

    d.update(state='Telangana', state_code='36', buyer_gstin='CUSTOMER-GSTIN',
             dispatch='Courier', freight='Extra')
    with pdfplumber.open(BytesIO(generate_pdf(d))) as pdf:
        with pdfplumber.open(BytesIO(plain)) as original:
            original_heading = original.pages[0].search('DESCRIPTION OF GOODS')[0]['top']
        detailed_heading = pdf.pages[0].search('DESCRIPTION OF GOODS')[0]['top']
        assert 19*72/25.4 < detailed_heading - original_heading < 21*72/25.4
    assert PdfReader(BytesIO(generate_pdf(d))).pages[0].extract_text().splitlines().count('GSTIN') == 1


def test_only_filled_item_rows_receive_serial_numbers():
    d = document(20)
    with pdfplumber.open(BytesIO(generate_pdf(d))) as pdf:
        numbers = []
        for page in pdf.pages:
            words = page.crop((10*72/25.4, 80*72/25.4, 20*72/25.4, 225*72/25.4)).extract_words()
            numbers += [int(w['text']) for w in words if w['text'].isdigit()]
        assert numbers == list(range(1, 21))


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
