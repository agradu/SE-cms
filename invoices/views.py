from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Sum, F, Value, DecimalField, Prefetch
from django.db.models.functions import Coalesce
from django.http import HttpResponse
from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.utils import timezone
from datetime import datetime, timedelta

from weasyprint import HTML, CSS
import base64

from orders.models import Order, OrderElement
from persons.models import Person
from .models import Invoice, InvoiceElement, Proforma, ProformaElement
from core.models import Serial
from common.helpers import get_date_range, get_search_params, paginate_objects

from .services import InvoiceService


def _validation_error_to_text(e: ValidationError) -> str:
    if hasattr(e, "message_dict"):
        parts = []
        for field, msgs in e.message_dict.items():
            for m in msgs:
                parts.append(f"{field}: {m}")
        return " | ".join(parts) if parts else str(e)
    if hasattr(e, "messages"):
        return " | ".join(e.messages)
    return str(e)


# ----------------------------
# INVOICES (list)
# ----------------------------
@login_required(login_url="/login/")
def invoices(request):
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)
    sort = request.GET.get("sort")

    base_qs = (
        Invoice.objects
        .select_related("person", "currency", "modified_by", "created_by")
        .filter(
            created_at__range=(filter_start, filter_end),
            description__icontains=search_description,
        )
        .filter(
            Q(person__firstname__icontains=search_client) |
            Q(person__lastname__icontains=search_client) |
            Q(person__company_name__icontains=search_client)
        )
    )

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


# ----------------------------
# STORNO
# ----------------------------
@login_required(login_url="/login/")
def cancellation_invoice(request, invoice_id):
    cancelled_invoice = get_object_or_404(Invoice, id=invoice_id)
    serials = Serial.get_solo()

    try:
        InvoiceService.create_cancellation_invoice(
            cancelled_invoice=cancelled_invoice,
            user=request.user,
            serials=serials,
        )
        messages.success(request, "Stornorechnung a fost creată.")
    except ValidationError as e:
        messages.error(request, _validation_error_to_text(e))
    except Exception as e:
        messages.error(request, f"Eroare: {e}")

    return redirect("invoices")


