"""لوحة التحكم: تسجيل دخول + إضافة/تعديل/حذف المنتجات."""
import csv
import io
import math
import os

from flask import (Blueprint, Response, flash, redirect, render_template, request,
                   session, url_for)

import db
import security
from brands import brand_slug
from config import ADMIN_PAGE_SIZE, BASE_DIR, HIERARCHY

bp = Blueprint('admin', __name__, url_prefix='/admin')

BRANDS_DIR = BASE_DIR / 'static' / 'images' / 'brands'
ALLOWED_LOGO_EXTENSIONS = {'.svg', '.png', '.jpg', '.jpeg', '.webp'}

_DIGITS = str.maketrans('٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬', '01234567890123456789.,')
_MAX_NUMBER = 10_000_000


# ---------------- أدوات مساعدة ----------------
@bp.before_request
def _protect_posts():
    if request.method == 'POST':
        security.validate_csrf()


@bp.after_request
def _no_cache(resp):
    resp.headers['Cache-Control'] = 'no-store'
    return resp


def _safe_next(target, fallback):
    """يمنع إعادة التوجيه إلى مواقع خارجية: لا نقبل إلا مسارات داخل /admin."""
    if target and target.startswith('/admin') and not target.startswith('//'):
        return target
    return fallback


def _to_number(raw):
    text = (raw or '').strip().translate(_DIGITS).replace(',', '')
    return float(text)


def parse_product_form(form):
    """يرجع (القيم النظيفة, قائمة الأخطاء)."""
    errors = []
    code = (form.get('code') or '').strip()
    name = ' '.join((form.get('name') or '').split())
    brand = ' '.join((form.get('brand') or '').split()) or 'Generic'
    main_cat = ' '.join((form.get('main_cat') or '').split()) or 'غير مصنف'
    sub_cat = ' '.join((form.get('sub_cat') or '').split()) or 'غير مصنف'

    if not code:
        errors.append('رقم الصنف مطلوب.')
    elif len(code) > 64:
        errors.append('رقم الصنف أطول من 64 حرفاً.')
    if not name:
        errors.append('اسم الصنف مطلوب.')
    elif len(name) > 300:
        errors.append('اسم الصنف أطول من 300 حرف.')
    if len(brand) > 60:
        errors.append('اسم البراند أطول من 60 حرفاً.')

    price = quantity = 0
    try:
        price = round(_to_number(form.get('price') or '0'), 2)
        if not (0 <= price <= _MAX_NUMBER):          # يرفض NaN أيضاً
            raise ValueError
    except ValueError:
        errors.append('السعر يجب أن يكون رقماً صحيحاً غير سالب.')
    try:
        qty = _to_number(form.get('quantity') or '0')
        if not (0 <= qty <= _MAX_NUMBER) or qty != int(qty):
            raise ValueError
        quantity = int(qty)
    except (ValueError, OverflowError):
        errors.append('العدد يجب أن يكون رقماً صحيحاً غير سالب.')

    return {'code': code, 'name': name, 'brand': brand, 
            'main_cat': main_cat, 'sub_cat': sub_cat,
            'price': price, 'quantity': quantity}, errors


def _list_context():
    q = request.values.get('q', '').strip()
    brand = request.values.get('brand', '').strip()
    try:
        page = max(1, int(request.values.get('page', 1)))
    except ValueError:
        page = 1
    total, rows = db.search_products(q, brand, ADMIN_PAGE_SIZE, (page - 1) * ADMIN_PAGE_SIZE)
    return {
        'q': q, 'brand': brand, 'page': page, 'total': total, 'products': rows,
        'pages': max(1, math.ceil(total / ADMIN_PAGE_SIZE)),
        'brands': db.brand_counts(),
        'hierarchy': HIERARCHY,
        'list_url': url_for('admin.products', q=q or None, brand=brand or None,
                            page=page if page > 1 else None),
    }


def _render_list(status=200, **extra):
    return render_template('admin/products.html', **_list_context(), reopen=None, **extra), status


def _reopen_with_errors(title, action, values, errors):
    ctx = _list_context()
    reopen = {'title': title, 'action': action, 'values': values, 'errors': errors}
    return render_template('admin/products.html', **ctx, reopen=reopen), 422


