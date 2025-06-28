from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from .models import Order, OrderElement, Offer, OfferElement
from persons.models import Person
from invoices.models import Invoice, InvoiceElement, ProformaElement
from payments.models import Payment, PaymentElement
from services.models import Currency, Status, Service, UM, Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils.dateparse import parse_date
from django.utils import timezone
from weasyprint import HTML, CSS
import base64
from common.helpers import get_date_range, get_search_params, paginate_objects

# Create your views here.

@login_required(login_url="/login/")
def c_orders(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)

    sort = request.GET.get("sort")

    # Query filtered orders
    selected_orders = Order.objects.filter(
        is_client=True,
        created_at__range=(filter_start, filter_end),
        description__icontains=search_description
    ).filter(
        Q(person__firstname__icontains=search_client) |
        Q(person__lastname__icontains=search_client) |
        Q(person__company_name__icontains=search_client)
    )

    # Prepare orders list with invoicing details
    client_orders = []
    for o in selected_orders:
        order_elements = list(OrderElement.objects.filter(order=o).order_by("id"))
        
        # proformed = any(ProformaElement.objects.filter(element=e).exists() for e in order_elements)
        proformed = next((ProformaElement.objects.filter(element=e).first() for e in order_elements if ProformaElement.objects.filter(element=e).exists()), None)
        invoiced = int(o.invoiced / o.value * 100) if o.value else 0
        
        client_orders.append({"order": o, "elements": order_elements, "invoiced": invoiced, "proformed": proformed})
    
    # Sorting logic
    sort_keys = {
        "order": lambda x: x["order"].id,
        "client": lambda x: x["order"].person.firstname,
        "assignee": lambda x: x["order"].modified_by.first_name,
        "registered": lambda x: x["order"].created_at,
        "deadline": lambda x: x["order"].deadline,
        "status": lambda x: x["order"].status.percent,
        "value": lambda x: x["order"].value,
        "invoiced": lambda x: x["invoiced"],
        "update": lambda x: x["order"].modified_at,
    }

    client_orders.sort(key=sort_keys.get(sort, lambda x: x["order"].created_at), reverse=(sort not in ["client", "status"]))
    
    # Pagination
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

