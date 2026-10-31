import re
import difflib

AR_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")


def normalize(text):
    """توحيد الحروف العربية وتحويلها لحروف صغيرة عشان البحث يفهم الاختلافات."""
    t = str(text).lower().translate(AR_DIGITS)
    t = re.sub(r"[\u064B-\u0652\u0640]", "", t)
    t = re.sub("[أإآ]", "ا", t)
    for a, b in (("ى", "ي"), ("ة", "ه"), ("ؤ", "و"), ("ئ", "ي")):
        t = t.replace(a, b)
    return t


def _prep(table):
    return {k: [normalize(a) for a in v] for k, v in table.items()}


# ---------- القواميس (زيد عليها اللي تبي) ----------
BRANDS = _prep({
    "aucas": ["اكوس", "اوكاس", "اوكس", "اكوص", "aucas"],
    "planet": ["بلانت", "بلانيت", "بلانط", "planet"],
    "commando": ["كوماندو", "كومندو", "commando"],
    "cisco": ["سيسكو", "سسكو", "cisco"],
    "onv": ["onv", "اونف"],
    "nexans": ["نكسانس", "نيكسانس", "nexans"],
    "dahua": ["داهوا", "داهوه", "dahua"],
    "atopwell": ["اتوبويل", "اتوب", "atopwell"],
    "exw": ["exw", "اي اكس دبليو"],
    "laoa": ["laoa", "لاوا"],
    "proskit": ["proskit", "بروسكيت", "بروسكت"],
    "aerech": ["aerech", "ايريش", "ايرك", "ايرتش"],
    "3m": ["3m", "ثري ام", "3 ام"],
    "honeywell": ["honeywell", "هانيويل", "هنيويل"],
    "premium": ["premium", "بريميوم", "برميوم"],
    "truper": ["truper", "تروبر", "تروبير"],
})

COLORS = _prep({
    "blue": ["ازرق", "زرق", "blue"],
    "green": ["اخضر", "خضر", "green"],
    "grey": ["رمادي", "grey", "gray"],
    "red": ["احمر", "حمر", "red"],
    "yellow": ["اصفر", "صفر", "yellow"],
    "black": ["اسود", "black"],
    "white": ["ابيض", "white"],
})

# نوع الفايبر: سنقل مود (sm) / ملتي مود (mm)
MODES = _prep({
    "sm": ["سنقل", "سنجل", "سينقل", "سينجل", "سنغل", "احادي", "single", "sm", "os2"],
    "mm": ["ملتي", "مالتي", "متعدد", "multi", "mm"],
})

# داخلي / خارجي
ENVS = _prep({
    "outdoor": ["خارجي", "خارجيه", "خارج", "outdoor"],
    "indoor": ["داخلي", "داخليه", "داخل", "indoor"],
})


def _product_mode(text):
    if re.search(r"\b(sm|single|os2)\b|9/125", text):
        return "sm"
    if re.search(r"\b(mm|multi|om[1-4])\b|50/125|62\.5", text):
        return "mm"
    return None


def _product_env(text):
    if re.search(r"outdoor|خارج", text):
        return "outdoor"
    if re.search(r"indoor|داخل", text):
        return "indoor"
    return None


def _product_conn(text):
    """يرجع نوع الكونكتورات مرتبة: lc/lc أو lc/sc أو sc/sc ..."""
    m = re.search(r"\b(lc|sc|fc|st)\s*/\s*(lc|sc|fc|st)\b", text)
    return "/".join(sorted(m.groups())) if m else None


# كلمات عامة تعطي نقاط إضافية للمنتجات المناسبة (مش شرط إجباري)
SOFT = {normalize(k): v for k, v in {
    "نحاس": ["cat", "utp", "sftp"],
    "نحاسي": ["cat", "utp", "sftp"],
    "سلك": ["patch", "cord"],
    "كابل": ["patch", "cord"],
    "وصله": ["patch", "cord"],
    "باتش": ["patch"],
    "كورد": ["cord"],
    "الياف": ["fiber", "sfp", "odf", "lc", "sc"],
    "فايبر": ["fiber", "sfp", "odf", "lc", "sc"],
    "بصري": ["fiber", "sfp", "odf", "lc", "sc"],
    "بصريه": ["fiber", "sfp", "odf", "lc", "sc"],
    "مدرع": ["armored"],
    "مدرعه": ["armored"],
    "راوتر": ["router"],
    "سويتش": ["switch"],
    "محول": ["switch"],
}.items()}

NUM_WORDS = {"واحد": 1, "اثنين": 2, "ثلاثه": 3, "ثلاث": 3, "اربعه": 4,
             "اربع": 4, "خمسه": 5, "خمس": 5, "عشره": 10}