# ---------------- الدخول والخروج ----------------
@bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('user') or session.get('admin'):
        return redirect(url_for('admin.products'))
    ip = request.remote_addr or 'unknown'
    configured = security.password_is_set()

    if request.method == 'POST' and configured:
        wait = security.throttle.seconds_locked(ip)
        if wait:
            flash(f'محاولات كثيرة خاطئة. حاول بعد {math.ceil(wait / 60)} دقيقة.', 'danger')
        else:
            username = request.form.get('username', 'admin').strip()
            password = request.form.get('password', '')
            user = security.authenticate(username, password)
            if user:
                security.throttle.success(ip)
                csrf = session.get('_csrf')
                session.clear()                       # يمنع تثبيت الجلسة (session fixation)
                session['_csrf'] = csrf
                session['user'] = user
                session['admin'] = (user['role'] in ('admin', 'developer'))
                session.permanent = True
                return redirect(_safe_next(request.form.get('next'), url_for('admin.products')))
            else:
                security.throttle.failure(ip)
                flash('اسم المستخدم أو كلمة المرور غير صحيحة.', 'danger')

    return render_template('admin/login.html', configured=configured,
                           next=request.values.get('next', ''))


@bp.post('/logout')
def logout():
    session.clear()
    return redirect(url_for('admin.login'))


# ---------------- المنتجات ----------------
@bp.get('/')
@security.login_required
def products():
    return _render_list()


@bp.post('/products/new')
@security.admin_required
def add_product():
    values, errors = parse_product_form(request.form)
    action = url_for('admin.add_product')
    if not errors:
        try:
            db.create_product(**values)
        except db.DuplicateCodeError:
            errors.append('رقم الصنف مستخدم لمنتج آخر.')
    if errors:
        return _reopen_with_errors('إضافة منتج', action, values, errors)
    flash(f'تمت إضافة «{values["name"]}».', 'success')
    return redirect(_safe_next(request.form.get('next'), url_for('admin.products')))


@bp.post('/products/<int:product_id>/edit')
@security.admin_required
def edit_product(product_id):
    values, errors = parse_product_form(request.form)
    action = url_for('admin.edit_product', product_id=product_id)
    if not errors:
        try:
            if not db.update_product(product_id, **values):
                flash('المنتج غير موجود (ربما حُذف).', 'danger')
                return redirect(url_for('admin.products'))
        except db.DuplicateCodeError:
            errors.append('رقم الصنف مستخدم لمنتج آخر.')
    if errors:
        return _reopen_with_errors('تعديل منتج', action, values, errors)
    flash('تم حفظ التعديلات.', 'success')
    return redirect(_safe_next(request.form.get('next'), url_for('admin.products')))


@bp.post('/products/<int:product_id>/delete')
@security.admin_required
def delete_product(product_id):
    if db.delete_product(product_id):
        flash('تم حذف المنتج.', 'success')
    else:
        flash('المنتج غير موجود (ربما حُذف مسبقاً).', 'danger')
    return redirect(_safe_next(request.form.get('next'), url_for('admin.products')))


@bp.get('/export')
@security.admin_required
def export_csv():
    """تصدير المنتجات إلى ملف CSV متوافق تماماً مع import_excel.py"""
    rows = db.list_products()
    output = io.StringIO()
    # إضافة BOM لتتعرف برامج الإكسل على ترميز UTF-8 واللغة العربية تلقائياً
    output.write('\ufeff')
    writer = csv.writer(output, dialect='excel')
    
    # الأعمدة المطابقة لسكريبت import_excel.py تماماً
    writer.writerow(['اسم الصنف', 'رقم الصنف', 'القطاعي', 'العدد الحالي', 'المجموعة الرئيسية', 'الفئة الفرعية'])
    
    for p in rows:
        writer.writerow([
            p['name'],
            p['code'],
            p['price'],
            p['quantity'],
            p['main_cat'],
            p['sub_cat']
        ])
        
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-disposition": "attachment; filename=etqan_products.csv"}
    )


# ---------------- إدارة شعارات البراندات ----------------
@bp.get('/brands')
@security.login_required
def brands():
    """عرض قائمة العلامات التجارية مع حالة الشعار ومعاينته."""
    BRANDS_DIR.mkdir(parents=True, exist_ok=True)
    all_brands = db.brand_counts()
    brands_data = []

    for b in all_brands:
        name = b['brand']
        slug = brand_slug(name)
        existing_file = None
        for ext in ('.svg', '.png', '.jpg', '.jpeg', '.webp'):
            if (BRANDS_DIR / f"{slug}{ext}").is_file():
                existing_file = f"{slug}{ext}"
                break
        brands_data.append({
            'name': name,
            'count': b['count'],
            'slug': slug,
            'has_logo': existing_file is not None,
            'logo_file': existing_file
        })

    return render_template('admin/brands.html', brands=brands_data)