@login_required(login_url="/login/")
def c_order(request, order_id, client_id):
    # Default parts
    statuses = Status.objects.all().order_by("percent")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.objects.get(id=1)
    search = ""
    clients = []
    elements = []
    element = ""
    is_invoiced = False
    is_proformed = False
    date_now = timezone.now()
    if order_id != 0:  # if order exists
        new = False
        order = get_object_or_404(Order, id=order_id)
        client = order.person
        elements = OrderElement.objects.filter(order=order).order_by("id")
        is_invoiced = InvoiceElement.objects.filter(element__order=order).exists()
        is_proformed = ProformaElement.objects.filter(element__order=order).exists()
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_client" in request.POST and is_invoiced == False:
                new_client = request.POST.get("new_client")
                client = get_object_or_404(Person, id=new_client)
                order.person = client
                order.modified_at = date_now
            if "order_description" in request.POST:
                order.description = request.POST.get("order_description")
                order.status = Status.objects.get(id=request.POST.get("order_status"))
                for e in elements:
                    e.status = order.status
                    e.save()
                order.currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    order.deadline = timezone.make_aware(deadline_naive)
                except:
                    order.deadline = date_now
            if "element_id" in request.POST:
                element_id = int(request.POST.get("element_id"))
                if element_id > 0:  # edit an element
                    element = OrderElement.objects.get(id=element_id)
                else:  # add an element to order
                    element = OrderElement(order=order)
                service_id = int(request.POST.get("e_service"))
                element.service = Service.objects.get(id=service_id)
                element.description = request.POST.get("e_description")
                e_quantity = request.POST.get("e_quantity")
                if e_quantity and e_quantity.replace(".", "").isdigit():
                    element.quantity = float(e_quantity)
                else:
                    element.quantity = float(1.0)
                element.um = ums[int(request.POST.get("e_um")) - 1]
                e_price = request.POST.get("e_price")
                if e_price and e_price.replace(".", "").isdigit():
                    element.price = float(e_price)
                else:
                    element.price = float(1.0)
                element.status = Status.objects.get(id=int(request.POST.get("e_status")))
                element.save()
                # setting order status to minimum form elements
                status_elements = sorted(elements, key=lambda x: x.status.percent)
                order.status = status_elements[0].status
                element = ""  # clearing the active element
            if "delete_element_id" in request.POST:  # delete en element
                element_id = int(request.POST.get("delete_element_id"))
                element = OrderElement.objects.get(id=element_id)
                element.delete()
            if "edit_element_id" in request.POST:  # set an element editable in template
                element_id = int(request.POST.get("edit_element_id"))
                element = OrderElement.objects.get(id=element_id)
            # Setting the modiffied user and date
            order.modified_by = request.user
            order.modified_at = date_now
            # Calculating the order value
            order.value = 0
            for e in elements:
                order.value += (e.price * e.quantity)
                try:
                    # Calculating the invoice value if element is invoiced
                    invoice_element = InvoiceElement.objects.get(element=e)
                    invoice = invoice_element.invoice
                    invoice_elements = InvoiceElement.objects.filter(invoice=invoice)
                    invoice.value = 0
                    for ie in invoice_elements:
                        if ie.element.status.percent > 0:
                            invoice.value += (ie.element.price * ie.element.quantity)
                    invoice.save()
                except:
                    invoice = ""
            order.save()

    else:  # if order is new
        new = True
        if Person.objects.filter(id=client_id).exists():
            client = Person.objects.get(id=client_id)
        else:
            client = ""
        order = ""
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_client" in request.POST:
                new_client = request.POST.get("new_client")
                client = get_object_or_404(Person, id=new_client)
                return redirect(
                    "c_order",
                    order_id = 0,
                    client_id = client.id
                )
            if "order_description" in request.POST:
                description = request.POST.get("order_description")
                status = Status.objects.get(id=request.POST.get("order_status"))
                currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                except:
                    deadline = date_now 
                order = Order(
                    description = description,
                    serial = serials.order_serial,
                    number = serials.order_number,
                    person=client,
                    deadline=deadline,
                    is_client=True,
                    modified_by=request.user,
                    created_by=request.user,
                    status=status,
                    currency=currency,
                )
                order.save()
                serials.order_number += 1
                serials.save()
                new = False
                return redirect(
                    "c_order",
                    order_id = order.id,
                    client_id = client.id
                )

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
            "element_selected": element,
            "is_invoiced": is_invoiced,
            "is_proformed": is_proformed,
        },
    )

@login_required(login_url="/login/")
def c_offers(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)

    sort = request.GET.get("sort")

    # Query filtered offers
    selected_offers = Offer.objects.filter(
        created_at__range=(filter_start, filter_end),
        description__icontains=search_description
    ).filter(
        Q(person__firstname__icontains=search_client) |
        Q(person__lastname__icontains=search_client) |
        Q(person__company_name__icontains=search_client)
    )

    # Prepare offers list
    client_offers = [
        {"offer": o, "elements": list(OfferElement.objects.filter(offer=o).order_by("id")), "order": o.order}
        for o in selected_offers
    ]
    
    # Sorting logic
    sort_keys = {
        "offer": lambda x: x["offer"].id,
        "client": lambda x: x["offer"].person.firstname,
        "assignee": lambda x: x["offer"].modified_by.first_name,
        "registered": lambda x: x["offer"].created_at,
        "deadline": lambda x: x["offer"].deadline,
        "status": lambda x: x["offer"].status.percent,
        "value": lambda x: x["offer"].value,
        "update": lambda x: x["offer"].modified_at,
    }
    client_offers.sort(key=sort_keys.get(sort, lambda x: x["offer"].created_at), reverse=(sort not in ["client", "status"]))
    
    # Pagination
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

