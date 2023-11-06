from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .models import Person
from orders.models import Order
from django.core.paginator import Paginator

# Create your views here.

@login_required(login_url='/login/')
def c_clients(request):
    # search elements
    search = ""
    if request.method == 'POST':
        search = request.POST.get('search')
        if len(search) < 3:
            search = ""
    # CLIENTS
    filtered_persons = Person.objects.filter(Q(firstname__icontains=search) | Q(lastname__icontains=search) | Q(company_name__icontains=search)).order_by('firstname')[:30]
    selected_clients = []
    for person in filtered_persons:
        if Order.objects.filter(person=person).filter(is_client=True).exists():
            selected_clients.append(person)
    page = request.GET.get('page')
    paginator = Paginator(selected_clients, 10)
    clients_on_page = paginator.get_page(page)
    return render(
        request,
        'clients/c_clients.html',
        {"selected_clients": clients_on_page, "search": search}
    )

@login_required(login_url='/login/')
def p_providers(request):
    # search elements
    search_name = ""
    search_service = ""
    if request.method == 'POST':
        search_name = request.POST.get('search_name')
        search_service = request.POST.get('search_service')
    # PROVIDERS
    filtered_persons = Person.objects.filter(Q(firstname__icontains=search_name) | Q(lastname__icontains=search_name) | Q(company_name__icontains=search_name)).filter(services__icontains=search_service).order_by('firstname')[:30]
    selected_providers = []
    for person in filtered_persons:
        if Order.objects.filter(person=person).filter(is_client=False).exists() or not Order.objects.filter(person=person).filter(is_client=True).exists():
            person_total_orders = Order.objects.filter(person=person).count()
            provider = {"provider": person, "total_orders": person_total_orders}
            selected_providers.append(provider)
    page = request.GET.get('page')
    paginator = Paginator(selected_providers, 10)
    providers_on_page = paginator.get_page(page)
    return render(
        request,
        'providers/p_providers.html',
        {"selected_providers": providers_on_page, "search_name": search_name, "search_service": search_service}
    )