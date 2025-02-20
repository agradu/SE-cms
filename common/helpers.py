from datetime import datetime, timedelta
from django.utils import timezone
from django.core.paginator import Paginator
from django.db.models import Q
from django.utils.dateparse import parse_date

def get_date_range(request, default_days=10):
    """Gets and parses the start and end dates from the request."""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = date_now - timedelta(days=default_days)

    reg_start = request.GET.get("r_start", date_before.strftime("%Y-%m-%d"))
    reg_end = request.GET.get("r_end", date_now.strftime("%Y-%m-%d"))

    if request.method == "POST":
        reg_start = request.POST.get("reg_start", reg_start)
        reg_end = request.POST.get("reg_end", reg_end)

    parsed_start = parse_date(reg_start) or date_before.date()
    parsed_end = parse_date(reg_end) or date_now.date()

    filter_start = timezone.make_aware(datetime.combine(parsed_start, datetime.min.time()))
    filter_end = timezone.make_aware(datetime.combine(parsed_end, datetime.max.time())).replace(
        hour=23, minute=59, second=59, microsecond=0
    )

    return filter_start, filter_end, reg_start, reg_end


def get_search_params(request):
    """Extract and validate search terms from the request."""
    search_client = request.GET.get("client", "").strip()
    search_description = request.GET.get("description", "").strip()

    if request.method == "POST":
        search_client = request.POST.get("search_client", "").strip()
        search_description = request.POST.get("search_description", "").strip()

    search_client = search_client if len(search_client) >= 3 else ""
    search_description = search_description if len(search_description) >= 3 else ""

    return search_client, search_description


def paginate_objects(request, object_list, per_page=10):
    """Applies pagination to a list of objects."""
    page = request.GET.get("page", 1)
    paginator = Paginator(object_list, per_page)
    return paginator.get_page(page)