# ----------------------------
# INVOICE (detail/edit/create)
# ----------------------------
@login_required(login_url="/login/")
def invoice(request, invoice_id, person_id, order_id):
    date_now = timezone.localtime()
    date_plus_five = timezone.localdate() + timedelta(days=5)

    person = get_object_or_404(Person, id=person_id)
    serials = Serial.get_solo()

    order = get_object_or_404(Order, id=order_id) if int(order_id) > 0 else None
    is_client = order.is_client if order else True

    # Resolve invoice
    if int(invoice_id) > 0:
        invoice_obj = get_object_or_404(Invoice.objects.select_related("currency", "person"), id=invoice_id)
        new = False
        last_invoice = Invoice.objects.order_by("-id").first()
        last = bool(last_invoice and last_invoice.id == invoice_obj.id)
    else:
        invoice_obj = None
        new = True
        last = True

    # Default serial/number for UI
    invoice_serial = serials.invoice_serial
    invoice_number = str(serials.invoice_number)

    # Provider invoices might be manual
    if order and order.is_client is False:
        invoice_serial = ""
        invoice_number = ""

    if invoice_obj:
        invoice_serial = invoice_obj.serial
        invoice_number = invoice_obj.number

    # -----------------------------
    # Determine eligible (uninvoiced) elements
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

    # Special: for storno invoice allow adding missing items from original invoice
    if invoice_obj and invoice_obj.cancellation_to_id:
        cancelled_elements = InvoiceElement.objects.filter(invoice=invoice_obj.cancellation_to)
        already_ids = InvoiceElement.objects.filter(invoice=invoice_obj).values_list("element_id", flat=True)
        missing_ids = cancelled_elements.exclude(element_id__in=already_ids).values_list("element_id", flat=True)
        missing_order_elements = OrderElement.objects.filter(id__in=missing_ids)
        uninvoiced_elements = uninvoiced_elements | missing_order_elements

    # Load invoice elements
    invoice_elements = []
    if invoice_obj:
        invoice_elements = list(
            InvoiceElement.objects
            .filter(invoice=invoice_obj)
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )

    # ----------------------------
    # POST actions
    # ----------------------------
    if request.method == "POST":
        form = request.POST

        try:
            with transaction.atomic():
                # -----------------------------------
                # Update existing invoice header
                # -----------------------------------
                if invoice_obj and "invoice_description" in form:
                    invoice_obj.description = form.get("invoice_description", "")

                    # provider invoice manual serial/number
                    if invoice_obj.is_client is False:
                        i_serial = form.get("invoice_serial")
                        i_number = form.get("invoice_number")
                        if i_serial is not None:
                            invoice_obj.serial = (i_serial or "").upper()
                            invoice_serial = invoice_obj.serial
                        if i_number is not None:
                            invoice_obj.number = (i_number or "").upper()
                            invoice_number = invoice_obj.number

                    deadline_date = form.get("deadline_date")
                    invoice_date = form.get("invoice_date")

                    try:
                        invoice_obj.deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                    except Exception:
                        invoice_obj.deadline = timezone.localdate()

                    try:
                        d = datetime.strptime(invoice_date, "%Y-%m-%d").date()
                        invoice_obj.created_at = timezone.make_aware(datetime.combine(d, date_now.time()))
                    except Exception:
                        pass

                    invoice_obj.modified_by = request.user
                    invoice_obj.modified_at = date_now
                    invoice_obj.save()

                # -----------------------------------
                # Remove an invoice element
                # -----------------------------------
                if invoice_obj and "invoice_element_id" in form:
                    inv_el_id = int(form.get("invoice_element_id") or 0)
                    if inv_el_id:
                        if InvoiceElement.objects.filter(invoice=invoice_obj).count() <= 1:
                            raise ValidationError("Nu poți șterge singurul element dintr-o factură.")
                        inv_el = InvoiceElement.objects.select_related("element").filter(id=inv_el_id, invoice=invoice_obj).first()
                        if inv_el:
                            touched_order_id = inv_el.element.order_id if inv_el.element_id else None
                            inv_el.delete()
                            InvoiceService.sync_invoice_after_elements(invoice_obj)
                            if touched_order_id:
                                InvoiceService.recalculate_order_invoiced_for_orders([touched_order_id])

                # -----------------------------------
                # Add an uninvoiced element
                # -----------------------------------
                if invoice_obj and "uninvoiced_element_id" in form:
                    un_id = int(form.get("uninvoiced_element_id") or 0)
                    if un_id:
                        element = uninvoiced_elements.get(id=un_id)
                        InvoiceElement.objects.get_or_create(invoice=invoice_obj, element=element)
                        InvoiceService.sync_invoice_after_elements(invoice_obj)
                        InvoiceService.recalculate_order_invoiced_for_orders([element.order_id])

                # -----------------------------------
                # Create new invoice
                # -----------------------------------
                if (not invoice_obj) and ("invoice_description" in form) and order:
                    invoice_description = form.get("invoice_description", "")

                    # serial/number assignment
                    if order.is_client is False:
                        invoice_serial = form.get("invoice_serial") or "??"
                        invoice_number = form.get("invoice_number") or "???"
                    else:
                        # reserve number
                        serials.invoice_number += 1
                        serials.save(update_fields=["invoice_number"])

                    deadline_date = form.get("deadline_date")
                    invoice_date = form.get("invoice_date")

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

                    invoice_obj = Invoice.objects.create(
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
                        vat_rate=getattr(order, "vat_rate", Decimal("0")) or Decimal("0"),
                    )

                    # Attach all uninvoiced elements
                    for element in uninvoiced_elements:
                        InvoiceElement.objects.get_or_create(invoice=invoice_obj, element=element)

                    InvoiceService.sync_invoice_after_elements(invoice_obj)

                    # update order invoiced totals
                    order_ids = set(
                        InvoiceElement.objects.filter(invoice=invoice_obj).values_list("element__order_id", flat=True)
                    )
                    InvoiceService.recalculate_order_invoiced_for_orders(order_ids)

                    return redirect(
                        "invoice",
                        invoice_id=invoice_obj.id,
                        order_id=order.id if order else 0,
                        person_id=person.id,
                    )

                # ensure sync after any changes on existing
                if invoice_obj:
                    InvoiceService.sync_invoice_after_elements(invoice_obj)

        except ValidationError as e:
            messages.error(request, _validation_error_to_text(e))
        except Exception as e:
            messages.error(request, f"Eroare: {e}")

    # Reload elements for render
    if invoice_obj:
        invoice_elements = list(
            InvoiceElement.objects
            .filter(invoice=invoice_obj)
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )

    return render(
        request,
        "payments/invoice.html",
        {
            "person": person,
            "invoice": invoice_obj,
            "invoice_serial": invoice_serial,
            "invoice_number": invoice_number,
            "is_client": (invoice_obj.is_client if invoice_obj else is_client),
            "invoice_elements": invoice_elements,
            "uninvoiced_elements": uninvoiced_elements,
            "new": new,
            "last": last,
            "date_plus_five": date_plus_five,
        },
    )


