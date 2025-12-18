from decimal import Decimal

from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField, ExpressionWrapper, Prefetch
from django.db.models.functions import Coalesce
from django.utils import timezone
from datetime import datetime, timedelta

from weasyprint import HTML, CSS
import base64

from orders.models import Order, OrderElement
from persons.models import Person
from payments.models import PaymentElement
from .models import Invoice, InvoiceElement, Proforma, ProformaElement
from services.models import Serial
from common.helpers import get_date_range, get_search_params, paginate_objects


# ----------------------------
# Helpers (view-level)
# ----------------------------

def _invoice_elements_total_expr(prefix: str = "element__") -> ExpressionWrapper:
    """
    Builds an expression for quantity * price.
    prefix = "element__" (InvoiceElement -> OrderElement)
    """
    return ExpressionWrapper(
        F(f"{prefix}quantity") * F(f"{prefix}price"),
        output_field=DecimalField(max_digits=12, decimal_places=2),
    )


def _recalculate_order_invoiced_for_orders(order_ids: set[int]) -> None:
    """
    Updates Order.invoiced (NET) as sum of invoice-linked OrderElements totals,
    excluding cancellation/cancelled invoices.
    """
    if not order_ids:
        return

    total_expr = _invoice_elements_total_expr(prefix="element__")

    for oid in order_ids:
        total = (
            InvoiceElement.objects
            .filter(
                element__order_id=oid,
                invoice__cancellation_to__isnull=True,
                invoice__cancelled_from__isnull=True,
            )
            .aggregate(total=Coalesce(Sum(total_expr), Value(0, output_field=DecimalField())))
            .get("total")
            or Decimal("0")
        )
        Order.objects.filter(id=oid).update(invoiced=total)


def _sync_invoice_after_elements(invoice: Invoice) -> None:
    """
    Recalculate invoice.value from InvoiceElement links.
    For cancellation invoices: force value negative and set payed=value (negative) to satisfy clean rules.
    """
    invoice.recalculate_from_elements(save=False)

    if invoice.cancellation_to_id:
        invoice.value = -abs(invoice.value or Decimal("0"))
        # Important: because Invoice.clean() has rule payed <= value,
        # for negative invoices we keep payed == value (negative) so it passes.
        invoice.payed = invoice.value
        invoice.save()  # uses DocumentBase.save() to recompute VAT too
    else:
        invoice.save()  # recompute VAT
        # keep payed cache consistent
        invoice.recalculate_payed_from_payments(save=True)


def _sync_proforma_after_elements(proforma: Proforma) -> None:
    proforma.recalculate_from_elements(save=True)


# ----------------------------
# Views
# ----------------------------

