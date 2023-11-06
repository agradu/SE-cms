from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from orders.models import Order, OrderElement
from payments.models import Payment
from invoices.models import Invoice
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

# Create your views here.

@login_required(login_url='/login/')
def c_clients(request):
    return render(request, 'clients/c_clients.html')

@login_required(login_url='/login/')
def c_orders(request):
    # search elements
    search = ""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = date_now - timedelta(days=6)
    reg_start = date_before.strftime('%Y-%m-%d')
    filter_start = date_before
    reg_end = date_now.strftime('%Y-%m-%d')
    filter_end = date_now
    if request.method == 'POST':
        search = request.POST.get('search')
        if len(search) > 2:
            reg_start = request.POST.get('reg_start')
            filter_start = datetime.strptime(reg_start, '%Y-%m-%d')
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get('reg_end')
            filter_end = datetime.strptime(reg_end, '%Y-%m-%d')
            filter_end = timezone.make_aware(filter_end).replace(hour=23, minute=59, second=59, microsecond=0)
        else:
            search = ""
    # CLIENT ORDERS
    selected_orders = Order.objects.filter(is_client=True).filter(Q(person__firstname__icontains=search) | Q(person__lastname__icontains=search) | Q(person__company_name__icontains=search)).filter(created_at__gte=filter_start, created_at__lte=filter_end)
    client_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by('id')
        o_status = order_elements[0].status
        o_currency = order_elements[0].currency.symbol
        o_value = 0
        for e in order_elements:
            o_value += e.price
            if e.status.id < o_status.id:
                o_status = e.status
        o_invoices = Invoice.objects.filter(order=o)
        o_payed = 0
        for i in o_invoices:
            o_payed += Payment.objects.aggregate(payed=Sum('price'))
        payed = int(o_value / 100 * o_payed)
        client_orders.append(
            {
                "order":o, 
                "elements":order_elements, 
                "status":o_status, 
                "payed":payed, 
                "currency":o_currency,
                "value": o_value,
            }
        )
    # sorting types
    page = request.GET.get('page')
    sort = request.GET.get('sort')
    if sort == 'order':
        client_orders = sorted(client_orders, key=lambda x: x["order"].id, reverse=True)
    elif sort == 'client':
        client_orders = sorted(client_orders, key=lambda x: x["order"].person.firstname)
    elif sort == 'assignee':
        client_orders = sorted(client_orders, key=lambda x: x["order"].user.first_name)
    elif sort == 'registered':
        client_orders = sorted(client_orders, key=lambda x: x["order"].created_at, reverse=True)
    elif sort == 'deadline':
        client_orders = sorted(client_orders, key=lambda x: x["order"].deadline, reverse=True)
    elif sort == 'status':
        client_orders = sorted(client_orders, key=lambda x: x["status"].id)
    elif sort == 'value':
        client_orders = sorted(client_orders, key=lambda x: x["value"], reverse=True)
    elif sort == 'payed':
        client_orders = sorted(client_orders, key=lambda x: x["payed"])
    elif sort == 'update':
        client_orders = sorted(client_orders, key=lambda x: x["order"].modified_at, reverse=True)
    else:
        client_orders = sorted(client_orders, key=lambda x: x["order"].created_at, reverse=True)
        
    paginator = Paginator(client_orders, 10)
    orders_on_page = paginator.get_page(page)

    return render(
        request,
        'clients/c_orders.html', 
        {
            'client_orders': orders_on_page, "sort": sort, "search": search, "reg_start": reg_start, "reg_end": reg_end
        }
    )

@login_required(login_url='/login/')
def c_offers(request):
    return render(request, 'clients/c_offers.html')

@login_required(login_url='/login/')
def p_providers(request):
    return render(request, 'providers/p_providers.html')

@login_required(login_url='/login/')
def p_orders(request):
    return render(request, 'providers/p_orders.html')