# ----------------------------
# PRINTING
# ----------------------------
@login_required(login_url="/login/")
def print_invoice(request, invoice_id):
    invoice_obj = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = (
        InvoiceElement.objects
        .exclude(element__status__id="6")
        .filter(invoice=invoice_obj)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    date1 = invoice_obj.created_at.date() if invoice_obj.created_at else timezone.localdate()
    date2 = invoice_obj.deadline
    day_left = (date2 - date1).days if date2 else 0

    leading_invoice = (invoice_obj.number or "").rjust(4, "0")

    proforma = Proforma.objects.filter(invoice=invoice_obj).first()
    proforma_number = proforma.number if proforma else ""
    leading_proforma = (proforma_number or "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        invoice_css = f.read()

    context = {
        "invoice": invoice_obj,
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
    response["Content-Disposition"] = f'filename=Rechnung-{invoice_obj.serial}-{invoice_obj.number}.pdf'
    return response


@login_required(login_url="/login/")
def print_cancellation_invoice(request, invoice_id):
    invoice_obj = get_object_or_404(Invoice, id=invoice_id)
    invoice_elements = (
        InvoiceElement.objects
        .exclude(element__status__id="6")
        .filter(invoice=invoice_obj)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    leading_storno = (invoice_obj.number or "").rjust(4, "0")
    leading_invoice = (invoice_obj.cancellation_to.number if invoice_obj.cancellation_to else "").rjust(4, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        invoice_css = f.read()

    context = {
        "invoice": invoice_obj,
        "leading_storno": leading_storno,
        "leading_invoice": leading_invoice,
        "invoice_elements": invoice_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("payments/print_cancellation_invoice.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=invoice_css)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Stornorechnung-{invoice_obj.serial}-{invoice_obj.number}.pdf'
    return response


# ----------------------------
# PROFORMAS (list/detail/convert/print)
# ----------------------------
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
        proforma_obj = get_object_or_404(Proforma.objects.select_related("currency", "person"), id=proforma_id)
        new = False
    else:
        proforma_obj = None
        new = True

    if proforma_obj:
        proforma_serial = proforma_obj.serial
        proforma_number = proforma_obj.number

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

    proforma_elements = []
    if proforma_obj:
        proforma_elements = list(
            ProformaElement.objects
            .filter(proforma=proforma_obj)
            .exclude(element__status__percent="0")
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )

    if request.method == "POST":
        form = request.POST
        try:
            with transaction.atomic():
                if proforma_obj:
                    if "proforma_description" in form:
                        proforma_obj.description = form.get("proforma_description", "")
                        deadline_date = form.get("deadline_date")
                        try:
                            proforma_obj.deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                        except Exception:
                            proforma_obj.deadline = timezone.localdate()

                    if "proforma_element_id" in form:
                        pe_id = int(form.get("proforma_element_id") or 0)
                        if pe_id:
                            if ProformaElement.objects.filter(proforma=proforma_obj).count() <= 1:
                                raise ValidationError("Nu poți șterge singurul element din proformă.")
                            ProformaElement.objects.filter(id=pe_id, proforma=proforma_obj).delete()

                    if "unproformed_element_id" in form:
                        ue_id = int(form.get("unproformed_element_id") or 0)
                        if ue_id:
                            element = unproformed_elements.get(id=ue_id)
                            ProformaElement.objects.get_or_create(proforma=proforma_obj, element=element)

                    proforma_obj.modified_by = request.user
                    proforma_obj.modified_at = date_now
                    proforma_obj.save()
                    InvoiceService.sync_proforma_after_elements(proforma_obj)

                else:
                    if ("proforma_description" in form) and order:
                        proforma_description = form.get("proforma_description", "")

                        deadline_date = form.get("deadline_date")
                        try:
                            proforma_deadline = datetime.strptime(deadline_date, "%Y-%m-%d").date()
                        except Exception:
                            proforma_deadline = timezone.localdate()

                        proforma_obj = Proforma.objects.create(
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
                            vat_rate=getattr(order, "vat_rate", Decimal("0")) or Decimal("0"),
                        )

                        for element in unproformed_elements:
                            ProformaElement.objects.get_or_create(proforma=proforma_obj, element=element)

                        InvoiceService.sync_proforma_after_elements(proforma_obj)

                        serials.proforma_number += 1
                        serials.save(update_fields=["proforma_number"])

                        return redirect(
                            "proforma",
                            proforma_id=proforma_obj.id,
                            order_id=order.id if order else 0,
                            person_id=person.id,
                        )
        except ValidationError as e:
            messages.error(request, _validation_error_to_text(e))
        except Exception as e:
            messages.error(request, f"Eroare: {e}")

    # reload for render
    if proforma_obj:
        proforma_elements = list(
            ProformaElement.objects
            .filter(proforma=proforma_obj)
            .exclude(element__status__percent="0")
            .select_related("element", "element__order", "element__service")
            .order_by("element__order__created_at")
        )

    return render(
        request,
        "payments/proforma.html",
        {
            "person": person,
            "proforma": proforma_obj,
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
    proforma_obj = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = (
        ProformaElement.objects
        .exclude(element__status__id="6")
        .filter(proforma=proforma_obj)
        .select_related("element", "element__service", "element__order")
        .order_by("id")
    )

    date1 = proforma_obj.created_at.date() if proforma_obj.created_at else timezone.localdate()
    date2 = proforma_obj.deadline
    day_left = (date2 - date1).days if date2 else 0
    leading_number = (proforma_obj.number or "").rjust(3, "0")

    with open("static/images/logo-se.jpeg", "rb") as f:
        logo_bytes = f.read()
    logo_base64 = base64.b64encode(logo_bytes).decode("utf-8")

    with open("static/css/invoice.css", "rb") as f:
        css_content = f.read()

    context = {
        "proforma": proforma_obj,
        "day_left": day_left,
        "leading_number": leading_number,
        "proforma_elements": proforma_elements,
        "logo_base64": logo_base64,
    }
    html_content = render_to_string("payments/print_proforma.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=css_content)])
    response = HttpResponse(pdf_file, content_type="application/pdf")
    response["Content-Disposition"] = f'filename=Proforma-{proforma_obj.serial}-{proforma_obj.number}.pdf'
    return response


@login_required(login_url="/login/")
def convert_proforma(request, proforma_id):
    proforma_obj = get_object_or_404(Proforma.objects.select_related("currency", "person"), id=proforma_id)
    serials = Serial.get_solo()

    proforma_elements = (
        ProformaElement.objects
        .exclude(element__status__percent__lt=1)
        .filter(proforma=proforma_obj)
        .select_related("element")
        .order_by("id")
    )

    with transaction.atomic():
        invoice_obj = Invoice.objects.create(
            description=proforma_obj.description,
            serial=serials.invoice_serial,
            number=str(serials.invoice_number),
            person=proforma_obj.person,
            deadline=proforma_obj.deadline,
            is_client=True,
            modified_by=request.user,
            created_by=request.user,
            currency=proforma_obj.currency,
            value=Decimal("0"),
            payed=Decimal("0"),
            vat_rate=proforma_obj.vat_rate,
        )

        serials.invoice_number += 1
        serials.save(update_fields=["invoice_number"])

        for pe in proforma_elements:
            InvoiceElement.objects.create(invoice=invoice_obj, element=pe.element)

        InvoiceService.sync_invoice_after_elements(invoice_obj)

        proforma_obj.invoice = invoice_obj
        proforma_obj.save(update_fields=["invoice"])

    return redirect(
        "invoice",
        invoice_id=invoice_obj.pk,
        person_id=invoice_obj.person.pk,
        order_id=0
    )