@login_required(login_url="/login/")
def c_offer(request, offer_id, client_id):
    # Default parts
    statuses = Status.objects.filter(id__range=(1,2)).order_by("id")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.objects.get(id=1)
    search = ""
    clients = []
    elements = []
    element = ""
    date_now = timezone.now()
    if offer_id != 0:  # if order exists
        new = False
        offer = get_object_or_404(Offer, id=offer_id)
        client = offer.person
        elements = OfferElement.objects.filter(offer=offer).order_by("id")
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_client" in request.POST:
                new_client = request.POST.get("new_client")
                client = get_object_or_404(Person, id=new_client)
                offer.person = client
                offer.modified_at = date_now
            if "offer_description" in request.POST:
                offer.description = request.POST.get("offer_description")
                offer.status = statuses[int(request.POST.get("offer_status")) - 1]
                for e in elements:
                    e.status = offer.status
                    e.save()
                offer.currency = currencies[int(request.POST.get("offer_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    offer.deadline = timezone.make_aware(deadline_naive)
                except:
                    offer.deadline = date_now
            if "element_id" in request.POST:
                element_id = int(request.POST.get("element_id"))
                if element_id > 0:  # edit an element
                    element = OfferElement.objects.get(id=element_id)
                else:  # add an element to order
                    element = OfferElement(offer=offer)
                service_id = int(request.POST.get("e_service"))
                element.service = Service.objects.get(id=service_id)
                element.description = request.POST.get("e_description")
                e_quantity = request.POST.get("e_quantity")
                if e_quantity and e_quantity.replace(".", "").isdigit():
                    element.quantity = float(e_quantity)
                else:
                    element.quantity = float(1.0)
                element.um = ums[int(request.POST.get("e_um")) - 1]
                e_price = request.POST.get("e_price")
                if e_price and e_price.replace(".", "").isdigit():
                    element.price = float(e_price)
                else:
                    element.price = float(1.0)
                element.save()
                element = ""  # clearing the active element
            if "delete_element_id" in request.POST:  # delete en element
                element_id = int(request.POST.get("delete_element_id"))
                element = OfferElement.objects.get(id=element_id)
                element.delete()
            if "edit_element_id" in request.POST:  # set an element editable in template
                element_id = int(request.POST.get("edit_element_id"))
                element = OfferElement.objects.get(id=element_id)
            # Setting the modiffied user and date
            offer.modified_by = request.user
            offer.modified_at = date_now
            # Calculating the offer value
            offer.value = 0
            for e in elements:
                offer.value += (e.price * e.quantity)
            offer.save()

    else:  # if offer is new
        new = True
        if Person.objects.filter(id=client_id).exists():
            client = Person.objects.get(id=client_id)
        else:
            client = ""
        offer = ""
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    clients = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_client" in request.POST:
                new_client = request.POST.get("new_client")
                client = get_object_or_404(Person, id=new_client)
                return redirect(
                    "c_offer",
                    offer_id = 0,
                    client_id = client.id
                )
            if "offer_description" in request.POST:
                description = request.POST.get("offer_description")
                status = statuses[int(request.POST.get("offer_status")) - 1]
                currency = currencies[int(request.POST.get("offer_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                    print ("DAAAAAAAAA NOU")
                except:
                    deadline = date_now
                    print ("NUUUUUUUUUUUU NOU")
                offer = Offer(
                    description = description,
                    serial = serials.offer_serial,
                    number = serials.offer_number,
                    person=client,
                    deadline=deadline,
                    modified_by=request.user,
                    created_by=request.user,
                    status=status,
                    currency=currency,
                )
                offer.save()
                serials.offer_number += 1
                serials.save()
                new = False
                return redirect(
                    "c_offer",
                    offer_id = offer.id,
                    client_id = client.id
                )

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
            "element_selected": element,
        },
    )

@login_required(login_url="/login/")
def convert_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    offer_elements = OfferElement.objects.filter(offer=offer).order_by("id")
    serials = get_object_or_404(Serial, id=1)
    statuses = Status.objects.filter(id__range=(1,2)).order_by("id")
    order = Order(
        description = offer.description,
        serial = serials.order_serial,
        number = serials.order_number,
        person= offer.person,
        deadline= offer.deadline,
        is_client=True,
        modified_by= request.user,
        created_by= request.user,
        currency= offer.currency,
        value= offer.value,
    )
    order.save()
    for e in offer_elements:
        element = OrderElement(
            order=order,
            service = e.service,
            description = e.description,
            quantity = e.quantity,
            um = e.um,
            price = e.price
        )
        element.save()
    offer.order = order
    offer.status = statuses[1]
    offer.save()
    serials.order_number += 1
    serials.save()

    return redirect(
        "c_order",
        order_id=order.pk,
        client_id=order.person.pk
    )

@login_required(login_url="/login/")
def p_orders(request):
    # Get data and filters
    filter_start, filter_end, reg_start, reg_end = get_date_range(request)
    search_client, search_provider, search_description = get_search_params(request)

    sort = request.GET.get("sort")

    # Query filtered orders
    selected_orders = Order.objects.filter(
        is_client=False,
        created_at__range=(filter_start, filter_end),
        description__icontains=search_description
    ).filter(
        Q(person__firstname__icontains=search_provider) |
        Q(person__lastname__icontains=search_provider) |
        Q(person__company_name__icontains=search_provider)
    )

    # Prepare orders list with invoicing details
    provider_orders = []
    for o in selected_orders:
        order_elements = list(OrderElement.objects.filter(order=o).order_by("id"))
        invoiced = int(o.invoiced / o.value * 100) if o.value else 0
        
        provider_orders.append({"order": o, "elements": order_elements, "invoiced": invoiced})
    
    # Sorting logic
    sort_keys = {
        "order": lambda x: x["order"].id,
        "provider": lambda x: x["order"].person.firstname,
        "assignee": lambda x: x["order"].modified_by.first_name,
        "registered": lambda x: x["order"].created_at,
        "deadline": lambda x: x["order"].deadline,
        "status": lambda x: x["order"].status.percent,
        "value": lambda x: x["order"].value,
        "invoiced": lambda x: x["invoiced"],
        "update": lambda x: x["order"].modified_at,
    }

    provider_orders.sort(key=sort_keys.get(sort, lambda x: x["order"].created_at), reverse=(sort not in ["provider", "status"]))
    
    # Pagination
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

def provider_orders(request, token):
    # Get data and filters
    try:
        person = Person.objects.get(token=token)
    except Person.DoesNotExist:
        # Handle the error, maybe redirect or show an error message
        return HttpResponse("Person not found", status=404)
    
    if Order.objects.filter(person=person, is_client=False).exists():
        latest_order = Order.objects.filter(person=person).latest('created_at')
        date_end = latest_order.created_at
    else:
        date_end = 0

    filter_start, filter_end, reg_start, reg_end = get_date_range(request, 30, date_end)

    value_total = 0
    payed_total = 0
    processed_payments = set()

    # Query filtered orders
    selected_orders = Order.objects.filter(
        is_client=False,
        person=person,
        created_at__range=(filter_start, filter_end),
        status__percent__gt=0
    ).order_by("-created_at")

    # Prepare orders list with invoicing details
    provider_orders = []
    for o in selected_orders:
        order_elements = list(OrderElement.objects.filter(order=o).order_by("id"))
        # Fetch all invoices associated with the order through its elements
        order_invoices = Invoice.objects.filter(
            invoiceelement__element__in=order_elements
        ).distinct().order_by("id")    
        # Prepare a list of all unique invoices to fetch related payments
        invoice_ids = order_invoices.values_list('id', flat=True)
        # Fetch all payments associated with the collected invoices
        order_payments = Payment.objects.filter(
            paymentelement__invoice__id__in=invoice_ids
        ).distinct().order_by("id")
        provider_orders.append({
            "order": o,
            "elements": order_elements,
            "invoices": list(order_invoices),
            "payments": list(order_payments)
        })
        value_total += o.value
        for p in order_payments:
            if p.id not in processed_payments:
                processed_payments.add(p.id)
                payed_total += p.value


    return render(
        request,
        "orders/providers_orders.html",
        {
            "provider_orders": provider_orders,
            "reg_start": reg_start,
            "reg_end": reg_end,
            "person": person,
            "unpayed_total": value_total - payed_total
        },
    )

@login_required(login_url="/login/")
def p_order(request, order_id, provider_id):
    # Default parts
    statuses = Status.objects.all().order_by("percent")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("name")
    serials = Serial.objects.get(id=1)
    search = ""
    providers = []
    elements = []
    element = ""
    is_invoiced = False
    date_now = timezone.now()
    if order_id != 0:  # if order exists
        new = False
        order = get_object_or_404(Order, id=order_id)
        provider = order.person
        elements = OrderElement.objects.filter(order=order).order_by("id")
        is_invoiced = InvoiceElement.objects.filter(element__order=order).exists()
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    providers = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_provider" in request.POST and is_invoiced == False:
                new_provider = request.POST.get("new_provider")
                provider = get_object_or_404(Person, id=new_provider)
                order.person = provider
                order.modified_at = date_now

            if "order_description" in request.POST:
                order.description = request.POST.get("order_description")
                order.status = Status.objects.get(id=request.POST.get("order_status"))
                for e in elements:
                    e.status = order.status
                    e.save()
                order.currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    order.deadline = timezone.make_aware(deadline_naive)
                except:
                    order.deadline = date_now 
            if "element_id" in request.POST:
                element_id = int(request.POST.get("element_id"))
                if element_id > 0:  # edit an element
                    element = OrderElement.objects.get(id=element_id)
                else:  # add an element to order
                    element = OrderElement(order=order)
                service_id = int(request.POST.get("e_service"))
                element.service = Service.objects.get(id=service_id)
                element.description = request.POST.get("e_description")
                e_quantity = request.POST.get("e_quantity")
                if e_quantity and e_quantity.replace(".", "").isdigit():
                    element.quantity = float(e_quantity)
                else:
                    element.quantity = float(1.0)
                element.um = ums[int(request.POST.get("e_um")) - 1]
                e_price = request.POST.get("e_price")
                if e_price and e_price.replace(".", "").isdigit():
                    element.price = float(e_price)
                else:
                    element.price = float(1.0)
                element.status = Status.objects.get(id=int(request.POST.get("e_status")))
                element.save()
                # setting order status to minimum form elements
                status_elements = sorted(elements, key=lambda x: x.status.percent)
                order.status = status_elements[0].status
                element = ""  # clearing the active element
            if "delete_element_id" in request.POST:  # delete en element
                element_id = int(request.POST.get("delete_element_id"))
                element = OrderElement.objects.get(id=element_id)
                element.delete()
            if "edit_element_id" in request.POST:  # set an element editable in template
                element_id = int(request.POST.get("edit_element_id"))
                element = OrderElement.objects.get(id=element_id)
            # Setting the modiffied user and date
            order.modified_by = request.user
            order.modified_at = date_now
            # Calculating the order value
            order.value = 0
            for e in elements:
                order.value += (e.price * e.quantity)
            order.save()

    else:  # if order is new
        new = True
        if Person.objects.filter(id=provider_id).exists():
            provider = Person.objects.get(id=provider_id)
        else:
            provider = ""
        order = ""
        if request.method == "POST":
            if "search" in request.POST:
                search = request.POST.get("search")
                if len(search) > 3:
                    providers = Person.objects.filter(
                        Q(firstname__icontains=search)
                        | Q(lastname__icontains=search)
                        | Q(company_name__icontains=search)
                    )
            if "new_provider" in request.POST:
                new_provider = request.POST.get("new_provider")
                provider = get_object_or_404(Person, id=new_provider)
                return redirect(
                    "p_order",
                    order_id = 0,
                    provider_id = provider.id
                )
            if "order_description" in request.POST:
                description = request.POST.get("order_description")
                status = Status.objects.get(id=request.POST.get("order_status"))
                currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M")
                    deadline = timezone.make_aware(deadline_naive)
                except:
                    deadline = date_now 
                order = Order(
                    description = description,
                    serial = serials.p_order_serial,
                    number = serials.p_order_number,
                    person=provider,
                    deadline=deadline,
                    is_client=False,
                    modified_by=request.user,
                    created_by=request.user,
                    status=status,
                    currency=currency,
                )
                order.save()
                serials.p_order_number += 1
                serials.save()
                new = False
                return redirect(
                    "p_order",
                    order_id = order.id,
                    provider_id = provider.id
                )

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
            "element_selected": element
        },
    )

@login_required(login_url="/login/")
def print_order(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    order_elements = OrderElement.objects.exclude(status__id='6').filter(order=order).order_by("id")
    leading_number = str(order.number).rjust(4,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        img_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(img_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        order_content = f.read()

    context = {
        "order": order,
        "leading_number": leading_number,
        "order_elements": order_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("orders/print_order.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=order_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=Auftragsbestaetigung_{order.serial}-{order.number}.pdf'
    return response

@login_required(login_url="/login/")
def print_offer(request, offer_id):
    offer = get_object_or_404(Offer, id=offer_id)
    offer_elements = OfferElement.objects.filter(offer=offer).order_by("id")
    leading_number = str(offer.number).rjust(4,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        img_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(img_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        offer_content = f.read()

    context = {
        "offer": offer,
        "leading_number": leading_number,
        "offer_elements": offer_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("orders/print_offer.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=offer_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=Angebot_{offer.serial}-{offer.number}.pdf'
    return response