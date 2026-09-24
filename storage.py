"""Private PostgreSQL history; explicit SQLite mode only for local development.

PDF bytes and editable source are saved in a single transaction. Optimistic
versions prevent an old browser tab from overwriting a newer saved edit.
"""
from contextlib import contextmanager
import json
import sqlite3
from copy import deepcopy
from datetime import datetime, timezone

class ConflictError(Exception):
    pass

class Store:
    def __init__(self, database_url='', local_path=None):
        self.url, self.local_path = database_url, local_path
        if not database_url and not local_path:
            raise ValueError('Configure DATABASE_URL to enable saved documents.')
        with self.connect() as con:
            cur = con.cursor()
            blob = 'BYTEA' if self.url else 'BLOB'
            cur.execute(f'''CREATE TABLE IF NOT EXISTS documents (
                id TEXT PRIMARY KEY, number TEXT UNIQUE NOT NULL, version INTEGER NOT NULL,
                updated_at TEXT NOT NULL, payload TEXT NOT NULL, buyer TEXT NOT NULL, kind TEXT NOT NULL)''')
            cur.execute(f'''CREATE TABLE IF NOT EXISTS revisions (
                document_id TEXT NOT NULL, version INTEGER NOT NULL,
                updated_at TEXT NOT NULL, payload TEXT NOT NULL, pdf {blob} NOT NULL,
                PRIMARY KEY (document_id, version))''')
            cur.execute('CREATE INDEX IF NOT EXISTS documents_updated ON documents(updated_at DESC)')
            cur.execute('CREATE INDEX IF NOT EXISTS documents_kind_updated ON documents(kind, updated_at DESC)')
            cur.execute('CREATE INDEX IF NOT EXISTS documents_buyer ON documents(buyer)')
            con.commit()

    @contextmanager
    def connect(self):
        if self.url:
            import psycopg
            con = psycopg.connect(self.url, connect_timeout=10)
        else:
            con = sqlite3.connect(self.local_path, timeout=10)
        try:
            with con:
                yield con
        finally:
            con.close()

    def sql(self, query):
        return query.replace('?', '%s') if self.url else query

    def save(self, doc, renderer):
        from billing import validate
        validate(doc)
        saved = deepcopy(doc)
        saved['version'] += 1
        # Stable unique identifiers; never rely on a race-prone MAX(number)+1.
        if not saved['number']:
            prefix = 'Q' if saved['kind'] == 'Quotation' else 'B'
            saved['number'] = f"{prefix}-{saved['date'][2:4]}-{saved['id'][:10].upper()}"
        pdf = renderer(saved)
        payload = json.dumps(saved, ensure_ascii=False)
        now = datetime.now(timezone.utc).isoformat()
        with self.connect() as con:
            cur = con.cursor()
            if doc['version'] == 0:
                cur.execute(self.sql('INSERT INTO documents VALUES (?, ?, ?, ?, ?, ?, ?)'),
                            (saved['id'], saved['number'], saved['version'], now, payload, saved['buyer'], saved['kind']))
            else:
                cur.execute(self.sql('UPDATE documents SET version=?, updated_at=?, payload=?, buyer=?, kind=? WHERE id=? AND version=?'),
                            (saved['version'], now, payload, saved['buyer'], saved['kind'], saved['id'], doc['version']))
                if cur.rowcount != 1:
                    raise ConflictError('A newer edit is already saved. Reopen this document from Saved documents before editing.')
            cur.execute(self.sql('INSERT INTO revisions VALUES (?, ?, ?, ?, ?)'),
                        (saved['id'], saved['version'], now, payload, pdf))
            con.commit()
        return saved, pdf

    def list(self, query='', kind='All', page=0, page_size=20):
        # SQL filtering/pagination; no PDF data in history queries.
        clauses, params = [], []
        if query:
            clauses.append("(LOWER(buyer) LIKE ? ESCAPE '!' OR LOWER(number) LIKE ? ESCAPE '!')")
            safe = query.lower().replace('!', '!!').replace('%', '!%').replace('_', '!_')
            params.extend(['%' + safe + '%'] * 2)
        if kind != 'All':
            clauses.append('kind=?')
            params.append(kind)
        where = (' WHERE ' + ' AND '.join(clauses)) if clauses else ''
        with self.connect() as con:
            rows = con.execute(self.sql('SELECT payload, updated_at FROM documents' + where +
                ' ORDER BY updated_at DESC, id LIMIT ? OFFSET ?'), (*params, page_size, page * page_size)).fetchall()
        return [(json.loads(payload), updated) for payload, updated in rows]

    def versions(self, id):
        with self.connect() as con:
            return con.execute(self.sql('SELECT version, updated_at FROM revisions WHERE document_id=? ORDER BY version DESC'), (id,)).fetchall()

    def get(self, id, version=None):
        with self.connect() as con:
            if version is None:
                row = con.execute(self.sql('SELECT d.payload, r.pdf FROM documents d JOIN revisions r ON r.document_id=d.id AND r.version=d.version WHERE d.id=?'), (id,)).fetchone()
            else:
                row = con.execute(self.sql('SELECT payload, pdf FROM revisions WHERE document_id=? AND version=?'), (id, version)).fetchone()
        if not row:
            raise ValueError('This saved document could not be found.')
        return json.loads(row[0]), bytes(row[1])
