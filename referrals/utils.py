# referrals/utils.py
from __future__ import annotations
import re, unicodedata
from typing import Optional

def make_student_key(name: str, civil_id: Optional[str] = None) -> str:
    """
    يبني مفتاحًا ثابتًا للطالب:
    - إن وُجد السجل المدني نستخدمه مباشرة (حتى 64 حرفًا).
    - وإلا نولّد من الاسم: Normalize + حذف محارف غير عربية/لاتينية/أرقام + استبدال المسافات بشرطة.
    """
    key = (civil_id or "").strip()
    if key:
        return key[:64]
    s = unicodedata.normalize("NFKC", (name or "").strip())
    s = re.sub(r"\s+", "-", s)
    s = re.sub(r"[^0-9A-Za-z\u0600-\u06FF\-]", "", s)
    return s[:60]
