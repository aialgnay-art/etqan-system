"""استخراج البراند من اسم الصنف — مصدر واحد للمنطق يستخدمه الاستيراد وإصلاح البيانات."""
import re

# المفتاح: صيغة مبسّطة (حروف صغيرة بلا رموز) ← القيمة: الاسم المعروض
BRAND_MAP = {
    'aucas': 'AUCAS', 'atopwell': 'AtopWell', 'proskit': "Pro'skit", 'prosket': "Pro'skit",
    'tinda': 'Tenda', 'tenda': 'Tenda', 'hikvision': 'HikVision', 'dahua': 'Dahua',
    'dauha': 'Dahua', 'planet': 'Planet', 'plant': 'Planet', 'cisco': 'Cisco',
    'onv': 'ONV', 'bdcom': 'BDCOM', 'aerech': 'AERECH', 'commando': 'COMMANDO',
    'vsol': 'V-SOL', 'fortigate': 'FortiGate', 'fortifate': 'FortiGate', 'noyafa': 'NOYAFA',
    'comptyco': 'Comptyco', 'compatyco': 'Comptyco', 'compatico': 'Comptyco',
    'fujikura': 'Fujikura', 'adtek': 'Adtek', 'nexans': 'Nexans', 'exw': 'EXW',
    '3m': '3M', '6com': '6COM', 'laoa': 'LAOA', 'ampcom': 'AMPCOM', 'legrand': 'Legrand',
    'honeywell': 'Honeywell', 'truper': 'Truper', 'pretul': 'Pretul', 'wanjeed': 'Wanjeed',
    'premium': 'Premium Line', 'premuim': 'Premium Line', 'premiumline': 'Premium Line',
    'premuimline': 'Premium Line', 'baudcom': 'BAUDCOM', 'knc': 'KNC', 'finen': 'FINEN',
    'htttf': 'HTTF', 'httf': 'HTTF', 'wave': 'Wave Link', 'wavelink': 'Wave Link',
    'ubiquiti': 'Ubiquiti', 'totolink': 'TOTOLINK', 'dlink': 'D-LINK', 'tplink': 'TPLINK',
    'sailsky': 'SailSky', 'cudy': 'Cudy', 'owire': 'OWIRE', 'tenveo': 'TENVEO',
    'niimbot': 'NIIMBOT', 'hdlink': 'HD-LINK', 'hdvision': 'HD Vision', 'fiberbit': 'FiberBit',
    'comfast': 'COMFAST', 'acti': 'ACTi', 'amp': 'AMP', 'asus': 'Asus', 'belco': 'Belco',
    'bonet': 'BO-Net', 'adp': 'ADP', 'adpadp': 'ADP', 'xiaomi': 'Xiaomi',
}

GENERIC = 'Generic'

# مفاتيح قصيرة/عامة لا تُقبل إلا في أول الاسم (تجنباً لإيجابيات كاذبة وسط الاسم)
_FIRST_POSITION_ONLY = {'wave', 'premium', 'plant', 'amp', 'knc', 'acti', 'adp', 'exw'}
_MIN_PREFIX_LEN = 5   # أقل طول لبراند يُقبل كبادئة داخل كلمة ملتصقة (commandoe1000)


def _canon(s):
    return re.sub(r'[^a-z0-9]', '', str(s).lower())


def brand_slug(s):
    """تحويل اسم البراند إلى معرف موحد لأسماء الملفات والروابط (أحرف صغيرة بلا رموز)."""
    return _canon(s) or 'generic'


def _match_start(tokens, start):
    """يجرّب دمج 3 ثم 2 ثم 1 كلمات ابتداءً من start، ثم مطابقة البادئة الملتصقة."""
    window = tokens[start:start + 3]
    for n in (3, 2, 1):
        key = _canon(''.join(window[:n]))
        if key in BRAND_MAP:
            return BRAND_MAP[key]

    first = _canon(window[0]) if window else ''
    for alias, display in BRAND_MAP.items():
        if not first.startswith(alias):
            continue
        rest = first[len(alias):]
        if len(alias) >= _MIN_PREFIX_LEN or (rest and rest[0].isdigit()):   # commandoe1000 / onv1110
            return display
    return None


def extract_brand(name):
    """يرجع اسم البراند المعروف، أو 'Generic' إذا لم يُتعرف عليه (لا يخترع براندات)."""
    if name is None:
        return GENERIC
    name = str(name).strip()
    if not name or name == '.':
        return GENERIC

    tokens = [t for t in re.split(r"[\s\-_/,]+", name.replace("'", "")) if t]
    if not tokens:
        return GENERIC

    # 1) أول الاسم (وإن بدأ برقم مثل "1 Core ..." نجرّب الكلمة التي بعده)
    starts = [0]
    if re.fullmatch(r'[\d.]+', tokens[0]) and len(tokens) > 1:
        starts.append(1)
    for s in starts:
        found = _match_start(tokens, s)
        if found:
            return found

    # 2) براند يأتي بعد كلمة وصفية: "Wireless TOTOLINK N350RT"
    for i in range(1, len(tokens)):
        for n in (2, 1):
            key = _canon(''.join(tokens[i:i + n]))
            if key in BRAND_MAP and key not in _FIRST_POSITION_ONLY:
                return BRAND_MAP[key]

    return GENERIC
