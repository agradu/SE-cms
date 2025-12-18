from django.contrib.auth import authenticate, login, logout
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect

from django.db.models import (
    Sum, F, Value, DecimalField, IntegerField, Exists, OuterRef,
    ExpressionWrapper
)
from django.db.models.functions import Coalesce
from django.utils import timezone

from orders.models import Order, OrderElement
from invoices.models import InvoiceElement
from invoices.models import Invoice, ProformaElement


@login_required(login_url="/login/")
def dashboard(request):
    now = timezone.now()
    today = timezone.localdate()

    # -------------------------
    # 1) Recent orders (ultimele 10)
    # -------------------------
    recent_qs = (
        Order.objects
        .select_related("status", "person", "currency")
        .order_by("-created_at")[:10]
    )
    recent_elements_qs = (
        OrderElement.objects
        .select_related("service", "um", "status", "order__currency")
        .order_by("id")
    )
    # Prefetch ca să nu faci query per order
    from django.db.models import Prefetch
    recent_qs = recent_qs.prefetch_related(Prefetch("elements", queryset=recent_elements_qs))

    recent_orders = [
        {"order": o, "elements": list(o.elements.all()), "status": o.status}
        for o in recent_qs
    ]

    # -------------------------
    # Helper: calc "invoiced %" pentru orders
    # (sumă din InvoiceElement -> OrderElement.quantity*price)
    # -------------------------
    invoiced_total_expr = ExpressionWrapper(
        F("elements__invoice_links__element__quantity") * F("elements__invoice_links__element__price"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )

    # Exists pentru proforma (dacă există cel puțin un ProformaElement pt orice element din order)
    proforma_exists = Exists(
        ProformaElement.objects.filter(element__order_id=OuterRef("pk"))
    )

    # -------------------------
    # 2) Unfinished client orders
    # -------------------------
    client_orders_qs = (
        Order.objects
        .filter(is_client=True, status__percent__gt=0, status__percent__lt=100)
        .select_related("status", "person", "currency")
        .annotate(
            proformed=proforma_exists,
            invoiced_total=Coalesce(Sum(invoiced_total_expr), Value(0, output_field=DecimalField())),
        )
        .order_by("deadline")[:10]
        .prefetch_related(Prefetch("elements", queryset=recent_elements_qs))
    )

    client_orders = []
    for o in client_orders_qs:
        invoiced_pct = int((o.invoiced_total / o.value) * 100) if o.value else 0
        alert = "text-danger" if o.deadline and o.deadline < now else ""
        client_orders.append({
            "order": o,
            "elements": list(o.elements.all()),
            "status": o.status,
            "invoiced": invoiced_pct,
            # păstrăm cheia din template: înainte era un obiect sau None; acum e bool
            # dacă ai nevoie de obiect, îl luăm ulterior, dar bool e mult mai ieftin.
            "proformed": o.proformed,
            "alert": alert,
        })

    # -------------------------
    # 3) Unfinished provider orders
    # -------------------------
    provider_orders_qs = (
        Order.objects
        .filter(is_client=False, status__percent__gt=0, status__percent__lt=100)
        .select_related("status", "person", "currency")
        .annotate(
            invoiced_total=Coalesce(Sum(invoiced_total_expr), Value(0, output_field=DecimalField())),
        )
        .order_by("deadline")[:10]
        .prefetch_related(Prefetch("elements", queryset=recent_elements_qs))
    )

    provider_orders = []
    for o in provider_orders_qs:
        invoiced_pct = int((o.invoiced_total / o.value) * 100) if o.value else 0
        alert = "text-danger" if o.deadline and o.deadline < now else ""
        provider_orders.append({
            "order": o,
            "elements": list(o.elements.all()),
            "status": o.status,
            "invoiced": invoiced_pct,
            "alert": alert,
        })

    # -------------------------
    # 4) Unpaid invoices (client + provider)
    # IMPORTANT: plătit = SUM(PaymentElement.value), nu Payment.value
    # Dacă folosești cache-ul Invoice.payed, poți folosi direct F("payed")
    # -------------------------
    invoices_base = (
        Invoice.objects
        .select_related("person", "currency")
        .annotate(
            total_paid=Coalesce(Sum("payment_links__value"), Value(0, output_field=DecimalField())),
        )
        .annotate(remaining=F("value") - F("total_paid"))
        .filter(remaining__gt=0)
        .order_by("-deadline")
    )

    client_invoices = []
    for inv in invoices_base.filter(is_client=True)[:15]:
        paid_pct = int((inv.total_paid / inv.value) * 100) if inv.value else 0
        alert = "text-danger" if inv.deadline and inv.deadline < today else ""
        client_invoices.append({"invoice": inv, "payed": paid_pct, "alert": alert})

    provider_invoices = []
    for inv in invoices_base.filter(is_client=False)[:15]:
        paid_pct = int((inv.total_paid / inv.value) * 100) if inv.value else 0
        alert = "text-danger" if inv.deadline and inv.deadline < today else ""
        provider_invoices.append({"invoice": inv, "payed": paid_pct, "alert": alert})

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
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            next_url = request.GET.get("next", None)
            return redirect(next_url) if next_url else redirect("dashboard")
        logout(request)
        return render(request, "login.html", {"error_message": "Fail to sign in. Please verify everything carefuly."})

    logout(request)
    return render(request, "login.html")
