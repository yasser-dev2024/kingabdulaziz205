from .models import NewsTicker

def active_news_ticker(request):
    """
    يرجّع آخر شريط إخباري مرئي (أو None) إلى المتغير: news_ticker
    يُستخدم في القوالب دون الحاجة لأي استدعاء في الفيوز.
    """
    try:
        obj = NewsTicker.objects.filter(is_active=True).order_by("-created_at").first()
        if obj and obj.is_visible:
            return {"news_ticker": obj}
    except Exception:
        pass
    return {"news_ticker": None}
