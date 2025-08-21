# messaging/views.py
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, get_object_or_404, redirect
from django.http import HttpResponseForbidden, HttpRequest
from django.db.models import Q, Max
from django.utils import timezone
from django.contrib.auth.models import User

# لا نستخدم django.contrib.messages هنا حتى لا يحصل تعارض اسم مع التطبيق
from accounts.models import Profile

# موديلات التطبيق (بدون تغيير هيكل/أسماء)
from .models import Thread, Message, MessageAttachment


# ===================== Helpers =====================

def _is_manager(user):
    """مدير المدرسة = is_staff أو ملفه الشخصي role == 'مدير المدرسة'."""
    try:
        return bool(user.is_staff or (getattr(user, "profile", None) and user.profile.role == "مدير المدرسة"))
    except Profile.DoesNotExist:
        return bool(user.is_staff)


def _can_view_thread(user, thread: Thread) -> bool:
    """المسموح لهم برؤية المراسلة: المدير، المرسل، المستلم."""
    if _is_manager(user):
        return True
    return (thread.sender_id == user.id) or (thread.recipient_id == user.id)


def _can_reply_thread(user, thread: Thread) -> bool:
    """يستطيع الرد: أي طرف في المحادثة أو المدير."""
    return _can_view_thread(user, thread)


def _normalize_files(files):
    """
    تحقق مبسّط من الملفات (امتدادات وأحجام معقولة). لا نغيّر إعدادات المشروع.
    """
    ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
    MAX_FILE_SIZE = 10 * 1024 * 1024
    checked = []
    for f in files:
        name = (f.name or "").lower()
        ext = "." + name.split(".")[-1]
        if ext not in ALLOWED_EXTS:
            return None, "نوع ملف غير مسموح."
        if getattr(f, "size", 0) > MAX_FILE_SIZE:
            return None, "حجم الملف يتجاوز 10MB."
        checked.append(f)
    return checked, None


# ====== دوال مساعدة لقراءة الحقول بأسماء متعددة (لا نمس القوالب القديمة) ======

def _first_non_empty(*vals, default=""):
    for v in vals:
        if isinstance(v, str):
            v = v.strip()
        if v:
            return v
    return default

def _post_any(request: HttpRequest, *names, default=""):
    return _first_non_empty(*[(request.POST.get(n) or "") for n in names], default=default)

def _files_any(request: HttpRequest, *names):
    files = []
    for n in names:
        files += request.FILES.getlist(n)
    return files

def _find_user(value: str):
    """
    يقبل value كـ id أو username ويعيد مستخدمًا نشطًا أو None.
    """
    v = (value or "").strip()
    if not v:
        return None
    try:
        return User.objects.get(pk=int(v), is_active=True)
    except Exception:
        pass
    try:
        return User.objects.get(username=v, is_active=True)
    except Exception:
        return None


# ===================== Views =====================

@login_required
def inbox(request: HttpRequest):
    """
    صندوق المراسلات:
      - المدير يرى جميع المواضيع (Threads).
      - غير المدير يرى المواضيع التي هو طرفٌ فيها (مرسل/مستلم).
    يتم ترتيب القائمة فعليًا حسب أحدث رسالة داخل كل موضوع (حتى تظهر الرسائل الحديثة فورًا).
    لا نغيّر القوالب أو المسارات: items = قائمة المواضيع، read_map للاتجاه/المقروء.
    """
    # المواضيع المرئية للمستخدم
    if _is_manager(request.user):
        threads_base = Thread.objects.all().select_related("sender", "recipient")
    else:
        threads_base = Thread.objects.filter(
            Q(sender=request.user) | Q(recipient=request.user)
        ).select_related("sender", "recipient")

    scope = request.GET.get("scope", "all")
    if scope == "sent":
        threads_scoped = threads_base.filter(sender=request.user)
    elif scope == "inbox":
        threads_scoped = threads_base.filter(recipient=request.user) if not _is_manager(request.user) else threads_base.exclude(sender=request.user)
    else:
        threads_scoped = threads_base

    # آخر رسالة لكل موضوع ضمن النطاق المحدد
    last_msg_ids = (
        Message.objects.filter(thread_id__in=threads_scoped.values("id"))
        .values("thread_id")
        .annotate(last_id=Max("id"))
        .values_list("last_id", flat=True)
    )
    last_msgs = {
        m.thread_id: m
        for m in Message.objects.filter(id__in=list(last_msg_ids)).select_related("author", "thread")
    }

    # رتب المواضيع حسب تاريخ آخر رسالة (إن وُجدت) وإلا حسب updated_at ثم created_at
    items = list(threads_scoped)
    items.sort(
        key=lambda t: (
            -(last_msgs.get(t.id).id if last_msgs.get(t.id) else 0),
            -int(t.updated_at.timestamp() if t.updated_at else 0),
            -int(t.created_at.timestamp() if t.created_at else 0),
        )
    )

    # خرائط للمقروء/اتجاه الرسالة بالنسبة للمستخدم
    read_map = {}
    for t in items:
        lm = last_msgs.get(t.id)
        unread = False
        if lm:
            unread = lm.author_id != request.user.id
        if t.sender_id == request.user.id:
            d = "out"
        elif _is_manager(request.user):
            d = "mgr"
        else:
            d = "in"
        read_map[t.id] = {"unread": unread, "dir": d, "last": lm}

    counts = {
        "all": threads_base.count(),
        "sent": threads_base.filter(sender=request.user).count(),
        "inbox": (threads_base.filter(recipient=request.user).count()
                  if not _is_manager(request.user) else threads_base.exclude(sender=request.user).count()),
    }

    return render(request, "messaging/index.html", {
        "items": items,           # قائمة المواضيع مرتبة بالأحدث
        "scope": scope,
        "counts": counts,
        "is_manager": _is_manager(request.user),
        "read_map": read_map,
    })


