from django.shortcuts import render, redirect

def home_view(request):
    # لو المستخدم مسجّل دخول، ادخله مباشرة على صفحة الإحالات
    if request.user.is_authenticated:
        return redirect('referrals:index')
    # لو غير مسجّل، اعرض صفحة ترحيب بسيطة
    return render(request, 'home/index.html')
