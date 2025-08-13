from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.contrib import messages
from django.db.models import Q
from django.shortcuts import render, redirect, get_object_or_404
from django.views.decorators.http import require_http_methods
from django.http import HttpResponseForbidden
from .models import Thread, Message, MessageAttachment

ALLOWED_EXTS = {".pdf", ".png", ".jpg", ".jpeg", ".doc", ".docx"}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10MB
MAX_FILES = 5

def _can_view(user, t: Thread):
    return user.is_staff or user == t.sender or user == t.recipient

@login_required
def inbox(request):
    items = Thread.objects.filter(Q(sender=request.user) | Q(recipient=request.user)).select_related("sender", "recipient")
    return render(request, "messaging/index.html", {"items": items})

@login_required
@require_http_methods(["GET", "POST"])
def new_thread(request):
    if request.method == "POST":
        to_id   = request.POST.get("to")
        subject = (request.POST.get("subject") or "").strip()
        content = (request.POST.get("content") or "").strip()
        files   = request.FILES.getlist("attachments")

        errs = {}
        # المستلم
        try:
            to_user = User.objects.get(pk=int(to_id), is_active=True)
        except Exception:
            errs["to"] = "المستخدم غير موجود."
            to_user = None

        if to_user and to_user.id == request.user.id:
            errs["to"] = "لا يمكنك مراسلة نفسك."

        if len(subject) < 4:
            errs["subject"] = "أدخل موضوعًا مناسبًا (4 أحرف على الأقل)."

        if not content and not files:
            errs["content"] = "أدخل رسالة أو قم بإرفاق ملفات."

        if len(files) > MAX_FILES:
            errs["attachments"] = f"يمكن رفع {MAX_FILES} ملفات كحد أقصى."

        checked = []
        for f in files:
            ext = "." + f.name.split(".")[-1].lower()
            if ext not in ALLOWED_EXTS:
                errs["attachments"] = "نوع ملف غير مسموح."
                break
            if f.size > MAX_FILE_SIZE:
                errs["attachments"] = "حجم الملف يتجاوز 10MB."
                break
            checked.append(f)

        if errs:
            users = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
            return render(request, "messaging/new.html", {"errors": errs, "form": request.POST, "users": users})

        t = Thread.objects.create(subject=subject, sender=request.user, recipient=to_user)
        msg = Message.objects.create(thread=t, author=request.user, content=content)
        for f in checked:
            MessageAttachment.objects.create(message=msg, file=f, uploaded_by=request.user)

        messages.success(request, "تم إنشاء المراسلة بنجاح.")
        return redirect("messaging:detail", pk=t.pk)

    users = User.objects.filter(is_active=True).exclude(id=request.user.id).order_by("username")
    return render(request, "messaging/new.html", {"users": users})

@login_required
def thread_detail(request, pk: int):
    t = get_object_or_404(Thread, pk=pk)
    if not _can_view(request.user, t):
        return HttpResponseForbidden("لا تملك صلاحية عرض هذه المراسلة.")
    msgs = t.messages.select_related("author").prefetch_related("files")
    return render(request, "messaging/detail.html", {"t": t, "msgs": msgs})

@login_required
@require_http_methods(["POST"])
def reply_thread(request, pk: int):
    t = get_object_or_404(Thread, pk=pk)
    if not _can_view(request.user, t):
        return HttpResponseForbidden("لا تملك صلاحية الرد على هذه المراسلة.")

    content = (request.POST.get("content") or "").strip()
    files   = request.FILES.getlist("attachments")

    if t.status == "CLOSED":
        messages.error(request, "المراسلة مغلقة.")
        return redirect("messaging:detail", pk=t.pk)

    if not content and not files:
        messages.error(request, "أدخل رسالة أو أرفق ملفات.")
        return redirect("messaging:detail", pk=t.pk)

    if len(files) > MAX_FILES:
        messages.error(request, f"يمكن رفع {MAX_FILES} ملفات كحد أقصى.")
        return redirect("messaging:detail", pk=t.pk)

    checked = []
    for f in files:
        ext = "." + f.name.split(".")[-1].lower()
        if ext not in ALLOWED_EXTS:
            messages.error(request, "نوع ملف غير مسموح.")
            return redirect("messaging:detail", pk=t.pk)
        if f.size > MAX_FILE_SIZE:
            messages.error(request, "حجم الملف يتجاوز 10MB.")
            return redirect("messaging:detail", pk=t.pk)
        checked.append(f)

    msg = Message.objects.create(thread=t, author=request.user, content=content)
    for f in checked:
        MessageAttachment.objects.create(message=msg, file=f, uploaded_by=request.user)

    messages.success(request, "تم إرسال الرد.")
    return redirect("messaging:detail", pk=t.pk)

@login_required
@require_http_methods(["POST"])
def close_thread(request, pk: int):
    t = get_object_or_404(Thread, pk=pk)
    if not _can_view(request.user, t):
        return HttpResponseForbidden("لا تملك صلاحية إغلاق هذه المراسلة.")
    t.status = "CLOSED"
    t.save()
    messages.success(request, "تم إغلاق المراسلة.")
    return redirect("messaging:detail", pk=t.pk)
