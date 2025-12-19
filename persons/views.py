from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Q, Count
from django.db.models.functions import Lower
from django.core.paginator import Paginator
from django.utils import timezone
from django.contrib import messages


import random
import string
import phonenumbers

from .models import Person
from orders.models import Order
from appointments.models import Appointment
from common.helpers import Unaccent


def format_phone_number(raw_number, default_region="DE"):
    raw_number = (raw_number or "").strip()
    if not raw_number:
        return ""
    try:
        phone_obj = phonenumbers.parse(raw_number, default_region)
        if phonenumbers.is_valid_number(phone_obj):
            e164 = phonenumbers.format_number(phone_obj, phonenumbers.PhoneNumberFormat.E164)
            return e164.replace("+", "00")
        return ""
    except phonenumbers.NumberParseException:
        return ""


def _s(val: str) -> str:
    return (val or "").strip()


@login_required(login_url="/login/")
def c_clients(request):
    # search from POST or GET
    search = _s(request.POST.get("search")) or _s(request.GET.get("search"))
    base_qs = Person.objects.all()

    if len(search) > 2:
        s = search.lower()
        base_qs = (
            base_qs.annotate(
                firstname_unaccent=Unaccent(Lower("firstname")),
                lastname_unaccent=Unaccent(Lower("lastname")),
                company_unaccent=Unaccent(Lower("company_name")),
            )
            .filter(
                Q(firstname_unaccent__icontains=s)
                | Q(lastname_unaccent__icontains=s)
                | Q(company_unaccent__icontains=s)
            )
            .order_by("firstname", "lastname")[:30]
        )
    else:
        search = ""
        base_qs = base_qs.order_by("-created_at")[:30]

    # ✅ no N+1: count orders via annotation
    qs = (
        base_qs.annotate(
            total_orders=Count("order", filter=Q(order__is_client=True), distinct=True)
        )
    )

    selected_clients = [{"client": p, "total_orders": p.total_orders} for p in qs]

    paginator = Paginator(selected_clients, 10)
    clients_on_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "persons/clients/c_clients.html",
        {"selected_clients": clients_on_page, "search": search},
    )


@login_required(login_url="/login/")
def p_providers(request):
    def get_param(name):
        return _s(request.POST.get(name)) if request.method == "POST" else _s(request.GET.get(name))

    search_name = get_param("search_name")
    search_service = get_param("search_service")
    search_place = get_param("search_place")

    base_qs = Person.objects.exclude(services="")

    if len(search_name) > 2 or len(search_service) > 2 or len(search_place) > 2:
        sn = search_name.lower()
        ss = search_service.lower()
        sp = search_place.lower()

        base_qs = (
            base_qs.annotate(
                firstname_unaccent=Unaccent(Lower("firstname")),
                lastname_unaccent=Unaccent(Lower("lastname")),
                company_unaccent=Unaccent(Lower("company_name")),
                services_unaccent=Unaccent(Lower("services")),
                address_unaccent=Unaccent(Lower("address")),
            )
            .filter(
                Q(firstname_unaccent__icontains=sn)
                | Q(lastname_unaccent__icontains=sn)
                | Q(company_unaccent__icontains=sn)
            )
            .filter(services_unaccent__icontains=ss)
            .filter(address_unaccent__icontains=sp)
            .order_by("firstname", "lastname")[:30]
        )
    else:
        search_name = search_service = search_place = ""
        base_qs = base_qs.order_by("-created_at")[:30]

    # ✅ no N+1: counts via annotation
    qs = base_qs.annotate(
        total_orders=Count("order", filter=Q(order__is_client=False), distinct=True),
        total_appointments=Count("with_person_appointment", distinct=True),
    )

    # NOTE: count appointment relation name:
    # In Appointment model, with_person has related_name="with_person_%(class)s"
    # => Appointment reverse accessor on Person is "with_person_appointment"
    selected_providers = [
        {"provider": p, "total_orders": p.total_orders, "total_appointments": p.total_appointments}
        for p in qs
    ]

    paginator = Paginator(selected_providers, 10)
    providers_on_page = paginator.get_page(request.GET.get("page"))

    return render(
        request,
        "persons/providers/p_providers.html",
        {
            "selected_providers": providers_on_page,
            "search_name": search_name,
            "search_service": search_service,
            "search_place": search_place,
        },
    )


@login_required(login_url="/login/")
def person_detail(request, person_id):
    date_now = timezone.localtime()

    if int(person_id) != 0:
        person = get_object_or_404(Person, id=person_id)
        update = ""

        if request.method == "POST":
            person.firstname = _s(request.POST.get("firstname"))
            person.lastname = _s(request.POST.get("lastname"))
            person.entity = request.POST.get("entity")
            person.gender = request.POST.get("gender")
            person.identity_card = request.POST.get("identity_card")
            person.company_name = _s(request.POST.get("company_name"))
            person.company_tax_code = request.POST.get("company_tax_code")
            person.company_iban = request.POST.get("company_iban")
            person.email = request.POST.get("email")
            person.phone = format_phone_number(request.POST.get("phone"))
            person.address = _s(request.POST.get("address"))
            person.services = _s(request.POST.get("services"))

            person.modified_at = date_now
            person.modified_by = request.user

            # optional: person.full_clean()
            person.save()
            update = "Successfully updated."
            messages.success(request, update)

        return render(request, "persons/clients/person.html", {"person": person, "update": update})

    # create new
    person = ""
    update = ""

    if request.method == "POST":
        firstname = _s(request.POST.get("firstname"))
        lastname = _s(request.POST.get("lastname"))
        company_name = _s(request.POST.get("company_name"))

        if not firstname or not lastname:
            update = "First name and last name are mandatory."
            messages.error(request, update)
            return render(request, "persons/clients/person.html", {"person": person, "update": update})

        # token unique
        token = "".join(random.choices(string.ascii_letters + string.digits, k=20))
        while Person.objects.filter(token=token).exists():
            token = "".join(random.choices(string.ascii_letters + string.digits, k=20))

        existing = Person.objects.filter(
            firstname__icontains=firstname,
            lastname__icontains=lastname,
            company_name__icontains=company_name,
        ).first()

        if existing:
            person = existing
            update = f"Person {person.firstname} {person.lastname} - {person.company_name} exists. Are you sure?"
            messages.warning(request, update)
            return render(request, "persons/clients/person.html", {"person": person, "update": update})

        person = Person.objects.create(
            firstname=firstname,
            lastname=lastname,
            company_name=company_name,
            token=token,
            entity=request.POST.get("entity"),
            gender=request.POST.get("gender"),
            identity_card=request.POST.get("identity_card"),
            company_tax_code=request.POST.get("company_tax_code"),
            company_iban=request.POST.get("company_iban"),
            phone=format_phone_number(request.POST.get("phone")),
            address=_s(request.POST.get("address")),
            email=request.POST.get("email"),
            services=_s(request.POST.get("services")),
            created_at=date_now,
            created_by=request.user,
            modified_at=date_now,
            modified_by=request.user,
        )
        update = "Person created."
        messages.success(request, update)

    return render(request, "persons/clients/person.html", {"person": person, "update": update})