@bp.post('/brands/<slug>/upload')
@security.admin_required
def upload_brand_logo(slug):
    """رفع أو استبدال شعار علامة تجارية."""
    slug_clean = brand_slug(slug)
    file = request.files.get('logo')
    brand_name = request.form.get('brand_name', slug).strip()

    if not file or not file.filename:
        flash('يرجى اختيار ملف صورة لرفعه.', 'danger')
        return redirect(url_for('admin.brands'))

    _, ext = os.path.splitext(file.filename.lower())
    if ext not in ALLOWED_LOGO_EXTENSIONS:
        flash(f'صيغة غير مدعومة ({ext}). الصيغ المسموحة هي: SVG, PNG, JPG, WEBP', 'danger')
        return redirect(url_for('admin.brands'))

    BRANDS_DIR.mkdir(parents=True, exist_ok=True)

    # حذف أي شعار سابق بهذه العلامة لتجنب تكرار الامتدادات
    for old_ext in ('.svg', '.png', '.jpg', '.jpeg', '.webp'):
        old_file = BRANDS_DIR / f"{slug_clean}{old_ext}"
        if old_file.is_file():
            try:
                old_file.unlink()
            except OSError:
                pass

    # حفظ الشعار الجديد
    target_filename = f"{slug_clean}{ext}"
    target_path = BRANDS_DIR / target_filename
    file.save(str(target_path))

    flash(f'تم تحديث شعار «{brand_name}» بنجاح.', 'success')
    return redirect(url_for('admin.brands'))


@bp.post('/brands/<slug>/delete')
@security.admin_required
def delete_brand_logo(slug):
    """حذف شعار علامة تجارية لتعود لاستخدام الشارة البديلة."""
    slug_clean = brand_slug(slug)
    brand_name = request.form.get('brand_name', slug).strip()
    deleted = False

    for ext in ('.svg', '.png', '.jpg', '.jpeg', '.webp'):
        old_file = BRANDS_DIR / f"{slug_clean}{ext}"
        if old_file.is_file():
            try:
                old_file.unlink()
                deleted = True
            except OSError:
                pass

    if deleted:
        flash(f'تم حذف شعار «{brand_name}». سيعتمد النظام الشارة النصية البديلة تلقائياً.', 'success')
    else:
        flash(f'لا يوجد شعار محفوظ لـ «{brand_name}» ليتم حذفه.', 'warning')

    return redirect(url_for('admin.brands'))


# ---------------- إدارة المستخدمين والصلاحيات (RBAC) ----------------
@bp.get('/users')
@security.admin_required
def users():
    """عرض وإدارة مستخدمي المنظومة والصلاحيات."""
    all_users = db.list_users()
    return render_template('admin/users.html', users=all_users, current_user=security.get_current_user())


@bp.post('/users/new')
@security.admin_required
def add_user():
    username = request.form.get('username', '').strip().lower()
    password = request.form.get('password', '')
    role = request.form.get('role', 'staff').strip().lower()
    name = request.form.get('name', '').strip()

    if not username or len(username) < 3:
        flash('اسم المستخدم يجب ألا يقل عن 3 أحرف.', 'danger')
        return redirect(url_for('admin.users'))

    if len(password) < 6:
        flash('كلمة المرور يجب ألا تقل عن 6 أحرف.', 'danger')
        return redirect(url_for('admin.users'))

    if role not in ('admin', 'developer', 'staff'):
        flash('الرتبة المحددة غير صالحة.', 'danger')
        return redirect(url_for('admin.users'))

    from werkzeug.security import generate_password_hash
    try:
        db.create_user(username, generate_password_hash(password), role, name)
        flash(f'تمت إضافة المستخدم «{name or username}» بنجاح كـ {role}.', 'success')
    except Exception:
        flash('اسم المستخدم مسجل مسبقاً لمستخدم آخر.', 'danger')

    return redirect(url_for('admin.users'))


@bp.post('/users/<username>/password')
@security.admin_required
def change_user_password(username):
    new_password = request.form.get('password', '')
    if len(new_password) < 6:
        flash('كلمة المرور يجب ألا تقل عن 6 أحرف.', 'danger')
        return redirect(url_for('admin.users'))

    from werkzeug.security import generate_password_hash
    if db.update_user_password(username, generate_password_hash(new_password)):
        flash(f'تم تحديث كلمة المرور لـ «{username}» بنجاح.', 'success')
    else:
        flash('المستخدم غير موجود.', 'danger')
    return redirect(url_for('admin.users'))


@bp.post('/users/<username>/delete')
@security.admin_required
def delete_user(username):
    curr = security.get_current_user()
    if curr and curr.get('username') == username.lower():
        flash('لا يمكنك حذف حسابك الحالي المسجل به الدخول.', 'danger')
        return redirect(url_for('admin.users'))

    if db.delete_user(username):
        flash(f'تم حذف المستخدم «{username}».', 'success')
    else:
        flash('المستخدم غير موجود.', 'danger')
    return redirect(url_for('admin.users'))