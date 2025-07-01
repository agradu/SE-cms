from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q, Func
from .models import Person
from orders.models import Order
from appointments.models import Appointment
from django.core.paginator import Paginator
from django.utils import timezone
import random
import string
import phonenumbers
from django.db.models.functions import Lower
from common.helpers import Unaccent


def format_phone_number(raw_number, default_region='DE'):
    try:
        # Parsează numărul – dacă nu are prefix, presupune regiunea implicită
        phone_obj = phonenumbers.parse(raw_number, default_region)
        # Verifică dacă numărul e valid
        if phonenumbers.is_valid_number(phone_obj):
            # Obține numărul în format E.164 (ex: +49123456789)
            e164 = phonenumbers.format_number(phone_obj, phonenumbers.PhoneNumberFormat.E164)
            # Convertește + în 00 și elimină orice alt caracter
            return e164.replace("+", "00")
        else:
            return ""
    except phonenumbers.NumberParseException:
        return ""

# Create your views here.

@login_required(login_url="/login/")
def c_clients(request):
    # default filter
    filtered_persons = Person.objects.order_by("-created_at")[:30]
    # finding search elements
    search = request.POST.get("search","")
    if search == "":
        search = request.GET.get("search", "")
    # limit the search string to minimum 3 chars
    if len(search) > 2:
        search = search.lower()
        filtered_persons = Person.objects.annotate(
            firstname_unaccent=Unaccent(Lower('firstname')),
            lastname_unaccent=Unaccent(Lower('lastname')),
            company_unaccent=Unaccent(Lower('company_name'))
        ).filter(
            Q(firstname_unaccent__icontains=search)
            | Q(lastname_unaccent__icontains=search)
            | Q(company_unaccent__icontains=search)
        ).order_by("firstname")[:30]
    else:
        search = ""

    selected_clients = []
    for person in filtered_persons:
        person_total_orders = Order.objects.filter(person=person, is_client=True).count()
        client = {"client": person, "total_orders": person_total_orders}
        selected_clients.append(client)
    page = request.GET.get("page")
    paginator = Paginator(selected_clients, 10)
    clients_on_page = paginator.get_page(page)
    return render(
        request,
        "persons/clients/c_clients.html",
        {"selected_clients": clients_on_page, "search": search},
    )


@login_required(login_url="/login/")
def p_providers(request):
    # default filter
    filtered_persons = Person.objects.exclude(services='').order_by("-created_at")[:30]
    # Function to simplify getting parameters from POST or GET
    def get_parameter(request, param_name):
        if request.method == 'POST':
            return request.POST.get(param_name, "")
        return request.GET.get(param_name, "")

    # Getting search parameters
    search_name = get_parameter(request, "search_name")
    search_service = get_parameter(request, "search_service")
    search_place = get_parameter(request, "search_place")
    # limit the search string to minimum 3 chars
    if len(search_name) > 2 or len(search_service) > 2 or len(search_place) > 2:
        search_name = search_name.lower()
        search_service = search_service.lower()
        search_place = search_place.lower()

        filtered_persons = (
            Person.objects.annotate(
                firstname_unaccent=Unaccent(Lower('firstname')),
                lastname_unaccent=Unaccent(Lower('lastname')),
                company_unaccent=Unaccent(Lower('company_name')),
                services_unaccent=Unaccent(Lower('services')),
                address_unaccent=Unaccent(Lower('address'))
            )
            .filter(
                Q(firstname_unaccent__icontains=search_name)
                | Q(lastname_unaccent__icontains=search_name)
                | Q(company_unaccent__icontains=search_name)
            )
            .filter(services_unaccent__icontains=search_service)
            .filter(address_unaccent__icontains=search_place)
            .exclude(services='')
            .order_by("firstname")[:30]
        )
    else:
        search_name = search_service = search_place = ""
    
    selected_providers = []
    for person in filtered_persons:
        person_total_orders = Order.objects.filter(person=person, is_client=False).count()
        person_total_appointments = Appointment.objects.filter(with_person=person).count()
        provider = {"provider": person, "total_orders": person_total_orders, "total_appointments": person_total_appointments}
        selected_providers.append(provider)
    page = request.GET.get("page")
    paginator = Paginator(selected_providers, 10)
    providers_on_page = paginator.get_page(page)
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
    date_now = timezone.now()
    if person_id != 0:
        person = get_object_or_404(Person, id=person_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            person.firstname = request.POST.get("firstname").strip()
            person.lastname = request.POST.get("lastname").strip()
            person.entity = request.POST.get("entity")
            person.gender = request.POST.get("gender")
            person.identity_card = request.POST.get("identity_card")
            person.company_name = request.POST.get("company_name").strip()
            person.company_tax_code = request.POST.get("company_tax_code")
            person.company_iban = request.POST.get("company_iban")
            person.email = request.POST.get("email")
            person.phone = format_phone_number(request.POST.get("phone"))
            person.address = request.POST.get("address").strip()
            person.services = request.POST.get("services").strip()
            person.modified_at = date_now
            person.modified_by = request.user
            person.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            firstname = request.POST.get("firstname")
            lastname = request.POST.get("lastname")
            company_name = request.POST.get("company_name")
            token = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
            while Person.objects.filter(token=token).exists():
                token = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
            if firstname != "" and lastname != "":
                try:
                    person = (
                        Person.objects.filter(firstname__icontains=firstname)
                        .filter(lastname__icontains=lastname)
                        .filter(company_name__icontains=company_name)
                        .get()
                    )
                    update = f"Person {person.firstname} {person.lastname} - {person.company_name} exists. Are you sure?"
                except:
                    update = "Person created"
                    person = Person(
                        firstname=firstname.strip(),
                        lastname=lastname.strip(),
                        company_name=company_name.strip(),
                        token=token,
                        entity=request.POST.get("entity"),
                        gender=request.POST.get("gender"),
                        identity_card=request.POST.get("identity_card"),
                        company_tax_code=request.POST.get("company_tax_code"),
                        company_iban=request.POST.get("company_iban"),
                        phone=format_phone_number(request.POST.get("phone")),
                        address=request.POST.get("address").strip(),
                        email=request.POST.get("email"),
                        services=request.POST.get("services").strip(),
                        modified_at=date_now,
                        modified_by=request.user,
                        created_at=date_now,
                        created_by=request.user,
                    )
                    person.save()
            else:
                update = "First name and last name are mandatory."
                person = ""
        else:
            update = ""
            person = ""
    return render(request, "persons/clients/person.html", {"person": person, "update": update})
