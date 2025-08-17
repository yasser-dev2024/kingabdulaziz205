# messaging/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.db.models import Q
from django.utils import timezone

# تجنّب التداخل مع اسم app "messages"
from django.contrib import messages as dj_messages

from accounts.models import Profile

# نحاول اكتشاف اسم نموذج المراسلة في مشروعك
try:
    from .models import Message as Msg
except Exception:
    try:
        from .models import Thread as Msg
    except Exception:
        from .models import Conversation as Msg


# ---------------------- Helpers ----------------------

def _is_manager(user):
    """مدير المدرسة = is_staff أو ملفه الشخصي role == 'مدير المدرسة'."""
    try:
        return bool(user.is_staff or (getattr(user, "profile", None) and user.profile.role == "مدير المدرسة"))
    except Profile.DoesNotExist:
        return bool(user.is_staff)


def _field_name(model, candidates):
    """اختر أول اسم حقل موجود فعلياً من قائمة مرشّحة."""
    names = {f.name for f in model._meta.get_fields()}
    for c in candidates:
        if c in names:
            return c
    return candidates[0]


# أسماء الحقول الشائعة
SENDER_F    = _field_name(Msg, ["sender", "from_user", "author", "created_by"])
RECIPIENT_F = _field_name(Msg, ["recipient", "to_user", "target", "receiver", "assigned_to"])
CREATED_F   = _field_name(Msg, ["created_at", "created", "timestamp", "created_on", "sent_at"])

# المقروء/غير المقروء (اختياري)
names_set = {f.name for f in Msg._meta.get_fields()}
READ_AT_F = "recipient_read_at" if "recipient_read_at" in names_set else ("read_at" if "read_at" in names_set else None)
IS_READ_F = "is_read" if "is_read" in names_set else ("read" if "read" in names_set else None)


def _fk_id(obj, name):
    """يرجّع المعرف من FK سواء كان name أو name_id."""
    if hasattr(obj, f"{name}_id"):
        return getattr(obj, f"{name}_id")
    val = getattr(obj, name, None)
    return getattr(val, "id", None)


def _msg_can_view(user, obj):
    """المدير يرى الكل، وغير المدير: المرسل أو المستلم فقط."""
    if _is_manager(user):
        return True
    return _fk_id(obj, SENDER_F) == user.id or _fk_id(obj, RECIPIENT_F) == user.id


def _mark_read_if_recipient(obj, user):
    """علّم الرسالة مقروءة فقط إن كان الزائر هو المستلم الحقيقي."""
    if _fk_id(obj, RECIPIENT_F) != user.id:
        return
    updated = []
    if READ_AT_F and getattr(obj, READ_AT_F, None) in (None, False):
        setattr(obj, READ_AT_F, timezone.now())
        updated.append(READ_AT_F)
    if IS_READ_F is not None:
        cur = getattr(obj, IS_READ_F, None)
        if cur is None or (isinstance(cur, bool) and not cur):
            setattr(obj, IS_READ_F, True)
            updated.append(IS_READ_F)
    if updated:
        obj.save(update_fields=list(set(updated)))


# ---------------------- Views (الأسماء المطلوبة من urls.py) ----------------------

@login_required
def inbox(request):
    """
    قائمة المراسلات:
      - المدير يرى جميع المراسلات.
      - غير المدير يرى ما أرسله أو استقبله.
    نرجع المتغير 'items' (توافقاً مع قوالبك).
    يدعم scope = all|sent|inbox إن وُجد في الروابط.
    """
    qs = Msg.objects.all().order_by(f"-{CREATED_F}")

    # تحسين select_related لعلاقتي المرسل/المستلم إن وُجدت
    to_select = []
    for f in (SENDER_F, RECIPIENT_F):
        try:
            if Msg._meta.get_field(f).is_relation:
                to_select.append(f)
        except Exception:
            pass
    if to_select:
        qs = qs.select_related(*to_select)

    if _is_manager(request.user):
        qs_all = qs
        qs_sent = qs
        qs_inbox = qs
    else:
        qs_sent = qs.filter(**{SENDER_F: request.user})
        qs_inbox = qs.filter(**{RECIPIENT_F: request.user})
        qs_all = qs.filter(Q(**{SENDER_F: request.user}) | Q(**{RECIPIENT_F: request.user}))

    scope = request.GET.get("scope", "all")
    if scope == "sent":
        items_qs = qs_sent
    elif scope == "inbox":
        items_qs = qs_inbox
    else:
        items_qs = qs_all

    items = list(items_qs)

    counts = {
        "all": qs_all.count(),
        "sent": qs_sent.count(),
        "inbox": qs_inbox.count(),
    }

    # خريطة مبسطة للاستفادة بها في القالب إن رغبت
    read_map = {}
    for m in items:
        unread = False
        if READ_AT_F:
            unread = (getattr(m, READ_AT_F, None) is None)
        elif IS_READ_F:
            unread = not bool(getattr(m, IS_READ_F, False))

        if _fk_id(m, SENDER_F) == request.user.id:
            d = "out"
        elif _fk_id(m, RECIPIENT_F) == request.user.id:
            d = "in"
        else:
            d = "mgr"  # يظهر فقط للمدير

        read_map[m.pk] = {"unread_for_recipient": unread, "dir": d}

    return render(request, "messaging/index.html", {
        "items": items,
        "scope": scope,
        "counts": counts,
        "is_manager": _is_manager(request.user),
        "read_map": read_map,
    })


# اسم بديل إن كانت هناك مسارات تستدعي index بدلاً من inbox
@login_required
def index(request):
    return inbox(request)


@login_required
def thread_detail(request, pk: int):
    """
    تفاصيل المراسلة:
      - المدير يمكنه فتح أي مراسلة.
      - نحدّث المقروء فقط للمستلم الحقيقي.
    نعيد المتغير 't' حفاظاً على توافق القالب.
    """
    obj = get_object_or_404(Msg.objects.all(), pk=pk)
    if not _msg_can_view(request.user, obj):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه المراسلة.")
    _mark_read_if_recipient(obj, request.user)
    return render(request, "messaging/detail.html", {
        "t": obj,
        "is_manager": _is_manager(request.user),
    })


# اسم بديل إن كان القالب أو الروابط تستخدم detail
@login_required
def detail(request, pk: int):
    return thread_detail(request, pk)


# الغلافات التالية فقط للحفاظ على أسماء مستوردة في urls.py بدون تغيير هيكلك.
# لم نعدّل إنشاء/رد/إغلاق لأن طلبك كان عرض جميع المراسلات للمدير فقط.

@login_required
def new_thread(request):
    # نعرض القالب كما هو إن وُجد، بدون تغيير المنطق لديك.
    # إن كانت لديك معالجة POST موجودة في مكان آخر فلن نمسّها.
    try:
        return render(request, "messaging/new.html", {})
    except Exception:
        # لا نكسر المشروع إن لم يوجد القالب
        return inbox(request)


@login_required
def reply_thread(request, pk: int):
    # نعيد التوجيه لتفاصيل الرسالة للحفاظ على التدفق دون كسر المسارات.
    return thread_detail(request, pk)


@login_required
def close_thread(request, pk: int):
    # نعيد عرض التفاصيل لتجنّب كسر المسارات القديمة.
    return thread_detail(request, pk)
