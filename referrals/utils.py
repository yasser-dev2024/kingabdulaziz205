# referrals/utils.py
import re
import unicodedata

_AR_MAP = str.maketrans({
    "أ": "ا", "إ": "ا", "آ": "ا",
    "ى": "ي", "ؤ": "و", "ئ": "ي", "ة": "ه",
    "٠": "0", "١": "1", "٢": "2", "٣": "3", "٤": "4",
    "٥": "5", "٦": "6", "٧": "7", "٨": "8", "٩": "9",
})

_HARAKAT_RE = re.compile(r"[\u0610-\u061A\u064B-\u065F\u0670\u06D6-\u06ED]")

def normalize_text(s: str) -> str:
    if not s:
        return ""
    s = unicodedata.normalize("NFKD", s)
    s = s.translate(_AR_MAP)
    s = _HARAKAT_RE.sub("", s)          # إزالة التشكيل
    s = re.sub(r"\s+", " ", s).strip()  # مسافات موحّدة
    return s

def make_student_key(name: str, national_id: str | None = None) -> str:
    """
    مفتاح ثابت للطالب:
    - إن وُجد رقم هوية (يمكنك تمريره لاحقًا) نستخدمه.
    - وإلا نطبّع الاسم ونحوّله لمعرّف URL آمن (يبقى عربيًا).
    """
    if national_id:
        return national_id.strip()
    n = normalize_text(name)
    # تحويل إلى معرّف URL آمن (أحرف عربية/أرقام وشرطات)
    key = re.sub(r"[^0-9\u0621-\u064A]+", "-", n).strip("-")
    return key
