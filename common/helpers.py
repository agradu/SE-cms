from datetime import datetime, timedelta
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Func
from django.utils.dateparse import parse_date
from django.db import models


def get_date_range(request, default_days=10, date_end=None):
    """
    Returnează (filter_start_dt, filter_end_dt, reg_start_str, reg_end_str)
    - Acceptă parametri atât r_start/r_end cât și reg_start/reg_end.
    - Robust la timezone.
    """
    now = timezone.localtime()

    if date_end not in (None, 0):
        # date_end poate fi datetime aware/naive
        if timezone.is_aware(date_end):
            now = timezone.localtime(date_end)
        else:
            now = timezone.make_aware(date_end)

    date_before = now - timedelta(days=default_days)

    # Acceptăm ambele variante pe GET
    reg_start = (
        request.GET.get("reg_start")
        or request.GET.get("r_start")
        or date_before.strftime("%Y-%m-%d")
    )
    reg_end = (
        request.GET.get("reg_end")
        or request.GET.get("r_end")
        or now.strftime("%Y-%m-%d")
    )

    # Pe POST la fel (acceptă ambele)
    if request.method == "POST":
        reg_start = request.POST.get("reg_start") or request.POST.get("r_start") or reg_start
        reg_end = request.POST.get("reg_end") or request.POST.get("r_end") or reg_end

    parsed_start = parse_date(reg_start) or date_before.date()
    parsed_end = parse_date(reg_end) or now.date()

    start_dt = datetime.combine(parsed_start, datetime.min.time())
    end_dt = datetime.combine(parsed_end, datetime.max.time()).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    if timezone.is_naive(start_dt):
        filter_start = timezone.make_aware(start_dt)
    else:
        filter_start = start_dt

    if timezone.is_naive(end_dt):
        filter_end = timezone.make_aware(end_dt)
    else:
        filter_end = end_dt

    return filter_start, filter_end, reg_start, reg_end


def get_search_params(request):
    """
    Returnează (search_client, search_provider, search_description)
    Min 3 caractere, altfel ''.
    """
    search_client = request.GET.get("client", "").strip()
    search_provider = request.GET.get("provider", "").strip()
    search_description = request.GET.get("description", "").strip()

    if request.method == "POST":
        search_client = request.POST.get("search_client", "").strip()
        search_provider = request.POST.get("search_provider", "").strip()
        search_description = request.POST.get("search_description", "").strip()

    if len(search_client) < 3:
        search_client = ""
    if len(search_provider) < 3:
        search_provider = ""
    if len(search_description) < 3:
        search_description = ""

    return search_client, search_provider, search_description


def paginate_objects(request, object_list, per_page=10):
    page = request.GET.get("page", 1)
    paginator = Paginator(object_list, per_page)
    return paginator.get_page(page)


class Unaccent(Func):
    function = "unaccent"
    arity = 1
    output_field = models.TextField()

    def as_sql(self, compiler, connection, **extra_context):
        sql, params = compiler.compile(self.source_expressions[0])
        # fără să mutăm output_field-ul expresiei
        return f"unaccent({sql}::text)", params
