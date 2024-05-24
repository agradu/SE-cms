from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .models import Person
from orders.models import Order
from django.core.paginator import Paginator
from django.utils import timezone

# Create your views here.


@login_required(login_url="/login/")
def c_clients(request):
    # search elements
    search = ""
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) < 3:
            search = ""
    # CLIENTS
    filtered_persons = Person.objects.filter(
        Q(firstname__icontains=search)
        | Q(lastname__icontains=search)
        | Q(company_name__icontains=search)
    ).order_by("firstname")[:30]
    selected_clients = []
    for person in filtered_persons:
        person_total_orders = Order.objects.filter(person=person, is_client=True).count()
        client = {"client": person, "total_orders": person_total_orders}
        selected_clients.append(client)
    page = request.GET.get("page")
    paginator = Paginator(selected_clients, 5)
    clients_on_page = paginator.get_page(page)
    return render(
        request,
        "clients/c_clients.html",
        {"selected_clients": clients_on_page, "search": search},
    )


@login_required(login_url="/login/")
def p_providers(request):
    # search elements
    search_name = ""
    search_service = ""
    if request.method == "POST":
        search_name = request.POST.get("search_name")
        search_service = request.POST.get("search_service")
    # PROVIDERS
    filtered_persons = (
        Person.objects.filter(
            Q(firstname__icontains=search_name)
            | Q(lastname__icontains=search_name)
            | Q(company_name__icontains=search_name)
        )
        .filter(services__icontains=search_service)
        .exclude(services='')
        .order_by("firstname")[:30]
    )
    selected_providers = []
    for person in filtered_persons:
        person_total_orders = Order.objects.filter(person=person, is_client=False).count()
        provider = {"provider": person, "total_orders": person_total_orders}
        selected_providers.append(provider)
    page = request.GET.get("page")
    paginator = Paginator(selected_providers, 5)
    providers_on_page = paginator.get_page(page)
    return render(
        request,
        "providers/p_providers.html",
        {
            "selected_providers": providers_on_page,
            "search_name": search_name,
            "search_service": search_service,
        },
    )


@login_required(login_url="/login/")
def person_detail(request, person_id):
    date_now = timezone.now()
    if person_id != 0:
        person = get_object_or_404(Person, id=person_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            person.firstname = request.POST.get("firstname")
            person.lastname = request.POST.get("lastname")
            person.entity = request.POST.get("entity")
            person.gender = request.POST.get("gender")
            person.identity_card = request.POST.get("identity_card")
            person.company_name = request.POST.get("company_name")
            person.company_tax_code = request.POST.get("company_tax_code")
            person.company_iban = request.POST.get("company_iban")
            person.email = request.POST.get("email")
            person.phone = request.POST.get("phone")
            person.address = request.POST.get("address")
            person.services = request.POST.get("services")
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
                        firstname=firstname,
                        lastname=lastname,
                        company_name=company_name,
                        entity=request.POST.get("entity"),
                        gender=request.POST.get("gender"),
                        identity_card=request.POST.get("identity_card"),
                        company_tax_code=request.POST.get("company_tax_code"),
                        company_iban=request.POST.get("company_iban"),
                        phone=request.POST.get("phone"),
                        address=request.POST.get("address"),
                        email=request.POST.get("email"),
                        services=request.POST.get("services"),
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
    return render(request, "clients/person.html", {"person": person, "update": update})
