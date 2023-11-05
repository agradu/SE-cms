from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.db.models import Sum
from orders.models import Order, OrderElement
from payments.models import Payment
from invoices.models import Invoice
from django.core.paginator import Paginator

# Create your views here.

@login_required(login_url='/login/')
def c_clients(request):
    return render(request, 'clients/c_clients.html')

@login_required(login_url='/login/')
def c_orders(request):
    # client orders
    if request.method == 'POST':
        search = request.POST.get('search')
        reg_start = request.POST.get('reg_start')
        reg_end = request.POST.get('reg_end')
    page = request.GET.get('page')
    order = request.GET.get('order')
    client = request.GET.get('client')
    assignee = request.GET.get('assignee')
    registered = request.GET.get('order')
    deadline = request.GET.get('client')
    status = request.GET.get('status')
    value = request.GET.get('value')
    payed = request.GET.get('payed')
    update = request.GET.get('update')
    selected_orders = Order.objects.filter(is_client=True).order_by('-created_at')
    client_orders = []
    for o in selected_orders:
        o_invoices = Invoice.objects.filter(order=o)
        o_payed = 0
        for i in o_invoices:
            o_payed += Payment.objects.aggregate(payed=Sum('price'))
        order_elements = OrderElement.objects.filter(order=o).order_by('id')
        o_status = order_elements[0].status
        for e in order_elements:
            if e.status.id < o_status.id:
                o_status = e.status
        client_orders.append({"order":o, "elements":order_elements, "status":o_status, "payed":o_payed})
    paginator = Paginator(client_orders, 10)
    orders_on_page = paginator.get_page(page)

    return render(
        request,
        'clients/c_orders.html', 
        {
            'client_orders': orders_on_page
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