STOP = set(normalize(w) for w in [
    "عندك", "عندكم", "نبي", "ابي", "نبغي", "ابغي", "بغيت", "شن", "شنو",
    "فيه", "من", "لي", "ليا", "في", "بي", "عطيني", "اعطيني", "ممكن",
    "شركه", "ماركه", "طول", "لون", "مود", "mode", "نوع", "الي", "و", "مع", "على", "علي", "ب",
])


_FLAT_CACHE = {}


def _canon(s):
    """يوحّد اسم البراند للمقارنة: Pro'skit و proskit يصبحان نفس الشيء."""
    return re.sub(r"[^a-z0-9]", "", str(s).lower())


def _lookup(token, table):
    flat = _FLAT_CACHE.get(id(table))
    if flat is None:  # كان يُبنى من جديد مع كل كلمة بحث؛ الآن مرة واحدة فقط
        flat = _FLAT_CACHE[id(table)] = {a: k for k, v in table.items() for a in v}
    if token in flat:
        return flat[token]
    if len(token) >= 4:
        m = difflib.get_close_matches(token, list(flat), n=1, cutoff=0.8)
        if m:
            return flat[m[0]]
    return None


def smart_search(query, products):
    """
    يرجع (قائمة_المنتجات, تقريبي؟)
    products: قائمة dict فيها code, name, brand, price, quantity
    """
    q = normalize(query).strip()
    if not q:
        return products, False

    # --- تجهيز الجملة ---
    q = re.sub(r"\bكات\b", "cat", q)
    for w, n in NUM_WORDS.items():
        q = re.sub(rf"\b{w}\s+(?=متر|ميتر)", f"{n} ", q)
    q = re.sub(r"\b(?:نص|نصف)\s+متر", "0.5 متر", q)
    q = re.sub(r"\bربع\s+متر", "0.25 متر", q)
    q = re.sub(r"\bمترين\b", "2 متر", q)

    # --- OM2 / OM3 / OM4 (ملتي مود) ---
    om = None
    m = re.search(r"\b(?:om|اوم|ام|m)\s*-?\s*([1-4])\b", q)
    if m:
        om = m.group(1)
        q = q.replace(m.group(0), " ")

    # --- داخلي / خارجي (عبارات من كلمتين) ---
    q = re.sub(r"اوت\s*دور", "outdoor", q)
    q = re.sub(r"\bان\s*دور", "indoor", q)

    # --- سماكة الكابل مثل 3.3mm ---
    q = re.sub(r"(\d+(?:\.\d+)?)\s*(?:mm|ملم|مم)\b", r"\1mm", q)

    # --- الكونكتور: LC (صغير) / SC (كبير) ---
    q = re.sub(r"\b(?:ال|ايل)\s*سي\b", "lc", q)
    q = re.sub(r"\bاس\s*سي\b", "sc", q)
    conn_pair = None
    soft_conn = []
    m = re.search(r"\b(lc|sc|fc|st)\s*[/\\\-]?\s*(lc|sc|fc|st)\b", q)
    if m:
        conn_pair = "/".join(sorted(m.groups()))
        q = q.replace(m.group(0), " ")
    else:
        big = re.search(r"كبير|كبيره|كبار", q)
        small = re.search(r"صغير|صغيره|صغار", q)
        both = re.search(r"الجهتين|جهتين|الطرفين|طرفين|الناحيتين|ناحيتين", q)
        if big and small:
            conn_pair = "lc/sc"
        elif big and both:
            conn_pair = "sc/sc"
        elif small and both:
            conn_pair = "lc/lc"
        elif big:
            soft_conn = ["sc"]
        elif small:
            soft_conn = ["lc"]
    q = re.sub(r"كبير|كبيره|كبار|صغير|صغيره|صغار|الجهتين|جهتين|الطرفين|طرفين"
               r"|الناحيتين|ناحيتين|جيهه|جهه|ناحيه|طرف", " ", q)

    # --- الطول ---
    length = None
    m = re.search(r"(\d+(?:\.\d+)?)\s*(?:متر|ميترو|ميتر|mtr|meter|m)\b", q)
    if m:
        length = float(m.group(1))
        q = q.replace(m.group(0), " ")

    # --- نوع الكات (Cat 6 / Cat 7) ---
    cat = None
    m = re.search(r"cat\s*-?\s*(\d)", q)
    if m:
        cat = m.group(1)
        q = q.replace(m.group(0), " ")

    # --- باقي الكلمات ---
    tokens = [t for t in re.findall(r"[a-z0-9.\-]+|[\u0600-\u06FF]+", q)
              if t not in STOP]
    brand = color = need_type = mode = env = None
    soft, plain = list(soft_conn), []
    for t in tokens:
        if t in ("utp", "sftp"):
            need_type = t
            continue
        b = _lookup(t, BRANDS)
        if b and not brand:
            brand = b
            continue
        c = _lookup(t, COLORS)
        if c and not color:
            color = c
            continue
        md = _lookup(t, MODES)
        if md and not mode:
            mode = md
            continue
        ev = _lookup(t, ENVS)
        if ev and not env:
            env = ev
            continue
        if t in SOFT:
            soft += SOFT[t]
            continue
        plain.append(t)

    active = sum(x is not None for x in (brand, color, cat, need_type, length, mode, om, env, conn_pair))

    scored = []
    for p in products:
        name = normalize(p["name"])
        brand_p = normalize(p["brand"])
        hay = f"{name} {normalize(p['code'])} {brand_p}"

        misses = 0
        if brand and not _canon(brand_p).startswith(_canon(brand)):
            misses += 1
        if color and color not in name:
            misses += 1
        if cat and not re.search(rf"cat\s*{cat}\b", name):
            misses += 1
        if need_type and need_type not in name:
            misses += 1
        if length is not None:
            ln = re.search(r"(\d+(?:\.\d+)?)\s*m\b", name)
            if not ln or float(ln.group(1)) != length:
                misses += 1

        if mode and _product_mode(hay) != mode:
            misses += 1
        if om and not re.search(rf"\bom{om}\b", hay):
            misses += 1
        if env and _product_env(hay) != env:
            misses += 1
        if conn_pair and _product_conn(hay) != conn_pair:
            misses += 1

        score = 3 * (active - misses)
        for s in soft:
            if s in hay:
                score += 1
        words = hay.split()
        for t in plain:
            if t in hay:
                score += 2
            elif len(t) >= 3 and difflib.get_close_matches(t, words, n=1, cutoff=0.75):
                score += 1

        scored.append((misses, score, p))

    exact = [(s, p) for ms, s, p in scored if ms == 0 and (s > 0 or active > 0)]
    if exact:
        exact.sort(key=lambda x: -x[0])
        return [p for _, p in exact], False

    near = [(s, p) for ms, s, p in scored if ms == 1 and s > 0]
    near.sort(key=lambda x: -x[0])
    return [p for _, p in near[:8]], True