@login_required(login_url="/login/")
def invoices(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    base_qs = (
        Invoice.objects
        .select_related("person", "currency", "modified_by", "created_by")  # <- fără status
        .filter(
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description
        )
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client)
        )
    )

    # Prefetch invoice elements -> order elements -> order
    inv_el_qs = (
        InvoiceElement.objects
        .select_related("element", "element__order", "element__order__currency")
        .order_by("id")
    )
    base_qs = base_qs.prefetch_related(Prefetch("elements", queryset=inv_el_qs))

    person_invoices = []
    for inv in base_qs:
        invoice_elements = list(inv.elements.all())
        orders = list({e.element.order for e in invoice_elements if e.element and e.element.order_id})
        payed_pct = int((inv.payed / inv.value) * 100) if inv.value else 0
        proforma = Proforma.objects.filter(invoice=inv).first()

        person_invoices.append({
            "invoice": inv,
            "payed": payed_pct,
            "value": inv.value,
            "orders": orders,
            "proforma": proforma,
        })

    sort_keys = {
        "type": lambda x: x["invoice"].is_client,
        "invoice": lambda x: (x["invoice"].serial or "", x["invoice"].number or ""),
        "person": lambda x: (x["invoice"].person.firstname if x["invoice"].person else ""),
        "assignee": lambda x: (x["invoice"].modified_by.first_name if x["invoice"].modified_by else ""),
        "registered": lambda x: x["invoice"].created_at or timezone.now(),
        "deadline": lambda x: x["invoice"].deadline or timezone.localdate(),
        "value": lambda x: x["value"] or Decimal("0"),
        "payed": lambda x: x["payed"] or 0,
        "update": lambda x: x["invoice"].modified_at or timezone.now(),
    }
    person_invoices.sort(
        key=sort_keys.get(sort, lambda x: x["invoice"].created_at or timezone.now()),
        reverse=(sort not in ["person", "payed"])
    )

    invoices_on_page = paginate_objects(request, person_invoices)

    return render(
        request,
        "payments/invoices.html",
        {
            "person_invoices": invoices_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def cancellation_invoice(request, invoice_id):
    """
    Create a cancellation (storno) invoice for an existing invoice.
    With current model constraints, we represent storno as:
    - cancellation invoice with negative value
    - payed equals value (negative) so it is not considered unpaid
    - copy invoice elements
    - link invoices via cancellation_to / cancelled_from
    - update orders.invoiced totals
    """
    cancelled_invoice = get_object_or_404(Invoice, id=invoice_id)
    serials = Serial.get_solo()

    with transaction.atomic():
        cancellation = Invoice.objects.create(
            serial=serials.invoice_serial,
            number=str(serials.invoice_number),
            person=cancelled_invoice.person,
            is_client=cancelled_invoice.is_client,
            modified_by=request.user,
            created_by=request.user,
            currency=cancelled_invoice.currency,
            cancellation_to=cancelled_invoice,
            description="Stornorechnung",
            value=Decimal("0"),   # will be computed from elements
            payed=Decimal("0"),
            vat_rate=cancelled_invoice.vat_rate,  # keep same VAT rate
        )

        # link back
        cancelled_invoice.cancelled_from = cancellation
        cancelled_invoice.save(update_fields=["cancelled_from"])

        # copy links
        src_elements = InvoiceElement.objects.filter(invoice=cancelled_invoice).values_list("element_id", flat=True)
        for eid in src_elements:
            InvoiceElement.objects.create(invoice=cancellation, element_id=eid)

        # recalc value, set negative, set payed=value (negative)
        _sync_invoice_after_elements(cancellation)

        # update invoiced totals on involved orders
        order_ids = set(
            OrderElement.objects.filter(id__in=src_elements).values_list("order_id", flat=True)
        )
        _recalculate_order_invoiced_for_orders(order_ids)

        # increment serial
        serials.invoice_number += 1
        serials.save(update_fields=["invoice_number"])

    return redirect("invoices")


@login_required(login_url="/login/")
def invoice(request, invoice_id, person_id, order_id):
    invoice_elements = []
    date_now = timezone.localtime()
    date_plus_five = timezone.localdate() + timedelta(days=5)

    person = get_object_or_404(Person, id=person_id)
    serials = Serial.get_solo()

    # Resolve order (optional)
    order = get_object_or_404(Order, id=order_id) if int(order_id) > 0 else None
    is_client = order.is_client if order else True

    # Resolve invoice
    if int(invoice_id) > 0:
        invoice = get_object_or_404(Invoice.objects.select_related("currency", "person"), id=invoice_id)
        new = False
        last_invoice = Invoice.objects.order_by("-id").first()
        last = True if (last_invoice and last_invoice.id == invoice.id) else False
    else:
        invoice = None
        new = True
        last = True

    # default serial/number
    invoice_serial = serials.invoice_serial
    invoice_number = str(serials.invoice_number)

    # For provider invoices, serial/number might be empty/manual
    if order and order.is_client is False:
        invoice_serial = ""
        invoice_number = ""

    if invoice:
        invoice_serial = invoice.serial
        invoice_number = invoice.number

    # -----------------------------
    # Determine uninvoiced elements
    # -----------------------------
    all_order_elements = (
        OrderElement.objects
        .exclude(status__percent__lt=1)
        .filter(order__person=person)
        .select_related("order", "service", "status")
        .order_by("id")
    )

    invoiced_element_ids = (
        InvoiceElement.objects
        .filter(invoice__person=person)
        .values_list("element_id", flat=True)
    )

    uninvoiced_elements = all_order_elements.exclude(id__in=invoiced_element_ids)

    # Special: if current invoice is a cancellation, allow adding missing items from the cancelled invoice
    if invoice and invoice.cancellation_to_id:
        cancelled_elements = InvoiceElement.objects.filter(invoice=invoice.cancellation_to)
        already_on_this_invoice_ids = InvoiceElement.objects.filter(invoice=invoice).values_list("element_id", flat=True)
        cancelled_missing = cancelled_elements.exclude(element_id__in=already_on_this_invoice_ids).values_list("element_id", flat=True)
        cancelled_missing_order_elements = OrderElement.objects.filter(id__in=cancelled_missing)
        uninvoiced_elements = uninvoiced_elements | cancelled_missing_order_elements

    # -----------------------------------
    # Existing invoice edit
    # -----------------------------------
    if invoice:
        invoice_elements = (
            InvoiceElement.objects
            .filter(invoice=invoice)
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )

        if request.method == "POST":
            with transaction.atomic():
                if "invoice_description" in request.POST:
                    invoice.description = request.POST.get("invoice_description", "")

                    # provider invoice manual serial/number
                    if invoice.is_client is False:
                        i_serial = request.POST.get("invoice_serial")
                        if i_serial is not None:
                            invoice.serial = (i_serial or "").upper()
                            invoice_serial = invoice.serial
                        i_number = request.POST.get("invoice_number")
                        if i_number is not None:
                            invoice.number = (i_number or "").upper()
                            invoice_number = invoice.number

                    deadline_date = request.POST.get("deadline_date")
                    invoice_date = request.POST.get("invoice_date")

                    try:
                        invoice.deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                    except Exception:
                        invoice.deadline = timezone.localdate()

                    try:
                        d = datetime.strptime(invoice_date, "%Y-%m-%d").date()
                        invoice.created_at = timezone.make_aware(datetime.combine(d, date_now.time()))
                    except Exception:
                        pass

                    invoice.modified_by = request.user
                    invoice.modified_at = date_now
                    invoice.save()

                # Remove an invoice element (only if more than 1)
                if "invoice_element_id" in request.POST:
                    try:
                        inv_el_id = int(request.POST.get("invoice_element_id"))
                        if InvoiceElement.objects.filter(invoice=invoice).count() > 1:
                            inv_el = InvoiceElement.objects.filter(id=inv_el_id, invoice=invoice).first()
                            if inv_el:
                                touched_orders = {inv_el.element.order_id} if inv_el.element_id else set()
                                inv_el.delete()
                                _sync_invoice_after_elements(invoice)
                                _recalculate_order_invoiced_for_orders(touched_orders)
                    except Exception:
                        pass

                # Add an uninvoiced element
                if "uninvoiced_element_id" in request.POST:
                    try:
                        un_id = int(request.POST.get("uninvoiced_element_id"))
                        element = uninvoiced_elements.get(id=un_id)
                        InvoiceElement.objects.get_or_create(invoice=invoice, element=element)
                        _sync_invoice_after_elements(invoice)
                        _recalculate_order_invoiced_for_orders({element.order_id})
                    except Exception:
                        pass

                # After any change, ensure totals are correct
                _sync_invoice_after_elements(invoice)

        # end POST

    # -----------------------------------
    # New invoice creation
    # -----------------------------------
    else:
        if request.method == "POST" and "invoice_description" in request.POST and order:
            with transaction.atomic():
                invoice_description = request.POST.get("invoice_description", "")

                # serial/number assignment
                if order.is_client is False:
                    invoice_serial = request.POST.get("invoice_serial") or "??"
                    invoice_number = request.POST.get("invoice_number") or "???"
                else:
                    # reserve number
                    serials.invoice_number += 1
                    serials.save(update_fields=["invoice_number"])

                deadline_date = request.POST.get("deadline_date")
                invoice_date = request.POST.get("invoice_date")

                try:
                    invoice_deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                except Exception:
                    invoice_deadline = timezone.localdate()

                created_at = date_now
                try:
                    d = datetime.strptime(invoice_date, "%Y-%m-%d").date()
                    created_at = timezone.make_aware(datetime.combine(d, date_now.time()))
                except Exception:
                    pass

                invoice = Invoice.objects.create(
                    created_at=created_at,
                    description=invoice_description,
                    serial=invoice_serial,
                    number=invoice_number,
                    person=person,
                    deadline=invoice_deadline,
                    is_client=order.is_client,
                    modified_by=request.user,
                    created_by=request.user,
                    currency=order.currency,
                    value=Decimal("0"),
                    payed=Decimal("0"),
                    vat_rate=order.vat_rate if hasattr(order, "vat_rate") else Decimal("0"),
                )

                # Attach all uninvoiced elements
                for element in uninvoiced_elements:
                    InvoiceElement.objects.get_or_create(invoice=invoice, element=element)

                _sync_invoice_after_elements(invoice)

                # update order invoiced totals (all orders touched by the elements)
                order_ids = set(
                    InvoiceElement.objects.filter(invoice=invoice).values_list("element__order_id", flat=True)
                )
                _recalculate_order_invoiced_for_orders(order_ids)

                return redirect(
                    "invoice",
                    invoice_id=invoice.id,
                    order_id=order.id if order else 0,
                    person_id=person.id,
                )

    return render(
        request,
        "payments/invoice.html",
        {
            "person": person,
            "invoice": invoice,
            "invoice_serial": invoice_serial,
            "invoice_number": invoice_number,
            "is_client": (invoice.is_client if invoice else is_client),
            "invoice_elements": invoice_elements,
            "uninvoiced_elements": uninvoiced_elements,
            "new": new,
            "last": last,
            "date_plus_five": date_plus_five,
        },
    )


@login_required(login_url="/login/")
def print_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = (
        InvoiceElement.objects
        .exclude(element__status__id="6")
        .filter(invoice=invoice)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    date1 = invoice.created_at.date() if invoice.created_at else timezone.localdate()
    date2 = invoice.deadline
    day_left = (date2 - date1).days if date2 else 0

    leading_invoice = (invoice.number or "").rjust(4, "0")

    proforma = Proforma.objects.filter(invoice=invoice).first()
    proforma_number = proforma.number if proforma else ""
    leading_proforma = (proforma_number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        invoice_css = f.read()

    context = {
        "invoice": invoice,
        "proforma": proforma,
        "day_left": day_left,
        "leading_invoice": leading_invoice,
        "leading_proforma": leading_proforma,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("payments/print_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_css)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Rechnung-{invoice.serial}-{invoice.number}.pdf'
    return response


@login_required(login_url="/login/")
def print_cancellation_invoice(request, invoice_id):
    invoice = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = (
        InvoiceElement.objects
        .exclude(element__status__id="6")
        .filter(invoice=invoice)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    leading_storno = (invoice.number or "").rjust(4, "0")
    leading_invoice = (invoice.cancellation_to.number if invoice.cancellation_to else "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        invoice_css = f.read()

    context = {
        "invoice": invoice,
        "leading_storno": leading_storno,
        "leading_invoice": leading_invoice,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("payments/print_cancellation_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_css)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Stornorechnung-{invoice.serial}-{invoice.number}.pdf'
    return response


@login_required(login_url="/login/")
def proformas(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    qs = (
        Proforma.objects
        .select_related("person", "currency", "modified_by", "created_by", "invoice")
        .filter(
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description
        )
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client)
        )
    )

    pf_el_qs = (
        ProformaElement.objects
        .select_related("element", "element__order", "element__order__currency")
        .order_by("id")
    )
    qs = qs.prefetch_related(Prefetch("elements", queryset=pf_el_qs))

    person_proformas = []
    for p in qs:
        proforma_elements = list(p.elements.all())
        orders = list({e.element.order for e in proforma_elements if e.element and e.element.order_id})
        person_proformas.append({"proforma": p, "value": p.value, "orders": orders})

    sort_keys = {
        "proforma": lambda x: (x["proforma"].serial or "", x["proforma"].number or ""),
        "person": lambda x: (x["proforma"].person.firstname if x["proforma"].person else ""),
        "assignee": lambda x: (x["proforma"].modified_by.first_name if x["proforma"].modified_by else ""),
        "registered": lambda x: x["proforma"].created_at or timezone.now(),
        "deadline": lambda x: x["proforma"].deadline or timezone.localdate(),
        "status": lambda x: (x["proforma"].status.id if getattr(x["proforma"], "status", None) else 0),
        "value": lambda x: x["value"] or Decimal("0"),
        "update": lambda x: x["proforma"].modified_at or timezone.now(),
    }
    person_proformas.sort(
        key=sort_keys.get(sort, lambda x: x["proforma"].created_at or timezone.now()),
        reverse=(sort not in ["person"])
    )

    proformas_on_page = paginate_objects(request, person_proformas)

    return render(
        request,
        "payments/proformas.html",
        {
            "person_proformas": proformas_on_page,
            "sort": sort,
            "search_client": search_client,
            "search_description": search_description,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def proforma(request, proforma_id, person_id, order_id):
    date_now = timezone.localtime()
    date_plus_five = timezone.localdate() + timedelta(days=5)

    person = get_object_or_404(Person, id=person_id)
    serials = Serial.get_solo()

    proforma_serial = serials.proforma_serial
    proforma_number = str(serials.proforma_number)

    order = get_object_or_404(Order, id=order_id) if int(order_id) > 0 else None

    if int(proforma_id) > 0:
        proforma = get_object_or_404(Proforma.objects.select_related("currency", "person"), id=proforma_id)
        new = False
    else:
        proforma = None
        new = True

    if proforma:
        proforma_serial = proforma.serial
        proforma_number = proforma.number

    # elements eligible
    all_elements = (
        OrderElement.objects
        .exclude(status__percent__lt=1)
        .exclude(status__percent__gt=100)
        .exclude(order__is_client=False)
        .filter(order__person=person)
        .order_by("id")
    )
    proformed_ids = (
        ProformaElement.objects
        .filter(proforma__person=person)
        .values_list("element_id", flat=True)
    )
    invoiced_ids = (
        InvoiceElement.objects
        .filter(invoice__person=person)
        .values_list("element_id", flat=True)
    )
    unproformed_elements = all_elements.exclude(id__in=invoiced_ids).exclude(id__in=proformed_ids)

    if proforma:
        proforma_elements = (
            ProformaElement.objects
            .filter(proforma=proforma)
            .exclude(element__status__percent="0")
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )
    else:
        proforma_elements = []

    if proforma:
        if request.method == "POST":
            with transaction.atomic():
                if "proforma_description" in request.POST:
                    proforma.description = request.POST.get("proforma_description", "")
                    deadline_date = request.POST.get("deadline_date")
                    try:
                        # Proforma.deadline in your model is DateField -> keep it date
                        proforma.deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                    except Exception:
                        proforma.deadline = timezone.localdate()

                if "proforma_element_id" in request.POST:
                    try:
                        pe_id = int(request.POST.get("proforma_element_id"))
                        if ProformaElement.objects.filter(proforma=proforma).count() > 1:
                            ProformaElement.objects.filter(id=pe_id, proforma=proforma).delete()
                    except Exception:
                        pass

                if "unproformed_element_id" in request.POST:
                    try:
                        ue_id = int(request.POST.get("unproformed_element_id"))
                        element = unproformed_elements.get(id=ue_id)
                        ProformaElement.objects.get_or_create(proforma=proforma, element=element)
                    except Exception:
                        pass

                proforma.modified_by = request.user
                proforma.modified_at = date_now
                proforma.save()
                _sync_proforma_after_elements(proforma)

    else:
        if request.method == "POST" and "proforma_description" in request.POST and order:
            with transaction.atomic():
                proforma_description = request.POST.get("proforma_description", "")

                deadline_date = request.POST.get("deadline_date")
                try:
                    proforma_deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                except Exception:
                    proforma_deadline = timezone.localdate()

                proforma = Proforma.objects.create(
                    description=proforma_description,
                    serial=proforma_serial,
                    number=proforma_number,
                    person=person,
                    deadline=proforma_deadline,
                    is_client=True,
                    modified_by=request.user,
                    created_by=request.user,
                    currency=order.currency,
                    value=Decimal("0"),
                    vat_rate=order.vat_rate if hasattr(order, "vat_rate") else Decimal("0"),
                )

                for element in unproformed_elements:
                    ProformaElement.objects.get_or_create(proforma=proforma, element=element)

                _sync_proforma_after_elements(proforma)

                serials.proforma_number += 1
                serials.save(update_fields=["proforma_number"])

                return redirect(
                    "proforma",
                    proforma_id=proforma.id,
                    order_id=order.id if order else 0,
                    person_id=person.id,
                )

    return render(
        request,
        "payments/proforma.html",
        {
            "person": person,
            "proforma": proforma,
            "proforma_serial": proforma_serial,
            "proforma_number": proforma_number,
            "proforma_elements": proforma_elements,
            "unproformed_elements": unproformed_elements,
            "new": new,
            "date_plus_five": date_plus_five,
        },
    )


@login_required(login_url="/login/")
def print_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = (
        ProformaElement.objects
        .exclude(element__status__id="6")
        .filter(proforma=proforma)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    date1 = proforma.created_at.date() if proforma.created_at else timezone.localdate()
    date2 = proforma.deadline
    day_left = (date2 - date1).days if date2 else 0
    leading_number = (proforma.number or "").rjust(3, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "proforma": proforma,
        "day_left": day_left,
        "leading_number": leading_number,
        "proforma_elements": proforma_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("payments/print_proforma.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Proforma-{proforma.serial}-{proforma.number}.pdf'
    return response


@login_required(login_url="/login/")
def convert_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma.objects.select_related("currency", "person"), id=proforma_id)
    serials = Serial.get_solo()

    proforma_elements = (
        ProformaElement.objects
        .exclude(element__status__percent__lt=1)
        .filter(proforma=proforma)
        .select_related("element")
        .order_by("id")
    )

    with transaction.atomic():
        invoice = Invoice.objects.create(
            description=proforma.description,
            serial=serials.invoice_serial,
            number=str(serials.invoice_number),
            person=proforma.person,
            deadline=proforma.deadline,
            is_client=True,
            modified_by=request.user,
            created_by=request.user,
            currency=proforma.currency,
            value=Decimal("0"),
            payed=Decimal("0"),
            vat_rate=proforma.vat_rate,
        )

        serials.invoice_number += 1
        serials.save(update_fields=["invoice_number"])

        for pe in proforma_elements:
            InvoiceElement.objects.create(invoice=invoice, element=pe.element)

        _sync_invoice_after_elements(invoice)

        proforma.invoice = invoice
        proforma.save(update_fields=["invoice"])

    return redirect(
        "invoice",
        invoice_id=invoice.pk,
        person_id=invoice.person.pk,
        order_id=0
    )
