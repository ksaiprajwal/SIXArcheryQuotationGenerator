from copy import deepcopy
import hmac
import os
from datetime import date
from pathlib import Path
import streamlit as st
from billing import DEFAULT_COMPANY, new_document, item, totals, validate, duplicate
from storage import Store, ConflictError
from pdf_renderer import generate_pdf

st.set_page_config(page_title='Shoot In X | Bills & Quotations', page_icon='🏹', layout='centered')
st.markdown('''<style>
.block-container {max-width:850px;padding-top:2rem;padding-bottom:5rem}
h1 {font-size:2rem!important;letter-spacing:-.04em}
h2 {font-size:1.4rem!important} h3 {font-size:1.15rem!important}
.stButton button,.stDownloadButton button {min-height:50px;font-size:1rem;border-radius:12px}
input,textarea {font-size:17px!important} label p {font-size:16px!important}
[data-testid="stMetricValue"] {font-size:1.8rem}
@media(max-width:600px) {.block-container {padding:1rem 1rem 4rem} h1 {font-size:1.65rem!important}}
</style>''', unsafe_allow_html=True)

def setting(name, default=''):
    try:
        return st.secrets.get(name, os.environ.get(name, default))
    except FileNotFoundError:
        return os.environ.get(name, default)

local = setting('LOCAL_DEMO', 'false').lower() == 'true'
password = setting('APP_PASSWORD')
st.title('Shoot In X Archery')
st.caption('Bills & quotations, made simple.')
if not local:
    if not password or len(password) < 12:
        st.info('One-time setup needed: add DATABASE_URL and a strong APP_PASSWORD in Streamlit settings. See the README in GitHub.')
        st.stop()
    if not st.session_state.get('authenticated'):
        with st.form('login'):
            entered = st.text_input('Shop password', type='password')
            if st.form_submit_button('Open my documents', type='primary', use_container_width=True):
                if hmac.compare_digest(entered.encode(), password.encode()):
                    st.session_state.authenticated = True
                    st.rerun()
                else:
                    st.error('Incorrect password. Please try again.')
        st.stop()
else:
    st.warning('Local demo: saved documents are on this computer only. Do not use this mode on Streamlit Cloud.')

@st.cache_resource
def connect_store(url, path):
    return Store(url, path)

try:
    store = connect_store(setting('DATABASE_URL'), str(Path(__file__).parent / 'local-demo.sqlite') if local else None)
except Exception:
    st.error('Saved documents are unavailable. Check the database connection in Streamlit settings, then retry. No data has been saved.')
    if st.button('Retry connection'):
        connect_store.clear()
        st.rerun()
    st.stop()

company = dict(DEFAULT_COMPANY)
for key in company:
    company[key] = setting('COMPANY_' + key.upper(), company[key])
if 'doc' not in st.session_state:
    st.session_state.doc = new_document(company=company)
    st.session_state.edit_epoch = 0


def open_doc(doc):
    st.session_state.doc = doc
    st.session_state.edit_epoch += 1
    st.session_state.pop('download', None)
    st.session_state.screen = 'Create / edit'

@st.dialog('Start a new document?')
def start_new(kind, source=None):
    st.write('Your current unsaved edits will be replaced. Save them first if you need them.')
    if st.button('Continue', type='primary', use_container_width=True):
        open_doc(source or new_document(kind, company))
        st.rerun()

if 'pending_doc' in st.session_state:
    open_doc(st.session_state.pop('pending_doc'))

left, right = st.columns(2)
if left.button('＋ New quotation', use_container_width=True):
    start_new('Quotation')
if right.button('＋ New bill', use_container_width=True):
    start_new('Bill')
screen = st.radio('Workspace', ['Create / edit', 'Saved documents'], horizontal=True, key='screen', label_visibility='collapsed')

