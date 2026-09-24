# Shoot In X Archery — bills and quotations

A phone-friendly Streamlit app with editable saved documents and professionally formatted A4 PDFs.

## What changed

- Large labelled controls and a three-section form: customer, items, tax/notes.
- Bills and quotations, customer search, 20-record history pages, reopen/edit,
  copy-as-new and quotation-to-bill conversion.
- Save & create PDF stores the editable source and the exact PDF together.
  Every subsequent save preserves the earlier version and PDF.
- CGST 6% + SGST 6%, IGST 12%, no GST, or individually selected rows. Rates
  remain editable. IGST cannot be combined with CGST/SGST. These defaults are
  the owner's requested values, not an automated tax determination.
- Optional message inside the buyer box, HSN, buyer GSTIN, state/code, dispatch,
  notes and signature. Unfilled customer/delivery fields and their boxes are omitted.
- A4 PDFs matching the printed shop bill: original archer at left, red shop
  name, thin outlined boxes, 14 ruled rows, rupees/paise columns, amount in Indian
  words, bank details and a bottom-right signature. Long items wrap; additional
  pages repeat the form and carry forward totals. Long notes use an appendix.
  The formal finish uses one font family, light charcoal rules, subtle grey
  table-header/grand-total shading, clean digital fields and consistent alignment.
- Optional freight annotation (informational; not added to the amount).
- Only actual items receive serial numbers. Items continue on new pages as needed,
  with final taxes and grand total after the last item. Tax selection uses three
  checkboxes with disabled rates for unselected taxes; IGST clears CGST/SGST and
  selecting either of those clears IGST.
- Decimal calculations and optimistic version checks prevent lost concurrent edits.

## Free-first deployment: existing Streamlit + Neon PostgreSQL

Keep the existing Streamlit entry point `quotation_app.py`. No separate API server,
Redis, paid domain or PDF service is needed. A PostgreSQL provider such as Neon
can run on its free plan; check current quotas at https://neon.com/pricing.
Free services may sleep and the first request can take longer. Monitor database
storage: PDFs and retained revisions count toward it. Never use local SQLite as
cloud persistence. No provider account or billable resource is provisioned by this code.

1. Create a free Neon project and copy its **pooled PostgreSQL connection string**
   (including `sslmode=require`). Use a region near the app host. An existing
   private PostgreSQL database also works.
2. In Streamlit Community Cloud, open the app's **Settings → Secrets** and set:

   ```toml
   DATABASE_URL = "postgresql://USER:PASSWORD@HOST/DATABASE?sslmode=require"
   COMPANY_GSTIN = "36APAPK0224P12Y"
   ```

   `APP_PASSWORD` is no longer used. The app opens directly without a login.
   Anyone who can open the app can view, edit and download its saved customer
   documents. If you later share its URL, consider enabling private-app access
   in Streamlit or adding authentication. Do not commit database credentials to
   GitHub.
3. The existing Streamlit app uses `quotation_app.py` and installs dependencies
   from `requirements.txt`; tables and indexes are created on first connection.
4. The shop GSTIN defaults to `36APAPK0224P12Y`. Set bank/contact details in
   private settings. The buyer GSTIN is a separate optional field. Shop details
   are editable under the collapsed shop section;
   configure permanent defaults with `COMPANY_NAME`, `COMPANY_ADDRESS`,
   `COMPANY_PHONE`, `COMPANY_GSTIN`, `COMPANY_BANK`, and `COMPANY_TAGLINE` secrets.
5. Create a test quotation, save it, reopen it on a second session, edit it, and
   check both PDF versions. Keep copies of important final bills and schedule
   database backups using the provider or `pg_dump` (free-tier retention varies).

Saved data is in the private database, **never in this public GitHub repository**.
The server alone uses the database credential. If using Supabase instead of Neon,
use a private non-exposed schema/role or disable Data API access to these tables;
this app uses a server connection, not Supabase's browser-facing API.

## How the history stays responsive

Primary keys provide direct retrieval of a document/version. Indexes support
recent-document and document-type ordering. Search runs in SQL, and only 20
editable documents are fetched at a time; PDF bytes are loaded on demand.
Customer substring search uses a scan; at substantially larger scale, add a
PostgreSQL trigram index before adding a cache. The cached resource is a Store
configuration, not an open connection or stale query result. Use the provider's
pooled endpoint for short database connections.

One transaction saves the source, PDF and revision. If another tab already saved
a newer version, the app asks the user to reopen it rather than overwrite it.
A network disconnect immediately after commit can make save confirmation ambiguous;
check history before retrying. Current implementation retains all revisions; each PDF is stored only once,
in its revision row. Monitor storage as the history grows.

## Local development and tests

```bash
python -m pip install -r requirements.txt
LOCAL_DEMO=true python -m streamlit run quotation_app.py
python -m pip install -r requirements-dev.txt
python -m pytest tests -q
```

`LOCAL_DEMO=true` is explicitly local-only: it creates ignored `local-demo.sqlite`.
**Do not enable it in a hosted deployment.** Without database configuration,
production mode stops with setup guidance rather than silently using temporary storage.

The sample generator in `examples/` uses fictional details; generated PDFs are
ignored by git. Customer-facing samples can use private shop settings. Font
files in `assets/` include their redistribution license. Fonts support English
and common symbols; Indian-script shaping and arbitrary emoji are not supported.
Existing PDFs from the old app cannot be automatically reopened as structured
records; enter/copy their details once to add them to the new history.

## Useful next improvements

- Saved customer and product shortcuts to avoid repeated typing.
- Automatic recovery of unfinished drafts after browser refresh.
- A familiar sequential invoice series, configured with the shop's accountant.
- Paid/unpaid status and a monthly export for bookkeeping.
- A one-tap backup download and tested restore flow.

No automatic WhatsApp sending is included: download the PDF and use the phone's
Share menu. No deletion button is exposed, reducing accidental loss.
