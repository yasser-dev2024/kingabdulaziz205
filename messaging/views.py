# messaging/views.py
from datetime import timedelta

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.db.models import Q, Max
from django.http import HttpRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from accounts.models import Profile
from .models import Message, MessageAttachment, Thread


# ===================== Helpers =====================

def _is_manager(user):
    try:
        return bool(user.is_staff or (getattr(user, "profile", None) and user.profile.role == "مدير المدرسة"))
    except Profile.DoesNotExist:
        return bool(user.is_staff)


def _can_view_thread(user, thread: Thread) -> bool:
    if _is_manager(user):
        return True
    return (thread.sender_id == user.id) or (thread.recipient_id == user.id)


def _can_reply_thread(user, thread: Thread) -> bool:
    return _can_view_thread(user, thread)


def _normalize_files(files):
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
    v = (value or "").strip()
    if not v:
        return None
    if v in {"ALL", "الكل", "*"}:
        return v
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

    items = list(threads_scoped)
    items.sort(
        key=lambda t: (
            -(last_msgs.get(t.id).id if last_msgs.get(t.id) else 0),
            -int(t.updated_at.timestamp() if t.updated_at else 0),
            -int(t.created_at.timestamp() if t.created_at else 0),
        )
    )

    now = timezone.now()
    recent_window = now - timedelta(days=3)

    read_map = {}
    for t in items:
        lm = last_msgs.get(t.id)
        unread = False
        is_new_incoming = False
        if lm:
            unread = (lm.author_id != request.user.id)
            is_new_incoming = unread and (lm.created_at >= recent_window)

        if t.sender_id == request.user.id:
            d = "out"
        elif _is_manager(request.user):
            d = "mgr"
        else:
            d = "in"

        read_map[t.id] = {
            "unread": unread,
            "dir": d,
            "last": lm,
            "is_new_incoming": is_new_incoming,
            "css": "is-new-card" if is_new_incoming else "",
            "mark": "●" if is_new_incoming else "",
        }

        setattr(t, "last_message", lm)
        setattr(t, "is_unread", unread)
        setattr(t, "is_new_incoming", is_new_incoming)
        setattr(t, "new_mark", "●" if is_new_incoming else "")
        setattr(t, "dir", d)

    counts = {
        "all": threads_base.count(),
        "sent": threads_base.filter(sender=request.user).count(),
        "inbox": (threads_base.filter(recipient=request.user).count()
                  if not _is_manager(request.user) else threads_base.exclude(sender=request.user).count()),
    }

    return render(request, "messaging/index.html", {
        "items": items,
        "scope": scope,
        "counts": counts,
        "is_manager": _is_manager(request.user),
        "read_map": read_map,
    })


@login_required
def index(request: HttpRequest):
    return inbox(request)


@login_required
def thread_detail(request: HttpRequest, pk: int):
    thread = Thread.objects.filter(pk=pk).select_related("sender", "recipient").first()
    if thread is None:
        msg = get_object_or_404(Message.objects.select_related("thread"), pk=pk)
        thread = msg.thread

    if not _can_view_thread(request.user, thread):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه المراسلة.")

    msgs_qs = (
        Message.objects.filter(thread=thread)
        .select_related("author")
        .order_by("created_at", "id")
    )
    msgs_list = list(msgs_qs)

    # حقن بدائل أسماء للتمبليت حتى تظهر الرسائل مهما كان اسم المتغير في القالب
    setattr(thread, "messages_list", msgs_list)
    ctx = {
        "t": thread,
        "thread": thread,
        "messages": msgs_list,
        "msgs": msgs_list,
        "items": msgs_list,
        "is_manager": _is_manager(request.user),
    }
    return render(request, "messaging/detail.html", ctx)


@login_required
def detail(request: HttpRequest, pk: int):
    return thread_detail(request, pk)


@login_required
def new_thread(request: HttpRequest):
    recipients_qs = (
        User.objects.filter(is_active=True)
        .exclude(id=request.user.id)
        .select_related("profile")
        .order_by("profile__full_name", "username")
    )

    if request.method == "POST":
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

        if isinstance(recipient, str) and recipient in {"ALL", "الكل", "*"}:
            targets = list(User.objects.filter(is_active=True).exclude(id=request.user.id))
            for rcpt in targets:
                thread = Thread.objects.create(subject=subject, sender=request.user, recipient=rcpt, status="OPEN")
                msg = Message.objects.create(thread=thread, author=request.user, content=content)
                for f in checked:
                    MessageAttachment.objects.create(message=msg, file=f, uploaded_by=request.user)
                thread.updated_at = timezone.now()
                thread.save(update_fields=["updated_at"])
            return redirect("messaging:inbox")

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

        thread.updated_at = timezone.now()
        thread.save(update_fields=["updated_at"])

        return redirect("messaging:detail", pk=thread.pk)

    ctx = {
        "users": recipients_qs,
        "recipients": recipients_qs,
        "all_users": recipients_qs,
        "receivers": recipients_qs,
    }
    return render(request, "messaging/new.html", ctx)


@login_required
def reply_thread(request: HttpRequest, pk: int):
    thread = Thread.objects.filter(pk=pk).first()
    if thread is None:
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
    thread = get_object_or_404(Thread, pk=pk)
    if not _can_reply_thread(request.user, thread):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه المراسلة.")
    thread.status = "CLOSED"
    thread.updated_at = timezone.now()
    thread.save(update_fields=["status", "updated_at"])
    return redirect("messaging:detail", pk=thread.pk)