if screen == 'Saved documents':
    st.subheader('Saved documents')
    query = st.text_input('Search customer or document number', placeholder='Customer name or Q-2026…')
    kind = st.selectbox('Show', ['All', 'Quotation', 'Bill'])
    search_key = (query, kind)
    if st.session_state.get('search_key') != search_key:
        st.session_state.history_page = 0
        st.session_state.search_key = search_key
    page = st.session_state.get('history_page', 0)
    try:
        records = store.list(query, kind, page)
        if not records:
            st.info('No saved documents here yet.' if not query else 'No matching documents found.')
        for saved, updated in records:
            with st.container(border=True):
                st.subheader(saved['buyer'])
                st.write(f"{saved['kind']} · {saved['number']}")
                st.caption(f"{saved['date']} · Version {saved['version']} · INR {totals(saved)[3]:,.2f}")
                if st.button('Open / edit', key='open'+saved['id'], use_container_width=True):
                    # Callback runs before the navigation widget is instantiated on the next run.
                    st.session_state.pending_doc = store.get(saved['id'])[0]
                    st.rerun()
                if st.button('Copy as new', key='copy'+saved['id']):
                    st.session_state.pending_doc = duplicate(saved)
                    st.rerun()
                if saved['kind'] == 'Quotation' and st.button('Convert to bill', key='bill'+saved['id']):
                    st.session_state.pending_doc = duplicate(saved, 'Bill')
                    st.rerun()
                with st.expander('Download PDF / earlier versions'):
                    # Streamlit expanders run even when closed; gate PDF fetch behind a button.
                    if st.button('Load saved PDFs', key='load'+saved['id']):
                        st.session_state['versions'+saved['id']] = store.versions(saved['id'])
                    versions = st.session_state.get('versions'+saved['id'], [])
                    if versions:
                        version = st.selectbox('Version', [v[0] for v in versions], key='version'+saved['id'])
                        old, pdf = store.get(saved['id'], version)
                        st.download_button('Download PDF', pdf, f"{old['number']}-v{version}.pdf", 'application/pdf', key='pdf'+saved['id'])
        prev, nxt = st.columns(2)
        if prev.button('Previous', disabled=page == 0, use_container_width=True):
            st.session_state.history_page = page - 1
            st.rerun()
        if nxt.button('Next', disabled=len(records) < 20, use_container_width=True):
            st.session_state.history_page = page + 1
            st.rerun()
    except Exception:
        st.error('Could not load saved documents. Please retry in a moment.')
    st.stop()

doc = st.session_state.doc
doc.setdefault('freight', '')
prefix = f"{doc['id']}-{st.session_state.edit_epoch}-"
def text(label, field, area=False, **kwargs):
    fn = st.text_area if area else st.text_input
    doc[field] = fn(label, value=doc[field], key=prefix+field, **kwargs)

st.subheader(f"{doc['kind']} · {doc['number'] or 'New document'}")
st.caption('Changes are saved when you tap Save & create PDF below.')
st.markdown('### 1. Customer')
text('Customer name *', 'buyer', max_chars=150)
text('Customer address', 'address', area=True, max_chars=1500)
doc['date'] = st.date_input('Date', date.fromisoformat(doc['date']), key=prefix+'date').isoformat()
with st.expander('Customer GST & delivery details (optional)'):
    text('Customer GSTIN', 'buyer_gstin', max_chars=15)
    text('State', 'state', max_chars=80)
    text('State code', 'state_code', max_chars=2)
    text('Dispatch through', 'dispatch', max_chars=150)
    text('Freight note (not added to total)', 'freight', max_chars=100)

st.markdown('### 2. Items')
for index, product in enumerate(doc['items']):
    key = prefix+product['id']
    with st.container(border=True):
        st.markdown(f'**Item {index+1}**')
        product['name'] = st.text_input('Item name *', product['name'], key=key+'name', max_chars=800)
        cols = st.columns(2)
        product['quantity'] = cols[0].number_input('Quantity', min_value=0.01, max_value=1000000.0, value=float(product['quantity']), step=1.0, key=key+'quantity')
        product['price'] = cols[1].number_input('Rate (INR)', min_value=0.0, max_value=100000000.0, value=float(product['price']), step=10.0, key=key+'price')
        st.caption(f"Item total: INR {totals({'items':[product], 'taxes':{}})[1]:,.2f}")
        product['hsn'] = st.text_input('HSN code (optional)', product['hsn'], key=key+'hsn', max_chars=12)
        if st.button('Remove this item', key=key+'remove', disabled=len(doc['items']) == 1):
            doc['items'].pop(index)
            st.session_state.pop('download', None)
            st.rerun()
