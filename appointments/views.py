from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .models import Appointment
from persons.models import Person
from django.core.paginator import Paginator
from django.utils import timezone

# Create your views here.


@login_required(login_url="/login/")
def appointments(request):
    # search elements
    search = ""
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) < 3:
            search = ""

    # APPOINTMENTS
    filtered_appointments = Appointment.objects.filter(
        Q(person__firstname__icontains=search)
        | Q(person__lastname__icontains=search)
        | Q(person__company_name__icontains=search)
    ).order_by("schedule")[:30]
    """
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    def get_sort_key(x):
        if sort == "client":
            return x["person"].firstname
        elif sort == "provider":
            return x["with_person"].firstname
        elif sort == "assignee":
            return x["modified_by"].first_name
        elif sort == "registered":
            return x["created_at"]
        elif sort == "modified":
            return x["modified_at"]
        elif sort == "scheduled":
            return x["schedule"]
        else:
            return x["schedule"]
    filtered_appointments = sorted(filtered_appointments, key=get_sort_key, reverse=(sort != "person" and sort != "with_person"))
    """
    page = request.GET.get("page")
    paginator = Paginator(filtered_appointments, 10)
    appointments_on_page = paginator.get_page(page)
    return render(
        request,
        "appointments/appointments.html",
        {"selected_appointments": appointments_on_page, "search": search},
    )
