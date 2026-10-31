"""إعدادات المشروع المركزية — لا توجد مسارات أو منافذ أو أسرار مكتوبة في أي ملف آخر."""
import os
import secrets
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / 'data'
DB_PATH = DATA_DIR / 'database.db'
BACKUP_DIR = DATA_DIR / 'backups'
SECRET_KEY_FILE = DATA_DIR / 'secret.key'

DATABASE_URL = os.environ.get('DATABASE_URL')
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

HOST = os.environ.get('ETQAN_HOST', '0.0.0.0')
PORT = int(os.environ.get('ETQAN_PORT', os.environ.get('PORT', '5000')))

# وضع التطوير يُفعَّل صراحةً فقط:  set ETQAN_DEBUG=1
DEBUG = os.environ.get('ETQAN_DEBUG') == '1'

# ---- الواجهة العامة ----
BRAND_BUTTONS = 15          # عدد أزرار البراند الظاهرة مباشرة (الباقي خلف "عرض الكل")
HIDDEN_BRANDS = {'generic'}  # براندات لا تُعرض كأزرار

# الهيكل الهرمي للأقسام (المصدر الوحيد لتوليد الواجهة وقوائم الإدخال)
HIERARCHY = {
    'CABLES & PATCH CORDS': ['PATCH CORD (COPPER)', 'PATCH CORD (FIBER)', 'BULK CABLE'],
    'COPPER INFRASTRUCTURE': ['PATCH PANEL', 'KEYSTONE JACK', 'FACE PLATE', 'RJ45 CONNECTORS', 'CABLE MANAGEMENT'],
    'FIBER OPTIC INFRASTRUCTURE': ['ODF & FTTH', 'CLOSURES', 'PIGTAILS', 'ADAPTERS', 'FAST CONNECTOR', 'SPLITTERS'],
    'ACTIVE NETWORKING': ['SFP / TRANSCEIVERS', 'SWITCHES', 'ROUTERS & FIREWALLS', 'WIRELESS (AP)', 'MEDIA CONVERTERS', 'OLT & ONU', 'POE INJECTORS'],
    'TOOLS & TESTERS': ['CRIMPERS & CUTTERS', 'NETWORK TESTERS', 'FIBER TOOLS'],
    'SURVEILLANCE & SECURITY': ['CAMERAS', 'NVR & HDD', 'ACCESS CONTROL'],
    'RACKS & POWER': ['RACKS & CABINETS', 'PDU & UPS', 'ACCESSORIES']
}

# ---- لوحة التحكم ----
ADMIN_PAGE_SIZE = 50
MIN_PASSWORD_LENGTH = 8
LOGIN_MAX_FAILURES = 5
LOGIN_LOCK_SECONDS = 300


def get_secret_key():
    """مفتاح توقيع الجلسات: يُولَّد عشوائياً مرة واحدة ويُحفظ، أو يُقرأ من متغير البيئة في السحابة."""
    env_secret = os.environ.get('SECRET_KEY')
    if env_secret:
        return env_secret.strip()

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not SECRET_KEY_FILE.exists():
        SECRET_KEY_FILE.write_text(secrets.token_hex(32), encoding='ascii')
        try:
            SECRET_KEY_FILE.chmod(0o600)
        except OSError:
            pass
    return SECRET_KEY_FILE.read_text(encoding='ascii').strip()