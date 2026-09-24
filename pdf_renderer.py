"""Printable A4 documents with wrapping cells and repeated table headings."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, Image
from billing import totals

RED = colors.HexColor('#9F2435')
INK = colors.HexColor('#202936')
MUTED = colors.HexColor('#596474')
LINE = colors.HexColor('#DDE1E6')
ROOT = Path(__file__).parent
pdfmetrics.registerFont(TTFont('DejaVu', str(ROOT / 'assets/DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DejaVu-Bold', str(ROOT / 'assets/DejaVuSans-Bold.ttf')))


def generate_pdf(doc):
    stream = BytesIO()
    styles = {
        'body': ParagraphStyle('body', fontName='DejaVu', fontSize=9, leading=13, textColor=INK),
        'small': ParagraphStyle('small', fontName='DejaVu', fontSize=8, leading=11, textColor=MUTED),
        'title': ParagraphStyle('title', fontName='DejaVu-Bold', fontSize=22, leading=27, textColor=RED),
        'label': ParagraphStyle('label', fontName='DejaVu-Bold', fontSize=9, leading=13, textColor=RED),
        'right': ParagraphStyle('right', fontName='DejaVu', fontSize=9, leading=13, alignment=TA_RIGHT),
        'head': ParagraphStyle('head', fontName='DejaVu-Bold', fontSize=8, leading=11, textColor=colors.white),
    }
    def p(text, style='body'):
        return Paragraph(escape(str(text)).replace('\n', '<br/>'), styles[style])
    def amount(value):
        return f'{value:,.2f}'
    company = doc['company']
    story = [p(company['name'], 'title'), p(company['tagline'], 'small'), Spacer(1, 3*mm),
             p(company['address'], 'small'), p(f"Phone: {company['phone']}  |  GSTIN: {company['gstin']}", 'small'), Spacer(1, 6*mm)]
    title = 'QUOTATION' if doc['kind'] == 'Quotation' else ('TAX INVOICE' if doc['taxes'] else 'BILL')
    band = Table([[p(title, 'head'), p(f"{doc['number'] or 'PREVIEW'}   |   {doc['date']}", 'head')]], colWidths=[77*mm, 105*mm])
    band.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),RED),('TOPPADDING',(0,0),(-1,-1),10),('BOTTOMPADDING',(0,0),(-1,-1),10)]))
    story += [band, Spacer(1, 5*mm)]
    if doc['top_note'].strip():
        story += [p(doc['top_note'], 'label'), Spacer(1, 4*mm)]
    buyer = '\n'.join(filter(None, [doc['buyer'], doc['address'],
        f"GSTIN: {doc['buyer_gstin']}" if doc['buyer_gstin'] else '',
        ' | '.join(filter(None, [doc['state'], f"State code: {doc['state_code']}" if doc['state_code'] else '']))]))
    story += [p('TO' if doc['kind'] == 'Quotation' else 'BILL TO', 'label'), p(buyer)]
    if doc['dispatch']:
        story.append(p('Dispatch through: ' + doc['dispatch'], 'small'))
    story.append(Spacer(1, 5*mm))
    lines, subtotal, taxes, grand = totals(doc)
    rows = [[p(s, 'head') for s in ['#', 'DESCRIPTION OF GOODS', 'HSN', 'QTY', 'RATE (INR)', 'AMOUNT (INR)']]]
    for i, (product, line) in enumerate(zip(doc['items'], lines), 1):
        rows.append([p(i, 'small'), p(product['name']), p(product['hsn'], 'small'),
                     p(f"{product['quantity']:g}", 'right'), p(amount(product['price']), 'right'), p(amount(line), 'right')])
    table = Table(rows, colWidths=[10*mm, 77*mm, 20*mm, 15*mm, 29*mm, 31*mm], repeatRows=1, hAlign='CENTER')
    table.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),INK), ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white, colors.HexColor('#F6F7F9')]),
        ('VALIGN',(0,0),(-1,-1),'TOP'), ('TOPPADDING',(0,0),(-1,-1),9), ('BOTTOMPADDING',(0,0),(-1,-1),9),
        ('LINEBELOW',(0,0),(-1,0),0.5,INK), ('LINEBELOW',(0,1),(-1,-1),0.4,LINE),
    ]))
    story += [table, Spacer(1, 4*mm)]
    summary = [[p('Subtotal'), p(amount(subtotal), 'right')]]
    for name, tax in taxes.items():
        summary.append([p(f"{name} ({doc['taxes'][name]:g}%)"), p(amount(tax), 'right')])
    summary.append([p('TOTAL (INR)', 'label'), p(amount(grand), 'right')])
    t = Table(summary, colWidths=[55*mm, 40*mm], hAlign='RIGHT')
    t.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6),
                          ('BACKGROUND',(0,-1),(-1,-1),colors.HexColor('#FAEDEF')),('LINEABOVE',(0,-1),(-1,-1),1,RED)]))
    story += [KeepTogether(t), Spacer(1, 7*mm)]
    if doc['notes'].strip():
        story += [p('NOTES & TERMS', 'label'), p(doc['notes']), Spacer(1, 5*mm)]
    closing = [p('BANK DETAILS', 'label'), p(company['bank'], 'small'), Spacer(1, 5*mm),
               p('For ' + company['name'], 'label')]
    if doc['signed'] and (ROOT / 'signature.png').exists():
        im = Image(str(ROOT / 'signature.png'), width=30*mm, height=15*mm, kind='proportional')
        im.hAlign = 'LEFT'
        closing.append(im)
    else:
        closing.append(Spacer(1, 12*mm))
    closing.append(p('Authorised signatory', 'small'))
    story.append(KeepTogether(closing))
    def footer(canvas, document):
        canvas.setStrokeColor(LINE)
        canvas.line(14*mm, 15*mm, 196*mm, 15*mm)
        canvas.setFont('DejaVu', 8)
        canvas.setFillColor(MUTED)
        canvas.drawString(14*mm, 10*mm, f"{doc['number'] or 'PREVIEW'} | {title}")
        canvas.drawRightString(196*mm, 10*mm, f'Page {document.page}')
    pdf = SimpleDocTemplate(stream, pagesize=(210*mm,297*mm), rightMargin=14*mm, leftMargin=14*mm,
                            topMargin=14*mm, bottomMargin=22*mm, title=f"{title} {doc['number']}", author=company['name'])
    pdf.build(story, onFirstPage=footer, onLaterPages=footer)
    return stream.getvalue()
