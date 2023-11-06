from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Count, Q
from .models import Person
from orders.models import Order
from payments.models import Payment
from invoices.models import Invoice
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

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
    distinct_persons = Order.objects.filter(is_client=True).values('person').distinct()
    selected_clients = Person.objects.filter(id__in=distinct_persons).filter(Q(firstname__icontains=search) | Q(lastname__icontains=search) | Q(company_name__icontains=search)).order_by('firstname')
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
    return render(request, 'providers/p_providers.html')