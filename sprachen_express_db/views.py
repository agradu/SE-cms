from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum
from orders.models import Order, OrderElement
from payments.models import Payment, PaymentElement
from invoices.models import Invoice, InvoiceElement
from datetime import datetime, timezone


@login_required(login_url="/login/")
def dashboard(request):
    # recent orders box
    selected_orders = Order.objects.all().order_by("-created_at")[:6]
    recent_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
        status = o.status
        recent_orders.append({"order": o, "elements": order_elements, "status": status})

    # last unfinished client orders
    selected_orders = Order.objects.filter(is_client=True).order_by("deadline")[:8]
    client_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
        o_status = o.status
        o_invoiced = 0
        for e in order_elements:
            try:
                invoice_element = InvoiceElement.objects.get(element=e)
                o_invoiced += (
                    invoice_element.element.price * invoice_element.element.quantity
                )
            except:
                invoice_element = None
        if o.value > 0:
            invoiced = int(o_invoiced / o.value * 100)
        else:
            invoiced = 0

        if o.deadline < datetime.now(timezone.utc):
            alert = "text-danger"
        else:
            alert = ""

        if o_status.id < 5:
            client_orders.append(
                {
                    "order": o,
                    "elements": order_elements,
                    "status": o_status,
                    "invoiced": invoiced,
                    "alert": alert
                }
            )

    # last unfinished provider orders
    selected_orders = Order.objects.filter(is_client=False).order_by("deadline")[:8]
    provider_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
        o_status = o.status
        o_value = 0
        o_invoiced = 0
        for e in order_elements:
            try:
                invoice_element = InvoiceElement.objects.get(element=e)
                o_invoiced += (
                    invoice_element.element.price * invoice_element.element.quantity
                )
            except:
                invoice_element = None
        if o.value > 0:
            invoiced = int(o_invoiced / o.value * 100)
        else:
            invoiced = 0

        if o.deadline < datetime.now(timezone.utc):
            alert = "text-danger"
        else:
            alert = ""

        if o_status.id < 5:
            provider_orders.append(
                {
                    "order": o,
                    "elements": order_elements,
                    "status": o_status,
                    "invoiced": invoiced,
                    "alert": alert
                }
            )

    # last unpayed client invoices
    selected_invoices = Invoice.objects.filter(is_client=True).order_by("deadline")[:8]
    client_invoices = []
    for i in selected_invoices:
        i_payed = 0
        i_payments = PaymentElement.objects.filter(invoice=i)
        for p in i_payments:
            if p.payment.value < p.invoice.value:
                i_payed += p.payment.value
            else:
                i_payed += p.invoice.value
        if i.value > 0:
            payed = int(i_payed / i.value * 100)
        else:
            payed = 0

        if o.deadline < datetime.now(timezone.utc):
            alert = "text-danger"
        else:
            alert = ""

        if payed < 100:
            client_invoices.append(
                {
                    "invoice": i,
                    "payed": payed,
                    "alert": alert
                }
            )

    # last unpayed provider invoices
    selected_invoices = Invoice.objects.filter(is_client=False).order_by("deadline")[:8]
    provider_invoices = []
    for i in selected_invoices:
        i_payed = 0
        i_payments = PaymentElement.objects.filter(invoice=i)
        for p in i_payments:
            if p.payment.value < p.invoice.value:
                i_payed += p.payment.value
            else:
                i_payed += p.invoice.value
        if i.value > 0:
            payed = int(i_payed / i.value * 100)
        else:
            payed = 0

        if o.deadline < datetime.now(timezone.utc):
            alert = "text-danger"
        else:
            alert = ""

        if payed < 100:
            provider_invoices.append(
                {
                    "invoice": i,
                    "payed": payed,
                    "alert": alert
                }
            )

    return render(
        request,
        "dashboard.html",
        {
            "recent_orders": recent_orders,
            "client_orders": client_orders,
            "provider_orders": provider_orders,
            "client_invoices": client_invoices,
            "provider_invoices": provider_invoices,
        },
    )


@csrf_protect
def login_view(request):
    if request.method == "POST":
        username = request.POST.get("username")
        password = request.POST.get("password")
        print("user:", username, "pass:", password)
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", None)
            if next_url:
                return redirect(next_url)
            return redirect("dashboard")
        else:
            logout(request)
            # Autentificarea a eșuat, poți afișa o eroare sau un mesaj de avertizare
            error_message = "Fail to sign in. Please verify everything carefuly."
            return render(request, "login.html", {"error_message": error_message})
    # Dacă nu e metoda POST, deconectează utilizatorul
    logout(request)

    return render(request, "login.html")
