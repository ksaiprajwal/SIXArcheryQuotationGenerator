"""A4 reconstruction of the shop's printed invoice pad.

The ruled form is drawn as vector lines and live text, not as a photographed
background. Its archer is clipped from the existing shop letterhead asset.
"""
from datetime import date
from decimal import Decimal
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas
from reportlab.platypus import Paragraph
from billing import money, totals

ROOT = Path(__file__).parent
pdfmetrics.registerFont(TTFont('Shop', str(ROOT / 'assets/DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('Shop-Bold', str(ROOT / 'assets/DejaVuSans-Bold.ttf')))
INK = colors.HexColor('#303438')
RULE = colors.HexColor('#73777B')
SHADE = colors.HexColor('#F2F3F4')
RED = colors.HexColor('#AE2928')
PAGE_W, PAGE_H = 210 * mm, 297 * mm
LEFT, RIGHT, BOTTOM = 10 * mm, 200 * mm, 287 * mm


def _words(n):
    small = ('Zero One Two Three Four Five Six Seven Eight Nine Ten Eleven Twelve '
             'Thirteen Fourteen Fifteen Sixteen Seventeen Eighteen Nineteen').split()
    tens = ['', '', 'Twenty', 'Thirty', 'Forty', 'Fifty', 'Sixty', 'Seventy', 'Eighty', 'Ninety']
    if n < 20:
        return small[n]
    if n < 100:
        return tens[n // 10] + (' ' + small[n % 10] if n % 10 else '')
    for value, label in [(10000000, 'Crore'), (100000, 'Lakh'), (1000, 'Thousand'), (100, 'Hundred')]:
        if n >= value:
            return _words(n // value) + ' ' + label + (' ' + _words(n % value) if n % value else '')


def amount_in_words(value):
    value = money(value)
    rupees = int(value)
    paise = int((value - rupees) * 100)
    return _words(rupees) + ' Rupees' + (' and ' + _words(paise) + ' Paise' if paise else '') + ' Only'


def _paragraph(text, width, size=9, bold=False, align=TA_LEFT, color=INK):
    style = ParagraphStyle('cell', fontName='Shop-Bold' if bold else 'Shop',
                           fontSize=size, leading=size * 1.25, textColor=color,
                           alignment=align, splitLongWords=True)
    paragraph = Paragraph(escape(str(text)).replace('\n', '<br/>'), style)
    _, height = paragraph.wrap(width, PAGE_H * 10)
    return paragraph, height


def generate_pdf(doc):
    output = BytesIO()
    c = canvas.Canvas(output, pagesize=(PAGE_W, PAGE_H), pageCompression=1)
    company = doc['company']
    kind = doc['kind']
    title = 'QUOTATION' if kind == 'Quotation' else ('TAX INVOICE' if doc['taxes'] else 'BILL')
    number = doc['number'] or 'PREVIEW'
    c.setTitle(f'{title} {number}')
    c.setAuthor(company['name'])
    line_amounts, subtotal, tax_amounts, grand = totals(doc)

    def line(x1, y1, x2, y2, weight=.35, dotted=False):
        c.saveState()
        c.setStrokeColor(INK if weight >= .7 else RULE)
        c.setLineWidth(weight)
        if dotted:
            c.setDash(.7, 1.7)
            c.setStrokeColor(colors.HexColor('#889099'))
        c.line(x1, PAGE_H-y1, x2, PAGE_H-y2)
        c.restoreState()

    def box(x, y, width, height, weight=.35):
        c.saveState()
        c.setStrokeColor(INK if weight >= .7 else RULE)
        c.setLineWidth(weight)
        c.rect(x, PAGE_H-y-height, width, height, stroke=1, fill=0)
        c.restoreState()

    def shade(x, y, width, height):
        c.saveState()
        c.setFillColor(SHADE)
        c.rect(x, PAGE_H-y-height, width, height, stroke=0, fill=1)
        c.restoreState()

    def text(value, x, y, width, size=9, bold=False, align='left', color=INK):
        # Single-line fields may shrink, but are never silently clipped.
        value = str(value)
        font = 'Shop-Bold' if bold else 'Shop'
        native = pdfmetrics.stringWidth(value, font, size)
        actual = min(size, size * width / native) if native else size
        if actual < 5.5:
            raise ValueError('A printed number or label is too long. Shorten it before saving.')
        c.saveState()
        c.setFont(font, actual)
        c.setFillColor(color)
        if align == 'right':
            c.drawRightString(x+width, PAGE_H-y-actual, value)
        elif align == 'center':
            c.drawCentredString(x+width/2, PAGE_H-y-actual, value)
        else:
            c.drawString(x, PAGE_H-y-actual, value)
        c.restoreState()

    def block(value, x, y, width, height, size=9, bold=False, align=TA_LEFT, color=INK, minimum=7):
        while size >= minimum:
            p, h = _paragraph(value, width, size, bold, align, color)
            if h <= height + .01:
                p.drawOn(c, x, PAGE_H-y-h)
                return
            size -= .25
        raise ValueError('Some text is too long for its printed box. Please shorten the shop, customer or delivery details.')

    def archer(x, y, width, height):
        header = ROOT / 'header.png'
        if not header.exists():
            raise ValueError('The shop logo asset header.png is missing.')
        # Visible source rectangle: the archer only (no shop phone/address).
        image = ImageReader(str(header))
        iw, ih = image.getSize()
        crop_x, crop_w, crop_h = 45, 255, 222
        scale_x, scale_y = width / crop_w, height / crop_h
        c.saveState()
        path = c.beginPath()
        # The source letterhead begins its blue tagline below the arrow.
        # This stepped clip includes the whole red arrow, excluding that text.
        points = [(45, 0), (300, 0), (300, 138), (235, 138), (235, 222), (45, 222)]
        for index, (px, py) in enumerate(points):
            method = path.moveTo if index == 0 else path.lineTo
            method(x+(px-crop_x)*scale_x, PAGE_H-y-py*scale_y)
        path.close()
        c.clipPath(path, stroke=0, fill=0)
        c.drawImage(image, x-crop_x*scale_x, PAGE_H-y-ih*scale_y, width=iw*scale_x, height=ih*scale_y, mask='auto')
        c.restoreState()

    # The optional note sits above the form; the item area absorbs its height.
    note = doc.get('top_note', '').strip()
    note_height = _paragraph(note, RIGHT-LEFT, 9)[1] + 3*mm if note else 0
    if note_height > 45*mm:
        raise ValueError('The top message is too long for the bill. Move some of it to the bottom notes.')
    top = 10*mm + note_height
    brand_top = top + 8*mm
    buyer_top = brand_top + 34*mm
    buyer_text = '\n'.join(filter(None, [doc['buyer'], doc['address']]))
    buyer_p, _ = _paragraph(buyer_text, 169*mm, 10)
    buyer_p.style.leading = 6.5*mm
    _, buyer_h = buyer_p.wrap(169*mm, PAGE_H*10)
    buyer_height = max(18*mm, buyer_h + 5*mm)
    if buyer_height > 60*mm:
        raise ValueError('The customer address is too long. Please shorten it to fit the bill.')
    meta_top = buyer_top + buyer_height
    table_top = meta_top + 20*mm
    grid_top = table_top + 9*mm
    grid_bottom = 225*mm
    grid_height = grid_bottom - grid_top
    if grid_height < 25*mm:
        raise ValueError('Please shorten the top message or customer address to leave room for the items.')
    columns = [10, 20, 118, 132, 148, 165, 192, 200]
    xs = [v*mm for v in columns]
    row_min = 9*mm
    row_data = []
    for i, product in enumerate(doc['items']):
        p, h = _paragraph(product['name'], xs[2]-xs[1]-4*mm, 10)
        height = max(row_min, h+4*mm)
        if height > grid_height:
            raise ValueError(f'Item {i+1} has a description too long for one page. Shorten it or split it into two items.')
        row_data.append((i, product, p, height))
    pages, current, used = [], [], 0
    for row in row_data:
        if current and used + row[3] > grid_height + .01:
            pages.append(current)
            current, used = [], 0
        current.append(row)
        used += row[3]
    pages.append(current)

    notes = doc.get('notes', '').strip()
    _, notes_height = _paragraph(notes, 122*mm, 8)
    notes_appendix = notes_height > 11*mm
    # Fourteen equal rows for a normal one-page bill, variable height for long descriptions.
    carried = Decimal('0.00')
    for page_index, page_rows in enumerate(pages):
        last = page_index == len(pages)-1
        if note:
            block(note, LEFT, 10*mm, RIGHT-LEFT, note_height-2*mm, 9)
        shade(LEFT, table_top, RIGHT-LEFT, grid_top-table_top)
        box(LEFT, top, RIGHT-LEFT, BOTTOM-top, .8)
        for y in [brand_top, buyer_top, meta_top, table_top, grid_top, grid_bottom, 267*mm]:
            line(LEFT, y, RIGHT, y)
        # Thin top strip: company GSTIN, document type, phone.
        text('GSTIN: '+company['gstin'], 12*mm, top+1.6*mm, 71*mm, 9)
        text(title, 86*mm, top+1.5*mm, 47*mm, 10.5, align='center')
        text('M: '+company['phone'], 137*mm, top+1.8*mm, 61*mm, 8.5, align='right')
        # Logo at left, the original red shop name across the main header.
        archer(12*mm, brand_top+3*mm, 23*mm, 28*mm)
        brand_right = 149*mm
        line(brand_right, brand_top, brand_right, buyer_top)
        text(company['name'], 36*mm, brand_top+1.2*mm, 110*mm, 26, True, color=RED)
        tagline = company.get('tagline', '')
        if tagline == 'Archery sport items, sports goods, gifts & novelties':
            tagline = 'Deals In : Archery Sport Items,\nSports Goods, Gifts & Novelties'
        block(tagline, 36*mm, brand_top+12*mm, 109*mm, 11*mm, 10.5, False, TA_CENTER)
        block(company['address'].upper(), 36*mm, brand_top+25*mm, 109*mm, 8*mm, 8.4, align=TA_CENTER, minimum=6.5)
        text('Quotation No.' if kind == 'Quotation' else 'Invoice No.', 152*mm, brand_top+9*mm, 26*mm, 9)
        if len(number) <= 8 and kind != 'Quotation':
            text(number, 179*mm, brand_top+8*mm, 18*mm, 12, align='right')
        else:
            text(number, 152*mm, brand_top+17*mm, 45*mm, 11)
        text('Date: '+date.fromisoformat(doc['date']).strftime('%d.%m.%Y'), 152*mm, brand_top+27*mm, 45*mm, 9)
        # Digital customer details stay clean inside the original field boxes.
        text('Buyer', 12*mm, buyer_top+3*mm, 16*mm, 9)
        buyer_p.drawOn(c, 29*mm, PAGE_H-buyer_top-2.5*mm-buyer_h)
        split = 116*mm
        line(split, meta_top, split, table_top)
        text('State', 12*mm, meta_top+4*mm, 16*mm, 9)
        block(doc['state'], 28*mm, meta_top+3*mm, 58*mm, 7*mm, 9)
        text('Code', 88*mm, meta_top+4*mm, 12*mm, 8.5)
        box(101*mm, meta_top+3*mm, 12*mm, 7*mm)
        text(doc['state_code'], 102*mm, meta_top+4*mm, 10*mm, 10, align='center')
        text('GSTIN', 12*mm, meta_top+13*mm, 17*mm, 9)
        box(29*mm, meta_top+11.5*mm, 84*mm, 7*mm)
        text(doc['buyer_gstin'], 31*mm, meta_top+12.8*mm, 80*mm, 10)
        text('Despatch Through', 118*mm, meta_top+3*mm, 38*mm, 8.5)
        block(doc['dispatch'], 157*mm, meta_top+2*mm, 40*mm, 8*mm, 8.5, minimum=6.5)
        text('Freight', 118*mm, meta_top+13*mm, 17*mm, 9)
        block(doc.get('freight', ''), 137*mm, meta_top+12*mm, 60*mm, 7*mm, 9)
        # Full-height ruled table, with separate rupees/paise columns.
        for x in xs[1:-1]:
            line(x, table_top if x != xs[-2] else table_top+4*mm, x, grid_bottom)
        text('S.No.', xs[0]+.5*mm, table_top+2.5*mm, 9*mm, 8, bold=True, align='center')
        text('DESCRIPTION OF GOODS', xs[1]+2*mm, table_top+2.5*mm, 94*mm, 9, bold=True, align='center')
        block('HSN\nCode', xs[2]+mm, table_top+.4*mm, 12*mm, 8*mm, 8, bold=True, align=TA_CENTER)
        for label, a, b in [('Qty.', 3, 4), ('RATE', 4, 5)]:
            text(label, xs[a]+mm, table_top+2.5*mm, xs[b]-xs[a]-2*mm, 9, bold=True, align='center')
        text('AMOUNT', xs[5], table_top+.4*mm, xs[-1]-xs[5], 8, bold=True, align='center')
        text('Rs.', xs[5]+2*mm, table_top+4.5*mm, 23*mm, 8, bold=True)
        text('Ps.', xs[6], table_top+4.5*mm, 8*mm, 8, bold=True, align='center')
        y = grid_top
        for i, product, paragraph, height in page_rows:
            text(i+1, xs[0]+mm, y+2*mm, 8*mm, 9, align='center')
            paragraph.drawOn(c, xs[1]+2*mm, PAGE_H-y-2*mm-paragraph.height)
            text(product['hsn'], xs[2]+.7*mm, y+2*mm, 12.6*mm, 7.5, align='center')
            text(f"{product['quantity']:g}", xs[3]+mm, y+2*mm, 14*mm, 9.5, align='center')
            text(f"{money(product['price']):.2f}", xs[4]+mm, y+2*mm, 15*mm, 9, align='right')
            whole, fraction = f'{line_amounts[i]:.2f}'.split('.')
            text(whole, xs[5]+mm, y+2*mm, 25*mm, 9.5, align='right')
            text(fraction, xs[6]+mm, y+2*mm, 6*mm, 9.5, align='right')
            y += height
            line(LEFT, y, RIGHT, y, .3)
        # Keep blank ruled rows down to the totals, just like the stationery.
        next_number = page_rows[-1][0]+2 if page_rows else 1
        blank_count = max(0, round((grid_bottom-y)/row_min))
        blank_height = (grid_bottom-y)/blank_count if blank_count else 0
        for _ in range(blank_count):
            text(next_number, xs[0]+mm, y+2*mm, 8*mm, 9, align='center')
            y += blank_height
            line(LEFT, y, RIGHT, y, .3)
            next_number += 1
        footer_split = 136*mm
        line(footer_split, grid_bottom, footer_split, BOTTOM)
        page_total = sum((line_amounts[row[0]] for row in page_rows), Decimal('0.00'))
        carried += page_total
        if last:
            text('Amount INR', 12*mm, grid_bottom+7*mm, 27*mm, 9)
            block(amount_in_words(grand), 40*mm, grid_bottom+5.5*mm, 93*mm, 18*mm, 10, minimum=7)
            text('BANK DETAILS', 12*mm, grid_bottom+26*mm, 122*mm, 8, align='center')
            block(company['bank'], 13*mm, grid_bottom+31*mm, 120*mm, 10*mm, 7.5, align=TA_CENTER, minimum=6)
            summary = [('TOTAL', subtotal)] + [(f"{key} {doc['taxes'][key]:g}%", value) for key,value in tax_amounts.items()] + [('G. TOTAL', grand)]
        else:
            block('Items continued on the next page.\nFinal taxes and grand total appear on the last item page.', 14*mm, grid_bottom+10*mm, 117*mm, 24*mm, 10)
            summary = [('PAGE TOTAL', page_total), ('CARRY FWD', carried)]
        summary_h = 42*mm / len(summary)
        for index, (label, value) in enumerate(summary):
            sy = grid_bottom + index*summary_h
            is_grand = last and index == len(summary)-1
            if is_grand:
                shade(footer_split+.5, sy+.3, RIGHT-footer_split-1, summary_h-.6)
            if index:
                line(footer_split, sy, RIGHT, sy)
            text(label, footer_split+2*mm, sy+summary_h/2-5, 26*mm, 9.5, bold=is_grand)
            whole, fraction = f'{value:.2f}'.split('.')
            text(whole, 166*mm, sy+summary_h/2-5, 25*mm, 10, bold=is_grand, align='right')
            text(fraction, 193*mm, sy+summary_h/2-5, 6*mm, 10, bold=is_grand, align='right')
        for x in [165*mm, 192*mm]:
            line(x, grid_bottom, x, 267*mm)
        if last:
            note_text = 'See attached notes and terms.' if notes_appendix else notes
            block(note_text, 13*mm, 271*mm, 117*mm, 11*mm, 8, minimum=7)
            text('E. & O.E.', 113*mm, 282*mm, 20*mm, 7, align='right')
            text('For '+company['name'], 138*mm, 269*mm, 60*mm, 8, align='center')
            if doc.get('signed') and (ROOT/'signature.png').exists():
                c.drawImage(str(ROOT/'signature.png'), 153*mm, PAGE_H-282*mm,
                            width=30*mm, height=10*mm, preserveAspectRatio=True, anchor='c',
                            mask=[220, 255, 220, 255, 220, 255])
            text('Signature', 173*mm, 283*mm, 24*mm, 8, align='right')
        else:
            text('Continued on next page', 13*mm, 275*mm, 120*mm, 9)
        text(f'{number}  |  Page {page_index+1} of {len(pages)}' + (' + notes' if notes_appendix else ''),
             LEFT, 290*mm, RIGHT-LEFT, 6.5, align='right')
        c.showPage()

    if notes_appendix:
        pending, _ = _paragraph(notes, 178*mm, 10)
        count = 1
        while pending:
            text(f'{title} {number} - NOTES & TERMS', 16*mm, 15*mm, 178*mm, 12)
            fragments = pending.split(178*mm, 245*mm)
            if not fragments:
                # A single paragraph already fitting the page returns itself from split.
                raise ValueError('The bottom notes could not be laid out. Please shorten them.')
            first = fragments[0]
            _, height = first.wrap(178*mm, 245*mm)
            first.drawOn(c, 16*mm, PAGE_H-28*mm-height)
            pending = fragments[1] if len(fragments)>1 else None
            text(f'{number} | Notes {count}', 16*mm, 285*mm, 178*mm, 7, align='right')
            count += 1
            c.showPage()
    c.save()
    return output.getvalue()
