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
from django.contrib import messages

# Create your views here.


@login_required(login_url="/login/")
def appointments(request):
    # Initial date range setup
    date_before = timezone.now() - timedelta(days=3)
    date_after = timezone.now() + timedelta(days=10)
    reg_start = date_before.strftime("%Y-%m-%d")
    reg_end = date_after.strftime("%Y-%m-%d")

    # Set initial filtering dates
    filter_start = date_before
    filter_end = date_after.replace(hour=23, minute=59, second=59, microsecond=0)

    # Acceptă GET sau POST pentru căutare
    search = request.GET.get("search", "").strip() if request.method == "GET" else request.POST.get("search", "").strip()
    reg_start = request.GET.get("reg_start", reg_start) if request.method == "GET" else request.POST.get("reg_start", reg_start)
    reg_end = request.GET.get("reg_end", reg_end) if request.method == "GET" else request.POST.get("reg_end", reg_end)

    try:
        filter_start = timezone.make_aware(datetime.strptime(reg_start, "%Y-%m-%d"))
        filter_end = timezone.make_aware(datetime.strptime(reg_end, "%Y-%m-%d"))
        filter_end = filter_end.replace(hour=23, minute=59, second=59, microsecond=0)
    except ValueError:
        messages.warning(request, "Date format invalid. Showing default range.")
        filter_start = date_before
        filter_end = date_after.replace(hour=23, minute=59, second=59, microsecond=0)

    # Filter appointments
    query = Q(schedule__gte=filter_start, schedule__lte=filter_end)
    if search:
        search_query = (
            Q(person__firstname__icontains=search) |
            Q(person__lastname__icontains=search) |
            Q(person__company_name__icontains=search) |
            Q(with_person__firstname__icontains=search) |
            Q(with_person__lastname__icontains=search) |
            Q(with_person__company_name__icontains=search)
        )
        query = query & search_query

    filtered_appointments = Appointment.objects.filter(query).order_by("schedule")

    # Pagination
    page = request.GET.get("page")
    paginator = Paginator(filtered_appointments, 10)
    appointments_on_page = paginator.get_page(page)

    return render(request, "appointments/appointments.html", {
        "selected_appointments": appointments_on_page,
        "search": search,
        "reg_start": reg_start,
        "reg_end": reg_end,
    })

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
                        modified_by=request.user,
                        person=client,
                        created_by=request.user,
                        schedule=date_now,
                    )
                    appointment.save()
                    messages.success(request, "New appointment created successfully.")
                    return redirect("appointment", appointment_id=appointment.id)
                except Person.DoesNotExist:
                    messages.error(request, "Client not found. Please try again.")
                    client = None
                except Exception as e:
                    messages.error(request, f"An error occurred: {str(e)}")
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
                    messages.success(request, "New appointment created successfully.")
                    return redirect("appointment", appointment_id=appointment.id)
                except Person.DoesNotExist:
                    messages.error(request, "Provider not found. Please try again.")
                    provider = None
                except Exception as e:
                    messages.error(request, f"An error occurred: {str(e)}")
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