if __name__ == "__main__":
    demo = [
        {"code": "AU-C6-3M", "name": "Aucas Copper Cable Cat 6 UTP Grey 3M", "brand": "Aucas", "price": 20, "quantity": 30},
        {"code": "AU-C6-1M", "name": "Aucas Copper Cable Cat 6 UTP Grey 1M", "brand": "Aucas", "price": 12, "quantity": 30},
        {"code": "PL-PC03U6GY", "name": "Planet Patch Cord Cat 6 UTP Grey 3M", "brand": "Planet", "price": 19.5, "quantity": 43},
        {"code": "PL-PC05U6RD", "name": "Planet Patch Cord Cat 6 UTP Red 0.5M", "brand": "Planet", "price": 13.5, "quantity": 57},
    ]
    demo += [
        {"code": "AT-SM-LCLC-10", "name": "Atopwell Patch Cord SM LC/LC 10m Indoor", "brand": "Atopwell", "price": 30, "quantity": 5},
        {"code": "AT-OM3-LCLC-10", "name": "Atopwell Patch Cord OM3 LC/LC 10m Indoor", "brand": "Atopwell", "price": 35, "quantity": 5},
        {"code": "AT-OM4-LCLC-10", "name": "Atopwell Patch Cord OM4 LC/LC 10m Indoor", "brand": "Atopwell", "price": 40, "quantity": 5},
        {"code": "AT-SM-OUT-100", "name": "Atopwell Patch Cord SM Outdoor LC/SC 100m", "brand": "Atopwell", "price": 675, "quantity": 7},
    ]
    demo += [
        {"code": "AT-LCSC-10", "name": "Atopwell Patch Cord SM LC/SC 10m Indoor", "brand": "Atopwell", "price": 32, "quantity": 5},
        {"code": "AT-SCSC-10", "name": "Atopwell Patch Cord SM SC/SC 10m Indoor", "brand": "Atopwell", "price": 31, "quantity": 5},
    ]
    for t in ["كبير من جيهة وصغير من جيهة", "صغير من الجهتين 10 متر", "كبير من الجهتين", "lc/sc 10 متر",
              "sc lc", "ال سي اس سي", "كبير", "الياف سنقل مود 10 متر", "ملتي مود m3", "ملتي مود om4 10 متر", "الياف خارجي سنقل مود",
              "الياف داخلي", "اوت دور 100 متر", "multi mode", "الياف 3.3 مم",
              "سلك نحاس 3 ميترو شركة اكوس", "نص متر احمر بلانت", "كات 6 رمادي ٣ متر", "PL-PC05"]:
        res, approx = smart_search(t, demo)
        print(t, "->", [r["code"] for r in res], "(تقريبي)" if approx else "")
