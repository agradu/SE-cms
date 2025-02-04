from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.db.models import Sum, Case, When, Value, F, DecimalField
from django.db.models.functions import Coalesce
from orders.models import Order, OrderElement
from payments.models import Payment, PaymentElement
from invoices.models import Invoice, InvoiceElement
from datetime import datetime, timezone


@login_required(login_url="/login/")
def dashboard(request):
    # recent orders box
    selected_orders = Order.objects.all().order_by("-created_at")[:10]
    recent_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
        status = o.status
        recent_orders.append({"order": o, "elements": order_elements, "status": status})

    # last unfinished client orders
    selected_orders = Order.objects.filter(is_client=True, status__percent__gt=5, status__percent__lt=100).order_by("deadline")[:10]
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
    selected_orders = Order.objects.filter(is_client=False, status__percent__gt=5, status__percent__lt=100).order_by("deadline")[:10]
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
    invoices_with_payments = Invoice.objects.filter(
        is_client=True
    ).annotate(
        total_paid=Coalesce(Sum(
            Case(
                When(paymentelement__payment__value__lte=F('value'), then='paymentelement__payment__value'),
                default=Value(0, output_field=DecimalField()),  # Dacă nu există plăți, sau sunt invalide, suma este zero
                output_field=DecimalField()
            )
        ), Value(0, output_field=DecimalField()))  # Setting all nulls to zero
    ).order_by('-deadline')

    # Select all invoices where the total is less than the invoice value (inclusiv without payments)
    partially_paid_invoices = invoices_with_payments.filter(
        total_paid__lt=F('value')
    )

    client_invoices = []
    for invoice in partially_paid_invoices[:15]:
        payed_percentage = (invoice.total_paid / invoice.value * 100) if invoice.value else 0
        payed_percentage = int(payed_percentage)
        
        current_date = datetime.now().date()
        alert = "text-danger" if invoice.deadline < current_date else ""
        
        client_invoices.append({
            "invoice": invoice,
            "payed": payed_percentage,
            "alert": alert
        })

    # last unpayed provider invoices
    invoices_with_payments = Invoice.objects.filter(
        is_client=False
    ).annotate(
        total_paid=Coalesce(Sum(
            Case(
                When(paymentelement__payment__value__lte=F('value'), then='paymentelement__payment__value'),
                default=Value(0, output_field=DecimalField()),  # Dacă nu există plăți, sau sunt invalide, suma este zero
                output_field=DecimalField()
            )
        ), Value(0, output_field=DecimalField()))  # Setting all nulls to zero
    ).order_by('-deadline')

    # Select all invoices where the total is less than the invoice value (inclusiv without payments)
    partially_paid_invoices = invoices_with_payments.filter(
        total_paid__lt=F('value')
    )

    provider_invoices = []
    for invoice in partially_paid_invoices[:15]:
        payed_percentage = (invoice.total_paid / invoice.value * 100) if invoice.value else 0
        payed_percentage = int(payed_percentage)
        
        current_date = datetime.now().date()
        alert = "text-danger" if invoice.deadline < current_date else ""
        
        provider_invoices.append({
            "invoice": invoice,
            "payed": payed_percentage,
            "alert": alert
        })


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
            error_message = "Fail to sign in. Please verify everything carefuly."
            return render(request, "login.html", {"error_message": error_message})
    # Dacă nu e metoda POST, deconectează utilizatorul
    logout(request)

    return render(request, "login.html")
