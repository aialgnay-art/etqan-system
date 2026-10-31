"""
نظام المصادقة والصلاحيات المركزي (RBAC) وحماية CSRF وتحديد محاولات الدخول.
يدعم تعدد المستخدمين برتب:
- admin (المدير: صلاحيات كاملة)
- developer (المطور: صلاحيات كاملة + سجلات تقنية)
- staff (الزميل: استعراض وجرد وبحث فقط)
"""
import hmac
import secrets
import threading
import time
from functools import wraps

from flask import abort, redirect, request, session, url_for
from werkzeug.security import check_password_hash, generate_password_hash

import db
from config import LOGIN_LOCK_SECONDS, LOGIN_MAX_FAILURES, MIN_PASSWORD_LENGTH

_LEGACY_PASSWORD_KEY = 'admin_password_hash'


# ---------------- التحقق والمصادقة ----------------
def authenticate(username, password):
    """التحقق من بيانات الدخول: يفحص جدول users ويدعم الحساب الافتراضي."""
    username = (username or '').strip().lower()
    if not username or not password:
        return None

    # 1. البحث في جدول المستخدمين متعدد الرتب
    user = db.get_user_by_username(username)
    if user and check_password_hash(user['password'], password):
        return {
            'id': user['id'],
            'username': user['username'],
            'role': user['role'],
            'name': user['name']
        }

    # 2. التوافق العكسي: إذا لم تُنشأ حسابات بعد، يُقبل حساب admin بكلمة المرور القديمة
    stored = db.get_setting(_LEGACY_PASSWORD_KEY)
    if stored and username in ('admin', 'مدير') and check_password_hash(stored, password):
        return {
            'id': 1,
            'username': 'admin',
            'role': 'admin',
            'name': 'المدير'
        }

    return None


def set_legacy_password(password):
    if len(password) < MIN_PASSWORD_LENGTH:
        raise ValueError(f'كلمة المرور يجب ألا تقل عن {MIN_PASSWORD_LENGTH} أحرف.')
    db.set_setting(_LEGACY_PASSWORD_KEY, generate_password_hash(password))


def password_is_set():
    if db.count_users() > 0:
        return True
    return db.get_setting(_LEGACY_PASSWORD_KEY) is not None


# ---------------- حراس الصلاحيات (Decorators) ----------------
def get_current_user():
    return session.get('user')


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if not session.get('user') and not session.get('admin'):
            return redirect(url_for('admin.login', next=request.full_path.rstrip('?')))
        return view(*args, **kwargs)
    return wrapped


def role_required(*allowed_roles):
    """حارس أمني صارم في السيرفر يتحقق من رتبة المستخدم لمنع أي تلاعب أو وصول غير مصرح."""
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            user = session.get('user')
            if not user and session.get('admin'):
                user = {'username': 'admin', 'role': 'admin', 'name': 'المدير'}
                session['user'] = user

            if not user:
                return redirect(url_for('admin.login', next=request.full_path.rstrip('?')))

            if user.get('role') not in allowed_roles:
                abort(403, 'غير مصرح لك بتنفيذ هذه العملية. هذه الميزة مخصصة للمدير والمطور فقط.')
            return view(*args, **kwargs)
        return wrapped
    return decorator


admin_required = role_required('admin', 'developer')
developer_required = role_required('developer')


# ---------------- حماية CSRF ----------------
def csrf_token():
    if '_csrf' not in session:
        session['_csrf'] = secrets.token_urlsafe(32)
    return session['_csrf']


def validate_csrf():
    sent = request.form.get('_csrf', '')
    expected = session.get('_csrf', '')
    if not expected or not hmac.compare_digest(sent, expected):
        abort(400, 'رمز الحماية غير صالح. أعد تحميل الصفحة وحاول مجدداً.')


# ---------------- تحديد محاولات الدخول (Brute Force Protection) ----------------
class LoginThrottle:
    def __init__(self, max_failures=LOGIN_MAX_FAILURES, lock_seconds=LOGIN_LOCK_SECONDS):
        self.max_failures, self.lock_seconds = max_failures, lock_seconds
        self._state = {}          # ip -> [failures, locked_until]
        self._lock = threading.Lock()

    def seconds_locked(self, ip):
        with self._lock:
            locked_until = self._state.get(ip, [0, 0])[1]
            return max(0, int(locked_until - time.time()))

    def failure(self, ip):
        with self._lock:
            entry = self._state.setdefault(ip, [0, 0])
            entry[0] += 1
            if entry[0] >= self.max_failures:
                entry[0], entry[1] = 0, time.time() + self.lock_seconds

    def success(self, ip):
        with self._lock:
            self._state.pop(ip, None)


throttle = LoginThrottle()
