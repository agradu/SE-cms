from decimal import Decimal, InvalidOperation

from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField, Exists, OuterRef, Prefetch, ExpressionWrapper
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import datetime, timedelta

from weasyprint import HTML, CSS
import base64

from .models import Order, OrderElement, Offer, OfferElement
from payments.models import Payment, PaymentElement
from persons.models import Person
from invoices.models import Invoice, InvoiceElement, ProformaElement
from core.models import Currency, Status, Service, UM, Serial
from common.helpers import get_date_range, get_search_params, paginate_objects


# ----------------------------
# Helpers
# ----------------------------

def _to_decimal(val: str, default: Decimal = Decimal("1")) -> Decimal:
    if val is None:
        return default
    try:
        s = str(val).strip().replace(",", ".")
        return Decimal(s)
    except (InvalidOperation, ValueError, TypeError):
        return default


def _order_invoiced_total(order_id: int) -> Decimal:
    """
    Sum NET of billed order elements (quantity*price) for this order, excluding cancellation/cancelled invoices.
    """
    total_expr = ExpressionWrapper(
        F("element__quantity") * F("element__price"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    return (
        InvoiceElement.objects
        .filter(
            element__order_id=order_id,
            invoice__cancellation_to__isnull=True,
            invoice__cancelled_from__isnull=True,
        )
        .aggregate(total=Coalesce(Sum(total_expr), Value(0, output_field=DecimalField())))
        .get("total")
        or Decimal("0")
    )


def _touch_invoices_linked_to_order(order: Order) -> None:
    """
    If you change order elements that are linked to invoices, update those invoices' totals.
    (Uses model method recalculate_from_elements)
    """
    invoice_ids = (
        InvoiceElement.objects
        .filter(element__order=order)
        .values_list("invoice_id", flat=True)
        .distinct()
    )
    for inv_id in invoice_ids:
        try:
            inv = Invoice.objects.get(id=inv_id)
        except Invoice.DoesNotExist:
            continue
        inv.recalculate_from_elements(save=True)


def _recalculate_offer_value(offer: Offer, save: bool = True) -> Decimal:
    total_expr = ExpressionWrapper(
        F("quantity") * F("price"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )
    total = (
        offer.elements.aggregate(total=Coalesce(Sum(total_expr), Value(0, output_field=DecimalField())))
        .get("total")
        or Decimal("0")
    )
    offer.value = total
    if save:
        offer.save()
    return total


# ----------------------------
# Client Orders (list)
# ----------------------------

@login_required(login_url="/login/")
def c_orders(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    # Exists: proforma for any element in order
    proforma_exists = Exists(
        ProformaElement.objects.filter(element__order_id=OuterRef("pk"))
    )

    qs = (
        Order.objects
        .filter(
            is_client=True,
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description
        )
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client)
        )
        .select_related("person", "currency", "status", "modified_by", "created_by")
        .annotate(proformed=proforma_exists)
        .order_by("-created_at")
    )

    elements_qs = (
        OrderElement.objects
        .select_related("service", "um", "status", "order__currency")
        .order_by("id")
    )
    qs = qs.prefetch_related(Prefetch("elements", queryset=elements_qs))

    client_orders = []
    for o in qs:
        invoiced_pct = int((o.invoiced / o.value) * 100) if o.value else 0
        client_orders.append({
            "order": o,
            "elements": list(o.elements.all()),
            "invoiced": invoiced_pct,
            "proformed": bool(getattr(o, "proformed", False)),
        })

    def safe_str(x): return x or ""

    sort_keys = {
        "order": lambda x: x["order"].id or 0,
        "client": lambda x: safe_str(getattr(x["order"].person, "firstname", "")),
        "assignee": lambda x: safe_str(getattr(x["order"].modified_by, "first_name", "")),
        "registered": lambda x: x["order"].created_at or timezone.now(),
        "deadline": lambda x: x["order"].deadline or timezone.now(),
        "status": lambda x: (x["order"].status.percent if x["order"].status else 0),
        "value": lambda x: x["order"].value or Decimal("0"),
        "invoiced": lambda x: x["invoiced"] or 0,
        "update": lambda x: x["order"].modified_at or timezone.now(),
    }
    client_orders.sort(
        key=sort_keys.get(sort, lambda x: x["order"].created_at or timezone.now()),
        reverse=(sort not in ["client", "status"])
    )

    orders_on_page = paginate_objects(request, client_orders)

    return render(
        request,
        "orders/c_orders.html",
        {
            "client_orders": orders_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


# ----------------------------
# Client Order (detail/edit)
# ----------------------------

@login_required(login_url="/login/")
def c_order(request, order_id, client_id):
    statuses = Status.objects.all().order_by("percent")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.get_solo()

    search = ""
    clients = []
    element_selected = None

    date_now = timezone.localtime()

    if int(order_id) != 0:
        order = get_object_or_404(Order.objects.select_related("person", "currency", "status"), id=order_id)
        new = False
        client = order.person

        elements = list(
            OrderElement.objects.filter(order=order)
            .select_related("service", "um", "status")
            .order_by("id")
        )

        is_invoiced = InvoiceElement.objects.filter(element__order=order).exists()
        is_proformed = ProformaElement.objects.filter(element__order=order).exists()

        if request.method == "POST":
            with transaction.atomic():
                form = request.POST

                if "search" in form:
                    search = form.get("search", "")
                    if len(search) > 3:
                        clients = Person.objects.filter(
                            Q(firstname__icontains=search) |
                            Q(lastname__icontains=search) |
                            Q(company_name__icontains=search)
                        )

                if "new_client" in form and not is_invoiced:
                    new_client_id = form.get("new_client")
                    if new_client_id:
                        client = get_object_or_404(Person, id=new_client_id)
                        order.person = client

                if "order_description" in form:
                    order.description = form.get("order_description", "")
                    order.status = Status.objects.get(id=form.get("order_status"))
                    order.currency = currencies[int(form.get("order_currency")) - 1]

                    deadline_date = form.get("deadline_date")
                    deadline_time = form.get("deadline_time")
                    try:
                        deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                        order.deadline = timezone.make_aware(deadline_naive)
                    except Exception:
                        order.deadline = date_now

                    # keep elements' status aligned if you want that rule
                    for e in elements:
                        e.status = order.status
                        e.save(update_fields=["status"])

                if "element_id" in form:
                    eid = int(form.get("element_id") or 0)
                    if eid > 0:
                        element = get_object_or_404(OrderElement, id=eid, order=order)
                    else:
                        element = OrderElement(order=order)

                    element.service = Service.objects.get(id=int(form.get("e_service")))
                    element.description = form.get("e_description", "")

                    element.quantity = int(_to_decimal(form.get("e_quantity"), Decimal("1")))
                    element.um = ums[int(form.get("e_um")) - 1]
                    element.price = _to_decimal(form.get("e_price"), Decimal("1"))

                    element.status = Status.objects.get(id=int(form.get("e_status")))
                    element.full_clean()
                    element.save()

                    # refresh elements list after change
                    elements = list(
                        OrderElement.objects.filter(order=order).select_related("status").order_by("id")
                    )

                    # order.status = minimum status among elements (if that's your rule)
                    if elements:
                        status_elements = sorted(elements, key=lambda x: x.status.percent)
                        order.status = status_elements[0].status

                    element_selected = None

                if "delete_element_id" in form:
                    del_id = int(form.get("delete_element_id") or 0)
                    el = get_object_or_404(OrderElement, id=del_id, order=order)
                    el.delete()
                    elements = list(
                        OrderElement.objects.filter(order=order).select_related("status").order_by("id")
                    )

                if "edit_element_id" in form:
                    edit_id = int(form.get("edit_element_id") or 0)
                    element_selected = get_object_or_404(OrderElement, id=edit_id, order=order)

                order.modified_by = request.user
                order.modified_at = date_now

                # Recalculate NET totals from elements (uses model method)
                order.recalculate_from_elements(save=True)

                # Update invoiced cache from DB
                order.invoiced = _order_invoiced_total(order.id)
                order.save(update_fields=["invoiced", "modified_by", "modified_at", "status", "description", "deadline", "currency", "person", "value", "vat_value", "vat_rate"])

                # If any linked invoices exist, update their totals too
                _touch_invoices_linked_to_order(order)

    else:
        new = True
        order = None
        client = Person.objects.filter(id=client_id).first() if int(client_id) else None
        elements = []
        is_invoiced = False
        is_proformed = False

        if request.method == "POST":
            form = request.POST

            if "search" in form:
                search = form.get("search", "")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search) |
                        Q(lastname__icontains=search) |
                        Q(company_name__icontains=search)
                    )

            if "new_client" in form:
                new_client_id = form.get("new_client")
                if new_client_id:
                    client = get_object_or_404(Person, id=new_client_id)
                    return redirect("c_order", order_id=0, client_id=client.id)

            if "order_description" in form and client:
                description = form.get("order_description", "")
                status = Status.objects.get(id=form.get("order_status"))
                currency = currencies[int(form.get("order_currency")) - 1]

                deadline_date = form.get("deadline_date")
                deadline_time = form.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                except Exception:
                    deadline = timezone.localtime()

                with transaction.atomic():
                    order = Order.objects.create(
                        description=description,
                        serial=serials.order_serial,
                        number=str(serials.order_number),
                        person=client,
                        deadline=deadline,
                        is_client=True,
                        modified_by=request.user,
                        created_by=request.user,
                        status=status,
                        currency=currency,
                        value=Decimal("0"),
                        invoiced=Decimal("0"),
                    )

                    serials.order_number += 1
                    serials.save(update_fields=["order_number"])

                new = False
                return redirect("c_order", order_id=order.id, client_id=client.id)

    return render(
        request,
        "orders/c_order.html",
        {
            "clients": clients,
            "order": order,
            "client": client,
            "elements": elements,
            "currencies": currencies,
            "statuses": statuses,
            "ums": ums,
            "services": services,
            "new": new,
            "element_selected": element_selected,
            "is_invoiced": is_invoiced,
            "is_proformed": is_proformed,
        },
    )


# ----------------------------
# Offers (list)
# ----------------------------

@login_required(login_url="/login/")
def c_offers(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    qs = (
        Offer.objects
        .filter(
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description
        )
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client)
        )
        .select_related("person", "currency", "status", "modified_by", "created_by", "order")
        .order_by("-created_at")
    )

    offer_el_qs = (
        OfferElement.objects
        .select_related("service", "um", "offer__currency")
        .order_by("id")
    )
    qs = qs.prefetch_related(Prefetch("elements", queryset=offer_el_qs))

    client_offers = [{"offer": o, "elements": list(o.elements.all()), "order": o.order} for o in qs]

    def safe_str(x): return x or ""

    sort_keys = {
        "offer": lambda x: x["offer"].id or 0,
        "client": lambda x: safe_str(getattr(x["offer"].person, "firstname", "")),
        "assignee": lambda x: safe_str(getattr(x["offer"].modified_by, "first_name", "")),
        "registered": lambda x: x["offer"].created_at or timezone.now(),
        "deadline": lambda x: x["offer"].deadline or timezone.now(),
        "status": lambda x: (x["offer"].status.percent if x["offer"].status else 0),
        "value": lambda x: x["offer"].value or Decimal("0"),
        "update": lambda x: x["offer"].modified_at or timezone.now(),
    }
    client_offers.sort(
        key=sort_keys.get(sort, lambda x: x["offer"].created_at or timezone.now()),
        reverse=(sort not in ["client", "status"])
    )

    offers_on_page = paginate_objects(request, client_offers)

    return render(
        request,
        "orders/c_offers.html",
        {
            "client_offers": offers_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


# ----------------------------
# Offer (detail/edit)
# ----------------------------

@login_required(login_url="/login/")
def c_offer(request, offer_id, client_id):
    statuses = Status.objects.filter(id__range=(1, 2)).order_by("id")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.get_solo()

    search = ""
    clients = []
    element_selected = None
    date_now = timezone.localtime()

    if int(offer_id) != 0:
        offer = get_object_or_404(Offer.objects.select_related("person", "currency", "status", "order"), id=offer_id)
        new = False
        client = offer.person

        elements = list(
            OfferElement.objects.filter(offer=offer).select_related("service", "um").order_by("id")
        )

        if request.method == "POST":
            with transaction.atomic():
                form = request.POST

                if "search" in form:
                    search = form.get("search", "")
                    if len(search) > 3:
                        clients = Person.objects.filter(
                            Q(firstname__icontains=search) |
                            Q(lastname__icontains=search) |
                            Q(company_name__icontains=search)
                        )

                if "new_client" in form:
                    new_client_id = form.get("new_client")
                    if new_client_id:
                        client = get_object_or_404(Person, id=new_client_id)
                        offer.person = client

                if "offer_description" in form:
                    offer.description = form.get("offer_description", "")
                    offer.status = statuses[int(form.get("offer_status")) - 1]
                    offer.currency = currencies[int(form.get("offer_currency")) - 1]

                    deadline_date = form.get("deadline_date")
                    deadline_time = form.get("deadline_time")
                    try:
                        deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                        offer.deadline = timezone.make_aware(deadline_naive)
                    except Exception:
                        offer.deadline = date_now

                    # optional: keep element status aligned (if OfferElement had status; your model doesn't)
                    offer.modified_by = request.user
                    offer.modified_at = date_now
                    offer.save()

                if "element_id" in form:
                    eid = int(form.get("element_id") or 0)
                    if eid > 0:
                        element = get_object_or_404(OfferElement, id=eid, offer=offer)
                    else:
                        element = OfferElement(offer=offer)

                    element.service = Service.objects.get(id=int(form.get("e_service")))
                    element.description = form.get("e_description", "")
                    element.quantity = int(_to_decimal(form.get("e_quantity"), Decimal("1")))
                    element.um = ums[int(form.get("e_um")) - 1]
                    element.price = _to_decimal(form.get("e_price"), Decimal("1"))
                    element.full_clean()
                    element.save()
                    element_selected = None

                if "delete_element_id" in form:
                    del_id = int(form.get("delete_element_id") or 0)
                    el = get_object_or_404(OfferElement, id=del_id, offer=offer)
                    el.delete()

                if "edit_element_id" in form:
                    edit_id = int(form.get("edit_element_id") or 0)
                    element_selected = get_object_or_404(OfferElement, id=edit_id, offer=offer)

                # refresh elements and recalc offer value
                _recalculate_offer_value(offer, save=True)

    else:
        new = True
        offer = None
        client = Person.objects.filter(id=client_id).first() if int(client_id) else None
        elements = []

        if request.method == "POST":
            form = request.POST

            if "search" in form:
                search = form.get("search", "")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search) |
                        Q(lastname__icontains=search) |
                        Q(company_name__icontains=search)
                    )

            if "new_client" in form:
                new_client_id = form.get("new_client")
                if new_client_id:
                    client = get_object_or_404(Person, id=new_client_id)
                    return redirect("c_offer", offer_id=0, client_id=client.id)

            if "offer_description" in form and client:
                description = form.get("offer_description", "")
                status = statuses[int(form.get("offer_status")) - 1]
                currency = currencies[int(form.get("offer_currency")) - 1]

                deadline_date = form.get("deadline_date")
                deadline_time = form.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                except Exception:
                    deadline = timezone.localtime()

                with transaction.atomic():
                    offer = Offer.objects.create(
                        description=description,
                        serial=serials.offer_serial,
                        number=str(serials.offer_number),
                        person=client,
                        deadline=deadline,
                        modified_by=request.user,
                        created_by=request.user,
                        status=status,
                        currency=currency,
                        value=Decimal("0"),
                    )
                    serials.offer_number += 1
                    serials.save(update_fields=["offer_number"])

                new = False
                return redirect("c_offer", offer_id=offer.id, client_id=client.id)

    return render(
        request,
        "orders/c_offer.html",
        {
            "clients": clients,
            "offer": offer,
            "client": client,
            "elements": elements,
            "currencies": currencies,
            "statuses": statuses,
            "ums": ums,
            "services": services,
            "new": new,
            "element_selected": element_selected,
        },
    )


# ----------------------------
# Convert offer -> order
# ----------------------------

@login_required(login_url="/login/")
def convert_offer(request, offer_id):
    offer = get_object_or_404(Offer.objects.select_related("person", "currency"), id=offer_id)
    offer_elements = OfferElement.objects.filter(offer=offer).select_related("service", "um").order_by("id")
    serials = Serial.get_solo()
    statuses = Status.objects.filter(id__range=(1, 2)).order_by("id")

    with transaction.atomic():
        order = Order.objects.create(
            description=offer.description,
            serial=serials.order_serial,
            number=str(serials.order_number),
            person=offer.person,
            deadline=offer.deadline,
            is_client=True,
            modified_by=request.user,
            created_by=request.user,
            currency=offer.currency,
            value=Decimal("0"),
            status=statuses[0] if statuses else Status.objects.first(),
        )

        for e in offer_elements:
            OrderElement.objects.create(
                order=order,
                service=e.service,
                description=e.description,
                quantity=e.quantity,
                um=e.um,
                price=e.price,
                status=order.status,
            )

        # recalc order totals
        order.recalculate_from_elements(save=True)
        order.invoiced = Decimal("0")
        order.save(update_fields=["invoiced"])

        offer.order = order
        offer.status = statuses[1] if len(statuses) > 1 else offer.status
        offer.save(update_fields=["order", "status"])

        serials.order_number += 1
        serials.save(update_fields=["order_number"])

    return redirect("c_order", order_id=order.pk, client_id=order.person.pk)


# ----------------------------
# Provider orders (list)
# ----------------------------

@login_required(login_url="/login/")
def p_orders(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    qs = (
        Order.objects
        .filter(
            is_client=False,
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description
        )
        .filter(
            Q(person__firstname__icontains=search_provider) |
            Q(person__lastname__icontains=search_provider) |
            Q(person__company_name__icontains=search_provider)
        )
        .select_related("person", "currency", "status", "modified_by", "created_by")
        .order_by("-created_at")
    )

    elements_qs = (
        OrderElement.objects
        .select_related("service", "um", "status", "order__currency")
        .order_by("id")
    )
    qs = qs.prefetch_related(Prefetch("elements", queryset=elements_qs))

    provider_orders = []
    for o in qs:
        invoiced_pct = int((o.invoiced / o.value) * 100) if o.value else 0
        provider_orders.append({"order": o, "elements": list(o.elements.all()), "invoiced": invoiced_pct})

    def safe_str(x): return x or ""

    sort_keys = {
        "order": lambda x: x["order"].id or 0,
        "provider": lambda x: safe_str(getattr(x["order"].person, "firstname", "")),
        "assignee": lambda x: safe_str(getattr(x["order"].modified_by, "first_name", "")),
        "registered": lambda x: x["order"].created_at or timezone.now(),
        "deadline": lambda x: x["order"].deadline or timezone.now(),
        "status": lambda x: (x["order"].status.percent if x["order"].status else 0),
        "value": lambda x: x["order"].value or Decimal("0"),
        "invoiced": lambda x: x["invoiced"] or 0,
        "update": lambda x: x["order"].modified_at or timezone.now(),
    }
    provider_orders.sort(
        key=sort_keys.get(sort, lambda x: x["order"].created_at or timezone.now()),
        reverse=(sort not in ["provider", "status"])
    )

    orders_on_page = paginate_objects(request, provider_orders)

    return render(
        request,
        "orders/p_orders.html",
        {
            "provider_orders": orders_on_page,
            "sort": sort,
            "search_provider": search_provider,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


# ----------------------------
# Public provider orders by token (optimized + correct NET)
# ----------------------------

def provider_orders(request, token):
    person = get_object_or_404(Person, token=token)

    if Order.objects.filter(person=person, is_client=False).exists():
        latest_order = Order.objects.filter(person=person, is_client=False).latest("created_at")
        date_end = latest_order.created_at
    else:
        date_end = None

    filter_start, filter_end, reg_start, reg_end = get_date_range(request, 30, date_end)

    selected_orders = (
        Order.objects
        .filter(
            is_client=False,
            person=person,
            created_at__range=(filter_start, filter_end),
            status__percent__gt=0
        )
        .select_related("person", "currency", "status")
        .order_by("-created_at")
        .prefetch_related(Prefetch("elements", queryset=OrderElement.objects.order_by("id")))
    )

    # Prefetch invoices + payments in bulk
    order_elements_ids = OrderElement.objects.filter(order__in=selected_orders).values_list("id", flat=True)
    invoice_ids = (
        InvoiceElement.objects
        .filter(element_id__in=order_elements_ids)
        .values_list("invoice_id", flat=True)
        .distinct()
    )

    invoices = Invoice.objects.filter(id__in=invoice_ids).order_by("id")
    # NET paid total = sum payment_links.value (not Payment.value)
    payments_by_invoice = (
        PaymentElement.objects
        .filter(invoice_id__in=invoice_ids)
        .select_related("payment", "invoice")
        .order_by("payment_id")
    )

    # group payments per invoice id
    inv_to_payments = {}
    processed_payment_ids = set()
    payed_total = Decimal("0")

    for pe in payments_by_invoice:
        inv_to_payments.setdefault(pe.invoice_id, set()).add(pe.payment_id)
        if pe.payment_id not in processed_payment_ids:
            processed_payment_ids.add(pe.payment_id)
            payed_total += (pe.payment.value or Decimal("0"))

    value_total = Decimal("0")
    provider_orders_ctx = []

    # precompute invoices per order via elements
    inv_by_order = {}
    inv_links = (
        InvoiceElement.objects
        .filter(element__order__in=selected_orders)
        .select_related("invoice", "element__order")
    )
    for link in inv_links:
        inv_by_order.setdefault(link.element.order_id, set()).add(link.invoice_id)

    for o in selected_orders:
        elems = list(o.elements.all())
        value_total += (o.value or Decimal("0"))

        o_invoice_ids = list(inv_by_order.get(o.id, set()))
        o_invoices = [inv for inv in invoices if inv.id in o_invoice_ids]

        # payments connected to these invoices (unique)
        payment_ids = set()
        for iid in o_invoice_ids:
            payment_ids |= inv_to_payments.get(iid, set())

        o_payments = list(Payment.objects.filter(id__in=payment_ids).order_by("id"))

        provider_orders_ctx.append({
            "order": o,
            "elements": elems,
            "invoices": o_invoices,
            "payments": o_payments,
        })

    return render(
        request,
        "orders/providers_orders.html",
        {
            "provider_orders": provider_orders_ctx,
            "reg_start": reg_start,
            "reg_end": reg_end,
            "person": person,
            "unpayed_total": (value_total - payed_total),
        },
    )


# ----------------------------
# Provider Order (detail/edit)
# ----------------------------

@login_required(login_url="/login/")
def p_order(request, order_id, provider_id):
    statuses = Status.objects.all().order_by("percent")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.get_solo()

    search = ""
    providers = []
    element_selected = None

    date_now = timezone.localtime()

    if int(order_id) != 0:
        order = get_object_or_404(Order.objects.select_related("person", "currency", "status"), id=order_id)
        new = False
        provider = order.person

        elements = list(
            OrderElement.objects.filter(order=order)
            .select_related("service", "um", "status")
            .order_by("id")
        )

        is_invoiced = InvoiceElement.objects.filter(element__order=order).exists()

        if request.method == "POST":
            with transaction.atomic():
                form = request.POST

                if "search" in form:
                    search = form.get("search", "")
                    if len(search) > 3:
                        providers = Person.objects.filter(
                            Q(firstname__icontains=search) |
                            Q(lastname__icontains=search) |
                            Q(company_name__icontains=search)
                        )

                if "new_provider" in form and not is_invoiced:
                    new_provider_id = form.get("new_provider")
                    if new_provider_id:
                        provider = get_object_or_404(Person, id=new_provider_id)
                        order.person = provider

                if "order_description" in form:
                    order.description = form.get("order_description", "")
                    order.status = Status.objects.get(id=form.get("order_status"))
                    order.currency = currencies[int(form.get("order_currency")) - 1]

                    deadline_date = form.get("deadline_date")
                    deadline_time = form.get("deadline_time")
                    try:
                        deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                        order.deadline = timezone.make_aware(deadline_naive)
                    except Exception:
                        order.deadline = date_now

                    for e in elements:
                        e.status = order.status
                        e.save(update_fields=["status"])

                if "element_id" in form:
                    eid = int(form.get("element_id") or 0)
                    if eid > 0:
                        element = get_object_or_404(OrderElement, id=eid, order=order)
                    else:
                        element = OrderElement(order=order)

                    element.service = Service.objects.get(id=int(form.get("e_service")))
                    element.description = form.get("e_description", "")
                    element.quantity = int(_to_decimal(form.get("e_quantity"), Decimal("1")))
                    element.um = ums[int(form.get("e_um")) - 1]
                    element.price = _to_decimal(form.get("e_price"), Decimal("1"))
                    element.status = Status.objects.get(id=int(form.get("e_status")))
                    element.full_clean()
                    element.save()
                    element_selected = None

                    elements = list(OrderElement.objects.filter(order=order).select_related("status").order_by("id"))
                    if elements:
                        status_elements = sorted(elements, key=lambda x: x.status.percent)
                        order.status = status_elements[0].status

                if "delete_element_id" in form:
                    del_id = int(form.get("delete_element_id") or 0)
                    el = get_object_or_404(OrderElement, id=del_id, order=order)
                    el.delete()

                if "edit_element_id" in form:
                    edit_id = int(form.get("edit_element_id") or 0)
                    element_selected = get_object_or_404(OrderElement, id=edit_id, order=order)

                order.modified_by = request.user
                order.modified_at = date_now

                order.recalculate_from_elements(save=True)
                order.invoiced = _order_invoiced_total(order.id)
                order.save(update_fields=["invoiced", "modified_by", "modified_at", "status", "description", "deadline", "currency", "person", "value", "vat_value", "vat_rate"])

                _touch_invoices_linked_to_order(order)

    else:
        new = True
        order = None
        provider = Person.objects.filter(id=provider_id).first() if int(provider_id) else None
        elements = []
        is_invoiced = False

        if request.method == "POST":
            form = request.POST

            if "search" in form:
                search = form.get("search", "")
                if len(search) > 3:
                    providers = Person.objects.filter(
                        Q(firstname__icontains=search) |
                        Q(lastname__icontains=search) |
                        Q(company_name__icontains=search)
                    )

            if "new_provider" in form:
                new_provider_id = form.get("new_provider")
                if new_provider_id:
                    provider = get_object_or_404(Person, id=new_provider_id)
                    return redirect("p_order", order_id=0, provider_id=provider.id)

            if "order_description" in form and provider:
                description = form.get("order_description", "")
                status = Status.objects.get(id=form.get("order_status"))
                currency = currencies[int(form.get("order_currency")) - 1]

                deadline_date = form.get("deadline_date")
                deadline_time = form.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                except Exception:
                    deadline = timezone.localtime()

                with transaction.atomic():
                    order = Order.objects.create(
                        description=description,
                        serial=serials.p_order_serial,
                        number=str(serials.p_order_number),
                        person=provider,
                        deadline=deadline,
                        is_client=False,
                        modified_by=request.user,
                        created_by=request.user,
                        status=status,
                        currency=currency,
                        value=Decimal("0"),
                        invoiced=Decimal("0"),
                    )
                    serials.p_order_number += 1
                    serials.save(update_fields=["p_order_number"])

                new = False
                return redirect("p_order", order_id=order.id, provider_id=provider.id)

    return render(
        request,
        "orders/p_order.html",
        {
            "providers": providers,
            "order": order,
            "provider": provider,
            "elements": elements,
            "currencies": currencies,
            "statuses": statuses,
            "ums": ums,
            "services": services,
            "is_invoiced": is_invoiced,
            "new": new,
            "element_selected": element_selected,
        },
    )


# ----------------------------
# Printing
# ----------------------------

@login_required(login_url="/login/")
def print_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_elements = OrderElement.objects.exclude(status__id="6").filter(order=order).order_by("id")
    leading_number = str(order.number).rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        img_content = f.read()
    logo_base64 = base64.b64encode(img_content).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "order": order,
        "leading_number": leading_number,
        "order_elements": order_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("orders/print_order.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Auftragsbestaetigung_{order.serial}-{order.number}.pdf'
    return response


@login_required(login_url="/login/")
def print_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    offer_elements = OfferElement.objects.filter(offer=offer).order_by("id")
    leading_number = str(offer.number).rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        img_content = f.read()
    logo_base64 = base64.b64encode(img_content).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "offer": offer,
        "leading_number": leading_number,
        "offer_elements": offer_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("orders/print_offer.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Angebot_{offer.serial}-{offer.number}.pdf'
    return response