if st.button('＋ Add another item', use_container_width=True):
    doc['items'].append(item())
    st.session_state.pop('download', None)
    st.rerun()

st.markdown('### 3. Tax & notes')
modes = ['CGST + SGST', 'IGST', 'No GST', 'Choose individually']
initial = 1 if 'IGST' in doc['taxes'] else (0 if set(doc['taxes']) == {'CGST','SGST'} else (2 if not doc['taxes'] else 3))
mode = st.selectbox('Tax to show on this document', modes, index=initial, key=prefix+'taxmode')
if mode == 'Choose individually':
    choices = st.multiselect('Tax rows', ['CGST','SGST','IGST'], default=list(doc['taxes']), key=prefix+'taxchoices')
else:
    choices = {'CGST + SGST':['CGST','SGST'], 'IGST':['IGST'], 'No GST':[]}[mode]
rates = {}
for name in choices:
    rates[name] = st.number_input(f'{name} rate (%)', min_value=0.0, max_value=100.0,
        value=float(doc['taxes'].get(name, 12.0 if name == 'IGST' else 6.0)), step=0.5, key=prefix+name)
doc['taxes'] = rates
if 'IGST' in rates and ('CGST' in rates or 'SGST' in rates):
    st.error('Select IGST or CGST / SGST. Remove the conflicting tax rows before saving.')
text('Message at the top (optional)', 'top_note', area=True, max_chars=1000, placeholder='For example: Kind attention: Coach Sharma')
with st.expander('Bottom notes & signature'):
    text('Notes / terms', 'notes', area=True, max_chars=3000)
    doc['signed'] = st.checkbox('Include saved signature', value=doc['signed'], key=prefix+'signed')
with st.expander('Shop & bank details on this document'):
    st.caption('Shop GSTIN is separate from customer GSTIN. Shop details come from private settings; saved documents retain their own copy.')
    for field, label in [('name','Shop name'),('tagline','Tagline'),('address','Shop address'),('phone','Phone'),('gstin','Shop GSTIN'),('bank','Bank details')]:
        doc['company'][field] = st.text_area(label, doc['company'][field], key=prefix+'company'+field, max_chars=500) if field in ('address','bank') else st.text_input(label, doc['company'][field], key=prefix+'company'+field, max_chars=150)
_, subtotal, taxes, grand = totals(doc)
with st.container(border=True):
    st.write(f'Subtotal: INR {subtotal:,.2f}')
    for name, value in taxes.items():
        st.write(f'{name} ({rates[name]:g}%): INR {value:,.2f}')
    st.metric('Total amount', f'INR {grand:,.2f}')
if st.button('Save & create PDF', type='primary', use_container_width=True):
    try:
        validate(doc)
        with st.spinner('Saving your document…'):
            saved, pdf = store.save(doc, generate_pdf)
        st.session_state.doc = doc = saved
        st.session_state.download = (deepcopy(saved), pdf)
        st.success(f"Saved as {saved['number']}. You can reopen it in Saved documents.")
    except (ValueError, ConflictError) as exc:
        st.error(str(exc))
    except Exception:
        st.error('Could not confirm the save. Your entries are still here. Check Saved documents before retrying if the connection dropped.')
if 'download' in st.session_state:
    saved, pdf = st.session_state.download
    if saved == doc:
        st.download_button('Download PDF', pdf, f"{saved['number']}.pdf", 'application/pdf', use_container_width=True)
        st.caption('On your phone, open the downloaded PDF and use Share to send it on WhatsApp.')
    else:
        st.info('You have new changes. Tap Save & create PDF to update the saved copy.')
