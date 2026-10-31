"""
طبقة البيانات الهجينة لمنظومة الإتقان:
تدعم محرك SQLite محلياً ومحرك PostgreSQL سحابياً (Supabase) بشكل شفاف وتلقائي.
"""
import os
import sqlite3
from contextlib import contextmanager

from config import DATA_DIR, DB_PATH, DATABASE_URL

# فحص ما إذا كنا في وضع السحابة (PostgreSQL) أو الوضع المحلي (SQLite)
IS_PG = bool(DATABASE_URL)

# ---------------- مخطط الجداول (Schemas) ----------------
SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id       INTEGER PRIMARY KEY AUTOINCREMENT,
    code     TEXT    NOT NULL UNIQUE,
    name     TEXT    NOT NULL,
    brand    TEXT    NOT NULL DEFAULT 'Generic',
    main_cat TEXT    NOT NULL DEFAULT 'غير مصنف',
    sub_cat  TEXT    NOT NULL DEFAULT 'غير مصنف',
    price    REAL    NOT NULL DEFAULT 0 CHECK (price >= 0),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0)
);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    role       TEXT NOT NULL CHECK(role IN ('admin', 'developer', 'staff')),
    name       TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

PG_SCHEMA = """
CREATE TABLE IF NOT EXISTS products (
    id       SERIAL PRIMARY KEY,
    code     TEXT    NOT NULL UNIQUE,
    name     TEXT    NOT NULL,
    brand    TEXT    NOT NULL DEFAULT 'Generic',
    main_cat TEXT    NOT NULL DEFAULT 'غير مصنف',
    sub_cat  TEXT    NOT NULL DEFAULT 'غير مصنف',
    price    NUMERIC(12, 2) NOT NULL DEFAULT 0 CHECK (price >= 0),
    quantity INTEGER NOT NULL DEFAULT 0 CHECK (quantity >= 0)
);
CREATE INDEX IF NOT EXISTS idx_products_brand ON products(brand);

CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    id         SERIAL PRIMARY KEY,
    username   TEXT UNIQUE NOT NULL,
    password   TEXT NOT NULL,
    role       TEXT NOT NULL CHECK(role IN ('admin', 'developer', 'staff')),
    name       TEXT NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

_COLUMNS = 'id, code, name, brand, main_cat, sub_cat, price, quantity'


class DuplicateCodeError(Exception):
    """رقم الصنف مستخدم لمنتج آخر."""


# ---------------- إدارة الاتصال ----------------
def _connect_sqlite():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=15)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA foreign_keys = ON')
    return conn


def _connect_pg():
    import psycopg2
    from psycopg2.extras import RealDictCursor
    conn = psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor, connect_timeout=10)
    return conn


@contextmanager
def get_db():
    """مدير السياق: يضمن إنهاء المعاملة وإغلاق الاتصال بأمان تام على كلا المحركين."""
    if IS_PG:
        conn = _connect_pg()
    else:
        conn = _connect_sqlite()

    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _format_query(sql):
    """مواءمة صياغة المعاملات بين SQLite (?) و PostgreSQL (%s)."""
    if IS_PG:
        return sql.replace('?', '%s').replace('COLLATE NOCASE', '')
    return sql


def _raise_if_duplicate(exc):
    msg = str(exc).upper()
    if 'UNIQUE' in msg or 'DUPLICATE' in msg or '23505' in msg:
        raise DuplicateCodeError() from exc
    raise exc


# ---------------- تهيئة المخطط ----------------
def init_schema():
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(PG_SCHEMA)
        else:
            conn.executescript(SQLITE_SCHEMA)


# ---------------- قراءة المنتجات ----------------
def list_products():
    sql = f'SELECT {_COLUMNS} FROM products ORDER BY id'
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        return [dict(r) for r in conn.execute(sql)]


def get_product(product_id):
    sql = _format_query(f'SELECT {_COLUMNS} FROM products WHERE id = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (product_id,))
                row = cur.fetchone()
                return dict(row) if row else None
        row = conn.execute(sql, (product_id,)).fetchone()
        return dict(row) if row else None


def count_products():
    sql = 'SELECT COUNT(*) FROM products'
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql)
                res = cur.fetchone()
                return list(res.values())[0] if isinstance(res, dict) else res[0]
        return conn.execute(sql).fetchone()[0]


def brand_counts():
    """[{'brand': 'AUCAS', 'count': 294}, ...] مرتبة بالأكثر منتجات."""
    if IS_PG:
        sql = ('SELECT brand, COUNT(*) AS count FROM products GROUP BY brand '
               'ORDER BY count DESC, LOWER(brand)')
    else:
        sql = ('SELECT brand, COUNT(*) AS count FROM products GROUP BY brand '
               'ORDER BY count DESC, brand COLLATE NOCASE')

    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        return [dict(r) for r in conn.execute(sql)]


def _like(term):
    escaped = term.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
    return f'%{escaped}%'


def search_products(q='', brand='', limit=50, offset=0):
    """بحث مع ترقيم صفحات للوحة التحكم. يرجع (الإجمالي، الصفوف)."""
    where, params = [], []
    like_op = 'ILIKE' if IS_PG else 'LIKE'

    if q:
        where.append(f"(code {like_op} ? ESCAPE '\\' OR name {like_op} ? ESCAPE '\\')")
        params += [_like(q), _like(q)]
    if brand:
        where.append('brand = ?')
        params.append(brand)
    clause = ('WHERE ' + ' AND '.join(where)) if where else ''

    sql_count = _format_query(f'SELECT COUNT(*) FROM products {clause}')
    sql_rows = _format_query(
        f'SELECT {_COLUMNS} FROM products {clause} ORDER BY id DESC LIMIT ? OFFSET ?'
    )

    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql_count, params)
                res = cur.fetchone()
                total = list(res.values())[0] if isinstance(res, dict) else res[0]
                cur.execute(sql_rows, params + [limit, offset])
                rows = [dict(r) for r in cur.fetchall()]
        else:
            total = conn.execute(sql_count, params).fetchone()[0]
            rows = [dict(r) for r in conn.execute(sql_rows, params + [limit, offset]).fetchall()]

    return total, rows


# ---------------- كتابة وتعديل المنتجات ----------------
def create_product(code, name, brand, main_cat, sub_cat, price, quantity):
    if IS_PG:
        sql = ('INSERT INTO products (code, name, brand, main_cat, sub_cat, price, quantity) '
               'VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id')
        try:
            with get_db() as conn:
                with conn.cursor() as cur:
                    cur.execute(sql, (code, name, brand, main_cat, sub_cat, price, quantity))
                    res = cur.fetchone()
                    return res['id'] if isinstance(res, dict) else res[0]
        except Exception as exc:
            _raise_if_duplicate(exc)
    else:
        sql = ('INSERT INTO products (code, name, brand, main_cat, sub_cat, price, quantity) '
               'VALUES (?, ?, ?, ?, ?, ?, ?)')
        try:
            with get_db() as conn:
                cur = conn.execute(sql, (code, name, brand, main_cat, sub_cat, price, quantity))
                return cur.lastrowid
        except sqlite3.IntegrityError as exc:
            _raise_if_duplicate(exc)


def update_product(product_id, code, name, brand, main_cat, sub_cat, price, quantity):
    sql = _format_query(
        'UPDATE products SET code=?, name=?, brand=?, main_cat=?, sub_cat=?, price=?, quantity=? WHERE id=?'
    )
    params = (code, name, brand, main_cat, sub_cat, price, quantity, product_id)
    try:
        with get_db() as conn:
            if IS_PG:
                with conn.cursor() as cur:
                    cur.execute(sql, params)
                    return cur.rowcount == 1
            cur = conn.execute(sql, params)
            return cur.rowcount == 1
    except Exception as exc:
        _raise_if_duplicate(exc)


def delete_product(product_id):
    sql = _format_query('DELETE FROM products WHERE id = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (product_id,))
                return cur.rowcount == 1
        return conn.execute(sql, (product_id,)).rowcount == 1


def upsert_many(rows):
    """إدراج دفعة منتجات بكفاءة وسرعة."""
    rows = list(rows)
    if not rows:
        return 0

    sql = _format_query("""
    INSERT INTO products (code, name, brand, main_cat, sub_cat, price, quantity)
    VALUES (?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(code) DO UPDATE SET
        name = excluded.name, brand = excluded.brand,
        main_cat = excluded.main_cat, sub_cat = excluded.sub_cat,
        price = excluded.price, quantity = excluded.quantity
    """)

    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.executemany(sql, rows)
        else:
            conn.executemany(sql, rows)
    return len(rows)


# ---------------- إعدادات النظام ----------------
def get_setting(key, default=None):
    sql = _format_query('SELECT value FROM settings WHERE key = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (key,))
                row = cur.fetchone()
                return row['value'] if row else default
        row = conn.execute(sql, (key,)).fetchone()
        return row['value'] if row else default


def set_setting(key, value):
    sql = _format_query("""
    INSERT INTO settings (key, value) VALUES (?, ?)
    ON CONFLICT(key) DO UPDATE SET value = excluded.value
    """)
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (key, str(value)))
        else:
            conn.execute(sql, (key, str(value)))


# ---------------- إدارة المستخدمين والصلاحيات (RBAC) ----------------
def get_user_by_username(username):
    sql = _format_query('SELECT id, username, password, role, name, created_at FROM users WHERE username = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (username.strip(),))
                row = cur.fetchone()
                return dict(row) if row else None
        row = conn.execute(sql, (username.strip(),)).fetchone()
        return dict(row) if row else None


def list_users():
    sql = 'SELECT id, username, role, name, created_at FROM users ORDER BY id'
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql)
                return [dict(r) for r in cur.fetchall()]
        return [dict(r) for r in conn.execute(sql)]


def create_user(username, password_hash, role='staff', name=''):
    sql = _format_query('INSERT INTO users (username, password, role, name) VALUES (?, ?, ?, ?)')
    params = (username.strip().lower(), password_hash, role.strip().lower(), name.strip() or username)
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, params)
        else:
            conn.execute(sql, params)


def update_user_password(username, new_password_hash):
    sql = _format_query('UPDATE users SET password = ? WHERE username = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (new_password_hash, username.strip().lower()))
                return cur.rowcount == 1
        return conn.execute(sql, (new_password_hash, username.strip().lower())).rowcount == 1


def delete_user(username):
    sql = _format_query('DELETE FROM users WHERE username = ?')
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql, (username.strip().lower(),))
                return cur.rowcount == 1
        return conn.execute(sql, (username.strip().lower(),)).rowcount == 1


def count_users():
    sql = 'SELECT COUNT(*) FROM users'
    with get_db() as conn:
        if IS_PG:
            with conn.cursor() as cur:
                cur.execute(sql)
                res = cur.fetchone()
                return list(res.values())[0] if isinstance(res, dict) else res[0]
        return conn.execute(sql).fetchone()[0]
