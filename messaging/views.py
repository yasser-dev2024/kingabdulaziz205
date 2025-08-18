# messaging/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404
from django.http import HttpResponseForbidden
from django.db.models import Q
from django.utils import timezone

# لا نستخدم django.contrib.messages لتفادي الالتباس مع app messaging
from accounts.models import Profile

# ————— محاولة استيراد نموذج الرسالة (Message/Thread/Conversation) —————
try:
    from .models import Message as Msg
except Exception:
    try:
        from .models import Thread as Msg
    except Exception:
        from .models import Conversation as Msg


# ===================== Helpers =====================

def _is_manager(user):
    """مدير المدرسة = is_staff أو ملفه الشخصي role == 'مدير المدرسة'."""
    try:
        return bool(user.is_staff or (getattr(user, "profile", None) and user.profile.role == "مدير المدرسة"))
    except Profile.DoesNotExist:
        return bool(user.is_staff)


def _field_names(model):
    try:
        return {f.name for f in model._meta.get_fields()}
    except Exception:
        return set()


def _get_field(model, name):
    try:
        return model._meta.get_field(name)
    except Exception:
        return None


def _pick_one(model, candidates, default=None):
    """اختر أول اسم حقل موجود من قائمة مرشحّة."""
    names = _field_names(model)
    for c in candidates:
        if c in names:
            return c
    return default


def _fk_id(obj, name):
    """يرجع المعرّف من FK سواء كان name أو name_id."""
    if not name:
        return None
    if hasattr(obj, f"{name}_id"):
        return getattr(obj, f"{name}_id")
    val = getattr(obj, name, None)
    return getattr(val, "id", None)


# ——— تحديد الحقول على نموذج الرسالة ———
MSG_AUTHOR_F = _pick_one(Msg, ["author", "sender", "from_user", "created_by", "user"])
MSG_CREATED_F = _pick_one(Msg, ["created_at", "created", "timestamp", "created_on", "sent_at", "updated_at"], default="id")
MSG_THREAD_F = _pick_one(Msg, ["thread", "conversation", "parent", "topic"])

# ——— نموذج الـ Thread المرتبط ———
ThreadModel = None
if MSG_THREAD_F:
    fld = _get_field(Msg, MSG_THREAD_F)
    if fld is not None and hasattr(fld, "remote_field") and fld.remote_field:
        ThreadModel = fld.remote_field.model

# مرشّحات حقول المستخدم على الـ Thread (FKs)
THREAD_USER_FKS = [
    "recipient", "to_user", "target", "receiver", "assigned_to", "assignee",
    "owner", "created_by", "user", "counselor", "teacher",
]

# مرشّحات علاقات M2M على الـ Thread (مجموعات مشاركين)
THREAD_M2M_USER = [
    "participants", "members", "users", "watchers", "involved",
]

# حقول المقروء المحتملة على الرسالة
MSG_READ_AT_F = _pick_one(Msg, ["recipient_read_at", "read_at", "seen_at"])
MSG_IS_READ_F = _pick_one(Msg, ["is_read", "read", "seen"])


def _thread_user_Q(user):
    """
    يبني Q لمطابقة الرسائل التي ينتمي موضوعها (Thread) للمستخدم عبر
    أي FK أو M2M متاح فعليًا على الـ Thread.
    """
    if not (ThreadModel and MSG_THREAD_F):
        return Q()  # لا شيء نضيفه

    thread_names = _field_names(ThreadModel)
    q = Q()

    # FKs
    for name in THREAD_USER_FKS:
        if name in thread_names:
            q |= Q(**{f"{MSG_THREAD_F}__{name}": user})

    # M2M
    for name in THREAD_M2M_USER:
        if name in thread_names:
            # في Django: filter(field=user) يعمل لكل من FK و M2M
            q |= Q(**{f"{MSG_THREAD_F}__{name}": user})

    return q


def _message_visible_by(user, obj):
    """يتحقق من قابلية رؤية رسالة واحدة."""
    if _is_manager(user):
        return True
    # مؤلف الرسالة؟
    if MSG_AUTHOR_F and _fk_id(obj, MSG_AUTHOR_F) == user.id:
        return True
    # عضو في الـ Thread؟
    if ThreadModel and MSG_THREAD_F:
        # نبني فحصًا سريعًا ضد الحقول الشائعة
        t = getattr(obj, MSG_THREAD_F, None)
        if t:
            names = _field_names(ThreadModel)
            for n in THREAD_USER_FKS:
                if n in names and _fk_id(t, n) == user.id:
                    return True
            for n in THREAD_M2M_USER:
                if n in names:
                    try:
                        m2m = getattr(t, n)
                        if m2m.filter(id=user.id).exists():
                            return True
                    except Exception:
                        pass
    return False