@login_required
def index(request: HttpRequest):
    """Alias للحفاظ على أي روابط قديمة."""
    return inbox(request)


@login_required
def thread_detail(request: HttpRequest, pk: int):
    """
    تفاصيل المراسلة:
      - يقبل pk لــ Thread مباشرة.
      - ولو تم تمرير pk لرسالة، نحولها تلقائياً لموضوعها.
    """
    # حاول كونه موضوع
    thread = Thread.objects.filter(pk=pk).select_related("sender", "recipient").first()
    if thread is None:
        # ربما pk لرسالة
        msg = get_object_or_404(Message.objects.select_related("thread"), pk=pk)
        thread = msg.thread

    if not _can_view_thread(request.user, thread):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه المراسلة.")

    msgs = (
        Message.objects.filter(thread=thread)
        .select_related("author")
        .order_by("created_at", "id")
    )

    return render(request, "messaging/detail.html", {
        "t": thread,                    # للحفاظ على اسم المتغير في القالب
        "thread": thread,               # اسم إضافي صريح
        "messages": list(msgs),         # جميع الرسائل في هذا الموضوع
        "is_manager": _is_manager(request.user),
    })


@login_required
def detail(request: HttpRequest, pk: int):
    """Alias للحفاظ على أي روابط تستخدم detail."""
    return thread_detail(request, pk)


@login_required
def new_thread(request: HttpRequest):
    """
    إنشاء مراسلة جديدة:
      - يدعم أسماء حقول متعددة في القالب بدون تعديل القوالب:
        * المستلم: recipient / to_user / to / receiver / target
        * العنوان: subject / title
        * النص: content / message / text / body
        * المرفقات: files / attachments / reply_files
      - POST: إنشاء Thread + أول Message + مرفقات.
      - GET: يعرض النموذج مع قائمة المستخدمين النشطين.
    """
    recipients_qs = (
        User.objects.filter(is_active=True)
        .exclude(id=request.user.id)
        .select_related("profile")
        .order_by("profile__full_name", "username")
    )

    if request.method == "POST":
        # التقاط القيم من أسماء متعددة بدون المساس بالقوالب
        recipient_val = _post_any(request, "recipient", "to_user", "to", "receiver", "target")
        subject = _post_any(request, "subject", "title")
        content = _post_any(request, "content", "message", "text", "body")
        files = _files_any(request, "files", "attachments", "reply_files")

        recipient = _find_user(recipient_val)

        if not recipient or not subject or (not content and not files):
            return render(request, "messaging/new.html", {
                "users": recipients_qs,
                "recipients": recipients_qs,
                "all_users": recipients_qs,
                "receivers": recipients_qs,
                "form": {"recipient": recipient_val, "subject": subject, "content": content},
                "error": "أكمل الحقول المطلوبة.",
            })

        checked, err = _normalize_files(files)
        if err:
            return render(request, "messaging/new.html", {
                "users": recipients_qs,
                "recipients": recipients_qs,
                "all_users": recipients_qs,
                "receivers": recipients_qs,
                "form": {"recipient": recipient_val, "subject": subject, "content": content},
                "error": err,
            })

        # إنشاء الموضوع والرسالة الأولى
        thread = Thread.objects.create(
            subject=subject,
            sender=request.user,
            recipient=recipient,
            status="OPEN",
        )
        msg = Message.objects.create(
            thread=thread,
            author=request.user,
            content=content,
        )
        for f in checked:
            MessageAttachment.objects.create(message=msg, file=f, uploaded_by=request.user)

        # تحديث المؤشر الزمني للترتيب
        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])

        return redirect("messaging:detail", pk=thread.pk)

    # GET
    ctx = {
        "users": recipients_qs,
        "recipients": recipients_qs,
        "all_users": recipients_qs,
        "receivers": recipients_qs,
    }
    return render(request, "messaging/new.html", ctx)


@login_required
def reply_thread(request: HttpRequest, pk: int):
    """
    الرد على موضوع موجود:
      - يدعم أسماء حقول متعددة للنص/الملفات بدون المساس بالقوالب.
      - يقبل pk موضوع مباشرة أو pk رسالة (ويحوّل للموضوع).
    """
    thread = Thread.objects.filter(pk=pk).first()
    if thread is None:
        # ربما pk لرسالة
        msg = get_object_or_404(Message.objects.select_related("thread"), pk=pk)
        thread = msg.thread

    if not _can_reply_thread(request.user, thread):
        return HttpResponseForbidden("لا تملك صلاحية الرد على هذه المراسلة.")

    if request.method == "POST":
        content = _post_any(request, "content", "message", "text", "body")
        files = _files_any(request, "files", "attachments", "reply_files")

        if not content and not files:
            return redirect("messaging:detail", pk=thread.pk)

        checked, err = _normalize_files(files)
        if err:
            return redirect("messaging:detail", pk=thread.pk)

        msg = Message.objects.create(thread=thread, author=request.user, content=content)
        for f in checked:
            MessageAttachment.objects.create(message=msg, file=f, uploaded_by=request.user)

        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])

        return redirect("messaging:detail", pk=thread.pk)

    return redirect("messaging:detail", pk=thread.pk)


@login_required
def close_thread(request: HttpRequest, pk: int):
    """
    إغلاق موضوع (تغيير الحالة فقط).
    """
    thread = get_object_or_404(Thread, pk=pk)
    if not _can_reply_thread(request.user, thread):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه المراسلة.")
    thread.status = "CLOSED"
    thread.updated_at = timezone.now()
    thread.save(update_fields=["status", "updated_at"])
    return redirect("messaging:detail", pk=thread.pk)
