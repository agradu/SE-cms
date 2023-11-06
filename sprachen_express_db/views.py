from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum
from orders.models import Order, OrderElement
from payments.models import Payment
from invoices.models import Invoice

@login_required(login_url='/login/')
def dashboard(request):
    # recent orders box
    selected_orders = Order.objects.all().order_by('-created_at')[:6]
    recent_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by('id')
        status = order_elements[0].status
        for e in order_elements:
            if e.status.id < status.id:
                status = e.status
        recent_orders.append({"order":o, "elements":order_elements, "status":status})

    # last unfinished client orders
    selected_orders = Order.objects.filter(is_client=True).order_by('deadline')[:6]
    client_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by('id')
        o_status = order_elements[0].status
        o_value = 0
        for e in order_elements:
            o_value += e.price * e.units
            if e.status.id < o_status.id:
                o_status = e.status
        o_invoices = Invoice.objects.filter(order=o)
        o_payed = 0
        for i in o_invoices:
            o_payed += Payment.objects.aggregate(payed=Sum('price'))
        payed = int(o_value / 100 * o_payed)
        
        if o_status.id < 5:
            client_orders.append(
                {
                    "order":o, 
                    "elements":order_elements, 
                    "status":o_status, 
                    "payed":payed,
                    "value": o_value
                }
            )
    # last unfinished provider orders
    selected_orders = Order.objects.filter(is_client=False).order_by('deadline')[:6]
    provider_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by('id')
        o_status = order_elements[0].status
        o_value = 0
        for e in order_elements:
            o_value += e.price * e.units
            if e.status.id < o_status.id:
                o_status = e.status
        o_invoices = Invoice.objects.filter(order=o)
        o_payed = 0
        for i in o_invoices:
            o_payed += Payment.objects.aggregate(payed=Sum('price'))
        payed = int(o_value / 100 * o_payed)
        
        if o_status.id < 5:
            provider_orders.append(
                {
                    "order":o, 
                    "elements":order_elements, 
                    "status":o_status, 
                    "payed":payed,
                    "value": o_value
                }
            )

    return render(
        request,
        'dashboard.html', 
        {'recent_orders': recent_orders, 'client_orders': client_orders, 'provider_orders': provider_orders}
    )

@csrf_protect
def login_view(request):
    if request.method == 'POST':
        username = request.POST.get('username')
        password = request.POST.get('password')
        print("user:",username,"pass:",password)
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get('next', None)
            if next_url:
                return redirect(next_url)
            return redirect('dashboard')
        else:
            logout(request)
            # Autentificarea a eșuat, poți afișa o eroare sau un mesaj de avertizare
            error_message = "Fail to sign in. Please verify everything carefuly."
            return render(request, 'login.html', {'error_message': error_message})
    # Dacă nu e metoda POST, deconectează utilizatorul 
    logout(request)

    return render(request, 'login.html')
