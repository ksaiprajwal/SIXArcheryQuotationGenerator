import streamlit as st
from fpdf import FPDF
from PIL import Image
import io

st.set_page_config(page_title="Archery Quotation Generator", layout="centered")
st.title("SIX Archery Quotation Generator")

# --- Company Branding (actual images) ---
COMPANY_HEADER_PATH = "header.png"
SIGNATURE_PATH = "signature.png"

from datetime import datetime

def get_today():
    return datetime.now().strftime("%d %m %Y")

# --- Sidebar: Instructions ---
st.sidebar.header("Instructions")
st.sidebar.write("""
1. Enter your product details below. Add more rows as needed.
2. Fill in the address and any special instructions.
3. Click 'Generate Quotation PDF' to download your quotation letterhead with branding.
""")

# --- Product Table Input ---
st.subheader("Product Details")

if 'products' not in st.session_state:
    st.session_state['products'] = [{'name': '', 'quantity': 1, 'price': 0.0}]

products = st.session_state['products']

# Dynamic table for products
for i, product in enumerate(products):
    st.markdown(f"#### Product {i+1}")
    product['name'] = st.text_input(f"Product Name", value=product['name'], key=f"name_{i}")
    product['quantity'] = st.number_input(f"Quantity", min_value=1, value=product.get('quantity'), key=f"qty_{i}", placeholder="")
    product['price'] = st.number_input(f"Rate", min_value=0.0, value=product.get('price'), key=f"price_{i}", placeholder="")
    if st.button("Remove", key=f"remove_{i}"):
        products.pop(i)
        st.rerun()
    st.markdown("---")

if st.button("Add Product"):
    products.append({'name': '', 'quantity': None, 'price': None})
    st.rerun()

# --- Dynamic Total Calculation ---
valid_products = [p for p in products if p.get('quantity') and p.get('price')]
total = sum(p['quantity'] * p['price'] for p in valid_products)
tax = total * 0.05
grand_total = total + tax
st.markdown(f"**Current Total:** ₹{total:.2f}  ")
st.markdown(f"**Tax (5%):** ₹{tax:.2f}  ")
st.markdown(f"**Grand Total:** ₹{grand_total:.2f}")

# --- Address and Date ---
st.subheader("Recipient Address & Date")
address_col, date_col = st.columns([2, 1])
address = address_col.text_area("To (Recipient Address)")
today_str = get_today()
date_val = date_col.text_input("Date", value=today_str)

# --- Special Instructions ---
st.subheader("Special Instructions")
instructions = st.text_area(
    "Special Instructions (will appear at the bottom)",
    value=(
        "Transportation cost extra\n"
        "Hope you find our prices reasonable, expecting your valuable order.\n"
        "Our GSTN - 36APAPK0224P12Y\n"
        "SBI Account No. - 36003509100\n"
        "Account name - Shoot In X Archery\n"
        "IFSC code - SBIN0001342\n"
        "Branch - Osmanjung, M.J. Road, Hyderabad - 500195"
    )
)