def _mark_read_for_viewer(obj, user):
    """
    تعليم الرسالة كمقروءة بشكل تحفظي:
    - نحدّث فقط إذا لم يكن القارئ هو المؤلف (غالبًا هو المستلم/الطرف الآخر).
    - لا نفعل شيئًا إن لم توجد حقول مقروء.
    """
    try:
        if MSG_AUTHOR_F and _fk_id(obj, MSG_AUTHOR_F) == user.id:
            return  # الكاتب نفسه، لا نغيّر
        updated = []
        if MSG_READ_AT_F and getattr(obj, MSG_READ_AT_F, None) in (None, False):
            setattr(obj, MSG_READ_AT_F, timezone.now())
            updated.append(MSG_READ_AT_F)
        if MSG_IS_READ_F is not None:
            cur = getattr(obj, MSG_IS_READ_F, None)
            if cur is None or (isinstance(cur, bool) and not cur):
                setattr(obj, MSG_IS_READ_F, True)
                updated.append(MSG_IS_READ_F)
        if updated:
            obj.save(update_fields=list(set(updated)))
    except Exception:
        # لا نكسر الصفحة لو فشل الحفظ
        pass


# ===================== Views =====================

@login_required
def inbox(request):
    """
    قائمة المراسلات:
      - المدير يرى جميع الرسائل.
      - غير المدير يرى رسائله المؤلّفة + أي رسالة ضمن Thread يشارك فيه.
    يحافظ على نفس اسم السياق: items, scope, counts.
    """
    qs = Msg.objects.all().order_by(f"-{MSG_CREATED_F}")

    # select_related لتحسين الأداء على الحقول الموجودة
    to_select = []
    for name in (MSG_AUTHOR_F, MSG_THREAD_F):
        f = _get_field(Msg, name) if name else None
        if f is not None and getattr(f, "is_relation", False) and not getattr(f, "many_to_many", False):
            to_select.append(name)
    if to_select:
        qs = qs.select_related(*to_select)

    if _is_manager(request.user):
        qs_all = qs
        qs_sent = qs if not MSG_AUTHOR_F else qs.filter(**{MSG_AUTHOR_F: request.user})
        # "inbox" للمدير = كل شيء
        qs_inbox = qs
    else:
        q_threads = _thread_user_Q(request.user)
        q_auth = Q()
        if MSG_AUTHOR_F:
            q_auth = Q(**{MSG_AUTHOR_F: request.user})

        qs_all = qs.filter(q_threads | q_auth)
        qs_sent = qs.filter(q_auth) if MSG_AUTHOR_F else qs.none()
        # الوارد = ما في الـ Thread للمستخدم وليس من كتابته (إن توفّر حقل المؤلف)
        if MSG_AUTHOR_F:
            qs_inbox = qs.filter(q_threads).exclude(**{MSG_AUTHOR_F: request.user})
        else:
            qs_inbox = qs.filter(q_threads)

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

    # خريطة مبسطة للمقروء/غير المقروء
    read_map = {}
    for m in items:
        # غير المقروء إذا وُجد حقل ويدل على ذلك
        unread = False
        if MSG_READ_AT_F:
            unread = (getattr(m, MSG_READ_AT_F, None) is None)
        elif MSG_IS_READ_F:
            unread = not bool(getattr(m, MSG_IS_READ_F, False))

        # اتجاه الرسالة بالنسبة للمستخدم (اختياري للقالب)
        if MSG_AUTHOR_F and _fk_id(m, MSG_AUTHOR_F) == request.user.id:
            d = "out"
        elif _is_manager(request.user):
            d = "mgr"
        else:
            d = "in"

        read_map[getattr(m, "pk", None)] = {"unread": unread, "dir": d}

    return render(request, "messaging/index.html", {
        "items": items,
        "scope": scope,
        "counts": counts,
        "is_manager": _is_manager(request.user),
        "read_map": read_map,
    })


# اسم بديل لو كانت الروابط القديمة تستخدم index بدل inbox
@login_required
def index(request):
    return inbox(request)


@login_required
def thread_detail(request, pk: int):
    """
    تفاصيل رسالة واحدة:
      - المدير يمكنه عرض أي رسالة.
      - نعلّم “مقروء” للمشاهد إذا لم يكن المؤلف نفسه.
    """
    obj = get_object_or_404(Msg.objects.all(), pk=pk)
    if not _message_visible_by(request.user, obj):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه المراسلة.")
    _mark_read_for_viewer(obj, request.user)
    return render(request, "messaging/detail.html", {
        "t": obj,
        "is_manager": _is_manager(request.user),
    })


# اسم بديل لو كانت الروابط تستخدم detail
@login_required
def detail(request, pk: int):
    return thread_detail(request, pk)


# نحافظ على الأسماء التي يستوردها urls.py بدون العبث بمنطقك الحالي لإنشاء/رد/إغلاق
@login_required
def new_thread(request):
    try:
        return render(request, "messaging/new.html", {})
    except Exception:
        return inbox(request)


@login_required
def reply_thread(request, pk: int):
    # إعادة استخدام تفاصيل الرسالة للحفاظ على المسارات
    return thread_detail(request, pk)


@login_required
def close_thread(request, pk: int):
    # إعادة استخدام التفاصيل، ولا نمس منطقك الأصلي
    return thread_detail(request, pk)
