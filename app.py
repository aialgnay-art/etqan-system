from datetime import timedelta

from flask import Flask, abort, jsonify, render_template, request, send_from_directory

import db
import security
from admin import bp as admin_bp
from brands import brand_slug
from config import (BRAND_BUTTONS, HIERARCHY, DEBUG, HIDDEN_BRANDS, HOST, PORT,
                    BASE_DIR, get_secret_key)
from smart_search import smart_search


def create_app():
    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=get_secret_key(),
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE='Lax',
        PERMANENT_SESSION_LIFETIME=timedelta(hours=12),
        MAX_CONTENT_LENGTH=4 * 1024 * 1024,          # حتى 4MB لرفع صور الشعارات
    )
    db.init_schema()
    app.register_blueprint(admin_bp)
    app.jinja_env.globals['csrf_token'] = security.csrf_token

    BRANDS_DIR = BASE_DIR / 'static' / 'images' / 'brands'
    ALLOWED_EXTENSIONS = ('.svg', '.png', '.jpg', '.jpeg', '.webp')

    @app.after_request
    def _security_headers(resp):
        resp.headers.setdefault('X-Content-Type-Options', 'nosniff')
        resp.headers.setdefault('X-Frame-Options', 'DENY')
        return resp

    @app.route('/brand-logo/<slug>')
    def brand_logo(slug):
        """خدمة شعار الماركة بصيغ متعددة مع كاش المتصفح."""
        slug_clean = brand_slug(slug)
        for ext in ALLOWED_EXTENSIONS:
            filename = f"{slug_clean}{ext}"
            file_path = BRANDS_DIR / filename
            if file_path.is_file():
                return send_from_directory(str(BRANDS_DIR), filename, max_age=300)
        return abort(404)

    @app.route('/')
    def index():
        brands = [b for b in db.brand_counts() if b['brand'].lower() not in HIDDEN_BRANDS]
        return render_template(
            'index.html',
            products=db.list_products(),
            hierarchy=HIERARCHY,
            brands_main=brands[:BRAND_BUTTONS],
            brands_more=brands[BRAND_BUTTONS:],
        )

    @app.route('/search')
    def search():
        """البحث الذكي (عربي/لهجة). يرجع ترتيب المعرّفات فقط؛ الجدول يبقى في المتصفح."""
        q = request.args.get('q', '').strip()
        search_type = request.args.get('type', 'name')
        brand = request.args.get('brand', '').strip().lower()

        rows = db.list_products()
        if brand:
            rows = [p for p in rows if p['brand'].lower() == brand]

        approx = False
        if q:
            if search_type == 'code':
                rows = [p for p in rows if q.lower() in p['code'].lower()]
            else:
                rows, approx = smart_search(q, rows)
        return jsonify({'approx': approx, 'ids': [p['id'] for p in rows]})

    @app.route('/health')
    def health():
        """فحص السلامة (Healthcheck) لخدمات السحابة و Uptime Monitoring لمنع الخمول."""
        db_ok = True
        total = 0
        try:
            total = db.count_products()
        except Exception:
            db_ok = False
        return jsonify({
            'status': 'healthy' if db_ok else 'degraded',
            'database': 'connected' if db_ok else 'error',
            'products_count': total,
            'cloud_mode': db.IS_PG
        }), (200 if db_ok else 500)

    return app


app = create_app()

if __name__ == '__main__':
    if DEBUG:
        # التطوير: محلي فقط، لأن الـ Debugger التفاعلي ينفّذ أكواداً على جهازك
        app.run(host='127.0.0.1', port=PORT, debug=True)
    else:
        if not security.password_is_set():
            print('⚠️  لم تُحدَّد كلمة مرور للوحة التحكم بعد: python setup_db.py --set-password')
        from waitress import serve
        print(f'✅ الخادم يعمل على http://{HOST}:{PORT}')
        serve(app, host=HOST, port=PORT, threads=8)