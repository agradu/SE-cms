from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib import messages
from django.db.models.functions import Lower

from datetime import datetime, timedelta

from .models import Appointment
from persons.models import Person
from core.models import Status
from orders.models import Order
from common.helpers import Unaccent


def _parse_date_range(reg_start: str, reg_end: str):
    """
    Returnează (start_dt, end_dt_inclusive, reg_start_str, reg_end_str).
    """
    now = timezone.localtime()
    default_start = now - timedelta(days=3)
    default_end = now + timedelta(days=10)

    default_reg_start = default_start.strftime("%Y-%m-%d")
    default_reg_end = default_end.strftime("%Y-%m-%d")

    reg_start = (reg_start or default_reg_start).strip()
    reg_end = (reg_end or default_reg_end).strip()

    try:
        start_naive = datetime.strptime(reg_start, "%Y-%m-%d")
        end_naive = datetime.strptime(reg_end, "%Y-%m-%d")

        start = timezone.make_aware(start_naive)
        end = timezone.make_aware(end_naive).replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end, reg_start, reg_end
    except Exception:
        # fallback safe
        start = default_start
        end = default_end.replace(hour=23, minute=59, second=59, microsecond=0)
        return start, end, default_reg_start, default_reg_end


@login_required(login_url="/login/")
def appointments(request):
    # Acceptăm GET/POST pentru căutare
    search = (request.GET.get("search") if request.method == "GET" else request.POST.get("search")) or ""
    search = search.strip()

    reg_start_in = (request.GET.get("reg_start") if request.method == "GET" else request.POST.get("reg_start")) or ""
    reg_end_in = (request.GET.get("reg_end") if request.method == "GET" else request.POST.get("reg_end")) or ""

    filter_start, filter_end, reg_start, reg_end = _parse_date_range(reg_start_in, reg_end_in)

    qs = (
        Appointment.objects
        .select_related("person", "with_person", "order", "status", "created_by", "modified_by")
        .annotate(
            person_firstname_unaccent=Unaccent(Lower("person__firstname")),
            person_lastname_unaccent=Unaccent(Lower("person__lastname")),
            person_company_unaccent=Unaccent(Lower("person__company_name")),
            with_firstname_unaccent=Unaccent(Lower("with_person__firstname")),
            with_lastname_unaccent=Unaccent(Lower("with_person__lastname")),
            with_company_unaccent=Unaccent(Lower("with_person__company_name")),
        )
        .filter(schedule__gte=filter_start, schedule__lte=filter_end)
    )

    if search:
        s = search.lower()
        qs = qs.filter(
            Q(person_firstname_unaccent__icontains=s) |
            Q(person_lastname_unaccent__icontains=s) |
            Q(person_company_unaccent__icontains=s) |
            Q(with_firstname_unaccent__icontains=s) |
            Q(with_lastname_unaccent__icontains=s) |
            Q(with_company_unaccent__icontains=s)
        )

    filtered_appointments = qs.order_by("schedule")

    page = request.GET.get("page")
    paginator = Paginator(filtered_appointments, 10)
    appointments_on_page = paginator.get_page(page)

    return render(
        request,
        "appointments/appointments.html",
        {
            "selected_appointments": appointments_on_page,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        }
    )


