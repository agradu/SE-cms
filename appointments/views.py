from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .models import Appointment
from persons.models import Person
from services.models import Status
from orders.models import Order
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

# Create your views here.


@login_required(login_url="/login/")
def appointments(request):
    # search elements
    search = ""
    # APPOINTMENTS
    filtered_appointments = Appointment.objects.order_by("schedule")[:30]
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) > 2:
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

@login_required(login_url="/login/")
def appointment(request, appointment_id):
    # Default parts
    statuses = Status.objects.filter(id__in=(2,6)).order_by("id")
    appointment = ""
    client = None
    clients = []
    provider = None
    providers = []
    orders = []
    date_now = timezone.now()
    if appointment_id > 0:
        appointment = get_object_or_404(Appointment, id=appointment_id)
        orders = Order.objects.filter(person=appointment.person).order_by("-deadline")[:5]
        if request.method == "POST":
            if "c_search" in request.POST:
                c_search = request.POST.get("c_search")
                if len(c_search) > 2:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=c_search)
                        | Q(lastname__icontains=c_search)
                        | Q(company_name__icontains=c_search)
                    )
            if "p_search" in request.POST:
                p_search = request.POST.get("p_search")
                if len(p_search) > 2:
                    providers = Person.objects.filter(
                        Q(firstname__icontains=p_search)
                        | Q(lastname__icontains=p_search)
                        | Q(company_name__icontains=p_search)
                    )
            if "new_client" in request.POST:
                client_id = request.POST.get("new_client")
                try:
                    client = Person.objects.get(id=client_id)
                    appointment.person = client
                except:
                    client = None
            if "new_provider" in request.POST:
                provider_id = request.POST.get("new_provider")
                try:
                    provider = Person.objects.get(id=provider_id)
                    appointment.with_person = provider
                except:
                    provider = None
            if "description" in request.POST:
                appointment.description = request.POST.get("description")
                scheduled_date = request.POST.get("scheduled_date")
                scheduled_time = request.POST.get("scheduled_time")
                try:
                    scheduled_naive = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
                    appointment.schedule = timezone.make_aware(scheduled_naive)
                except:
                    appointment.schedule = date_now
                order_id = request.POST.get("order")
                try:
                    order = Order.objects.get(id=order_id)
                    appointment.order = order
                except:
                    order = None
                status_id = request.POST.get("status")
                try:
                    status = Status.objects.get(id=status_id)
                    appointment.status = status
                except:
                    status = Status.objects.get(id=2)
            appointment.save()
            update = "Succesfuly updated"
        else:
            update = ""
    else:
        if request.method == "POST":
            if "c_search" in request.POST:
                c_search = request.POST.get("c_search")
                if len(c_search) > 2:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=c_search)
                        | Q(lastname__icontains=c_search)
                        | Q(company_name__icontains=c_search)
                    )
            if "p_search" in request.POST:
                p_search = request.POST.get("p_search")
                if len(p_search) > 2:
                    providers = Person.objects.filter(
                        Q(firstname__icontains=p_search)
                        | Q(lastname__icontains=p_search)
                        | Q(company_name__icontains=p_search)
                    )
            if "new_client" in request.POST:
                client_id = request.POST.get("new_client")
                try:
                    client = Person.objects.get(id=client_id)
                    appointment = Appointment(
                        modified_by = request.user,
                        person = client,
                        created_by = request.user,
                        schedule = date_now,
                    )
                    appointment.save()
                    update = "New appointment created"
                    return redirect("appointment", appointment_id = appointment.id)
                except:
                    client = None
            if "new_provider" in request.POST:
                provider_id = request.POST.get("new_provider")
                try:
                    provider = Person.objects.get(id=provider_id)
                    appointment = Appointment(
                        modified_by = request.user,
                        with_person = provider,
                        created_by = request.user,
                        schedule = date_now,
                    )
                    appointment.save()
                    update = "New appointment created"
                    return redirect("appointment", appointment_id = appointment.id)
                except:
                    provider = None
        update = ""
        
    return render(
            request,
            "appointments/appointment.html",
            {
                "appointment": appointment,
                "clients": clients,
                "client": client,
                "providers": providers,
                "provider": provider,
                "orders": orders,
                "statuses": statuses,
                "update": update
            }
        )