# --- PDF Generation ---
def generate_pdf(products, address, date_val, instructions, header_path, signature_path):
    pdf = FPDF()
    pdf.add_page()
    # Company header image
    try:
        pdf.image(header_path, x=0, y=0, w=210)  # Full width for A4
        pdf.set_y(45)  # Start content just below the header image
    except Exception:
        pdf.set_font("Arial", 'B', 20)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(0, 30, '[Company Header Here]', ln=1, align='C')
        pdf.set_text_color(0, 0, 0)
    # Address and date row
    # Use smaller font for address/date
    pdf.set_font("Arial", '', 10)
    y_before = pdf.get_y()
    # Render address (left)
    pdf.set_xy(10, y_before)
    pdf.multi_cell(120, 6, f"To:\n{address}")
    y_after_address = pdf.get_y()
    # Render date (right, at y_before)
    pdf.set_xy(150, y_before)
    pdf.cell(40, 6, f"Date: {date_val}", ln=1, align='R')
    y_after_date = y_before + 6  # 6 is the height of the date cell
    # Set y to the lower of the two
    pdf.set_y(max(y_after_address, y_after_date) + 2)
    # Table header
    pdf.set_font("Arial", '', 10)
    pdf.set_fill_color(220, 220, 220)
    pdf.cell(12, 8, 'S.No', 1, 0, 'C', 1)
    pdf.cell(75, 8, 'Product', 1, 0, 'C', 1)
    pdf.cell(28, 8, 'Quantity', 1, 0, 'C', 1)
    pdf.cell(35, 8, 'Rate', 1, 0, 'C', 1)
    pdf.cell(35, 8, 'Total', 1, 1, 'C', 1)
    # Table rows
    pdf.set_fill_color(255, 255, 255)
    for idx, p in enumerate(products, 1):
        total = p['quantity'] * p['price']
        # Save the current position
        x_start = pdf.get_x()
        y_start = pdf.get_y()
        # Calculate height needed for product name
        product_name_width = 75
        line_height = 8
        # Estimate number of lines for product name
        pdf.set_font("Arial", '', 10)
        product_name_lines = pdf.multi_cell(product_name_width, line_height, p['name'], border=0, align='L', split_only=True)
        n_lines = len(product_name_lines)
        row_height = line_height * n_lines
        # S.No
        pdf.set_xy(x_start, y_start)
        pdf.cell(12, row_height, str(idx), 1, 0, 'C')
        # Product Name
        pdf.set_xy(x_start + 12, y_start)
        pdf.multi_cell(product_name_width, line_height, p['name'], border=1, align='L')
        # Move to right for rest of row
        x_next = x_start + 12 + product_name_width
        y_next = y_start
        pdf.set_xy(x_next, y_next)
        pdf.cell(28, row_height, str(p['quantity']), 1, 0, 'L')
        pdf.cell(35, row_height, f"{p['price']:.2f}", 1, 0, 'L')
        pdf.cell(35, row_height, f"{total:.2f}", 1, 0, 'L')
        pdf.ln(row_height)
    # Total, Tax, Grand Total
    total = sum(p['quantity'] * p['price'] for p in products)
    tax = total * 0.05
    grand_total = total + tax
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(150, 8, 'Total', 1, 0, 'R')
    pdf.cell(35, 8, f"{total:.2f}", 1, 1, 'L')
    pdf.set_font("Arial", '', 10)
    pdf.cell(150, 8, 'Tax (5%)', 1, 0, 'R')
    pdf.cell(35, 8, f"{tax:.2f}", 1, 1, 'L')
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(150, 8, 'Grand Total', 1, 0, 'R')
    pdf.cell(35, 8, f"{grand_total:.2f}", 1, 1, 'L')
    pdf.ln(8)
    # Special instructions
    pdf.set_font("Arial", '', 10)
    pdf.multi_cell(0, 5, instructions)
    pdf.ln(5)
    # Regards and name above signature
    pdf.ln(5)
    pdf.set_font("Arial", '', 10)
    pdf.cell(0, 6, "Regards,", ln=1, align='L')
    pdf.cell(0, 6, "Praveen Kumar Kongalla", ln=1, align='L')
    pdf.ln(2)
    # Signature (left and right)
    y_sig = pdf.get_y()
    try:
        pdf.image(signature_path, x=25, y=y_sig, w=25)  # Left
    except Exception:
        pdf.set_font("Arial", 'I', 12)
        pdf.set_text_color(200, 200, 200)
        pdf.cell(0, 10, '[Signature Here]', ln=1, align='R')
        pdf.set_text_color(0, 0, 0)
    return pdf.output(dest='S').encode('latin1')

# --- Generate PDF Button ---
if st.button("Generate Quotation PDF"):
    pdf_bytes = generate_pdf(products, address, date_val, instructions, COMPANY_HEADER_PATH, SIGNATURE_PATH)
    st.success("Quotation PDF generated!")
    st.download_button(
        label="Download Quotation PDF",
        data=pdf_bytes,
        file_name="quotation.pdf",
        mime="application/pdf"
    )

st.write("\n---\nMade with ❤️ for SIX Archery.")