@login_required(login_url="/login/")
def appointment(request, appointment_id):
    # Statusurile folosite de tine (2,6)
    statuses = Status.objects.filter(id__in=(2, 6)).order_by("id")

    appointment_obj = None
    client = None
    provider = None
    clients = []
    providers = []
    orders = []
    update = ""

    now = timezone.localtime()

    if int(appointment_id) > 0:
        appointment_obj = get_object_or_404(
            Appointment.objects.select_related("person", "with_person", "order", "status"),
            id=appointment_id
        )
        client = appointment_obj.person
        provider = appointment_obj.with_person

        if appointment_obj.person_id:
            orders = list(
                Order.objects.filter(person_id=appointment_obj.person_id).order_by("-deadline")[:5]
            )

        if request.method == "POST":
            form = request.POST

            # --- searches ---
            c_search = form.get("c_search", "").strip()
            if len(c_search) > 2:
                clients = Person.objects.filter(
                    Q(firstname__icontains=c_search) |
                    Q(lastname__icontains=c_search) |
                    Q(company_name__icontains=c_search)
                )[:25]

            p_search = form.get("p_search", "").strip()
            if len(p_search) > 2:
                providers = Person.objects.filter(
                    Q(firstname__icontains=p_search) |
                    Q(lastname__icontains=p_search) |
                    Q(company_name__icontains=p_search)
                )[:25]

            # --- set client/provider ---
            new_client_id = form.get("new_client")
            if new_client_id:
                client = Person.objects.filter(id=new_client_id).first()
                appointment_obj.person = client

            new_provider_id = form.get("new_provider")
            if new_provider_id:
                provider = Person.objects.filter(id=new_provider_id).first()
                appointment_obj.with_person = provider

            # --- update fields ---
            if "description" in form:
                appointment_obj.description = form.get("description", "")

                scheduled_date = form.get("scheduled_date")
                scheduled_time = form.get("scheduled_time")
                try:
                    scheduled_naive = datetime.strptime(f"{scheduled_date} {scheduled_time}", "%Y-%m-%d %H:%M")
                    appointment_obj.schedule = timezone.make_aware(scheduled_naive)
                except Exception:
                    appointment_obj.schedule = now

                order_id = form.get("order")
                if order_id:
                    appointment_obj.order = Order.objects.filter(id=order_id).first()

                status_id = form.get("status")
                if status_id:
                    appointment_obj.status = Status.objects.filter(id=status_id).first() or Status.objects.get(id=2)
                else:
                    appointment_obj.status = Status.objects.get(id=2)

            # audit
            appointment_obj.modified_by = request.user
            appointment_obj.modified_at = now
            appointment_obj.save()

            update = "Successfully updated."
            messages.success(request, update)

    else:
        # create new appointment (minim) – creezi ori cu client, ori cu provider
        if request.method == "POST":
            form = request.POST

            c_search = form.get("c_search", "").strip()
            if len(c_search) > 2:
                clients = Person.objects.filter(
                    Q(firstname__icontains=c_search) |
                    Q(lastname__icontains=c_search) |
                    Q(company_name__icontains=c_search)
                )[:25]

            p_search = form.get("p_search", "").strip()
            if len(p_search) > 2:
                providers = Person.objects.filter(
                    Q(firstname__icontains=p_search) |
                    Q(lastname__icontains=p_search) |
                    Q(company_name__icontains=p_search)
                )[:25]

            new_client_id = form.get("new_client")
            new_provider_id = form.get("new_provider")

            if new_client_id:
                client = Person.objects.filter(id=new_client_id).first()
                if not client:
                    messages.error(request, "Client not found.")
                else:
                    appointment_obj = Appointment.objects.create(
                        created_by=request.user,
                        modified_by=request.user,
                        person=client,
                        schedule=now,
                        status=Status.objects.get(id=2),
                    )
                    messages.success(request, "New appointment created successfully.")
                    return redirect("appointment", appointment_id=appointment_obj.id)

            if new_provider_id:
                provider = Person.objects.filter(id=new_provider_id).first()
                if not provider:
                    messages.error(request, "Provider not found.")
                else:
                    appointment_obj = Appointment.objects.create(
                        created_by=request.user,
                        modified_by=request.user,
                        with_person=provider,
                        schedule=now,
                        status=Status.objects.get(id=2),
                    )
                    messages.success(request, "New appointment created successfully.")
                    return redirect("appointment", appointment_id=appointment_obj.id)

    return render(
        request,
        "appointments/appointment.html",
        {
            "appointment": appointment_obj or "",
            "clients": clients,
            "client": client,
            "providers": providers,
            "provider": provider,
            "orders": orders,
            "statuses": statuses,
            "update": update,
        }
    )
