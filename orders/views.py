from django.shortcuts import render, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.db.models import Sum, Q
from .models import Order, OrderElement
from persons.models import Person
from payments.models import Payment
from invoices.models import Invoice, InvoiceElement
from services.models import Currency, Status, Service, UM
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone

# Create your views here.


@login_required(login_url="/login/")
def c_orders(request):
    # search elements
    search = ""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = date_now - timedelta(days=10)
    reg_start = date_before.strftime("%Y-%m-%d")
    filter_start = date_before
    reg_end = date_now.strftime("%Y-%m-%d")
    filter_end = date_now
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) > 2:
            reg_start = request.POST.get("reg_start")
            filter_start = datetime.strptime(reg_start, "%Y-%m-%d")
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get("reg_end")
            filter_end = datetime.strptime(reg_end, "%Y-%m-%d")
            filter_end = timezone.make_aware(filter_end).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
        else:
            search = ""
    # CLIENT ORDERS
    selected_orders = (
        Order.objects.filter(is_client=True)
        .filter(
            Q(person__firstname__icontains=search)
            | Q(person__lastname__icontains=search)
            | Q(person__company_name__icontains=search)
        )
        .filter(created_at__gte=filter_start, created_at__lte=filter_end)
    )
    client_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
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
        client_orders.append(
            {"order": o, "elements": order_elements, "invoiced": invoiced}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "order":
        client_orders = sorted(client_orders, key=lambda x: x["order"].id, reverse=True)
    elif sort == "client":
        client_orders = sorted(client_orders, key=lambda x: x["order"].person.firstname)
    elif sort == "assignee":
        client_orders = sorted(
            client_orders, key=lambda x: x["order"].modified_by.first_name
        )
    elif sort == "registered":
        client_orders = sorted(
            client_orders, key=lambda x: x["order"].created_at, reverse=True
        )
    elif sort == "deadline":
        client_orders = sorted(
            client_orders, key=lambda x: x["order"].deadline, reverse=True
        )
    elif sort == "status":
        client_orders = sorted(client_orders, key=lambda x: x["order"].status.id)
    elif sort == "value":
        client_orders = sorted(client_orders, key=lambda x: x["value"], reverse=True)
    elif sort == "payed":
        client_orders = sorted(client_orders, key=lambda x: x["payed"])
    elif sort == "update":
        client_orders = sorted(
            client_orders, key=lambda x: x["order"].modified_at, reverse=True
        )
    else:
        client_orders = sorted(
            client_orders, key=lambda x: x["order"].created_at, reverse=True
        )

    paginator = Paginator(client_orders, 10)
    orders_on_page = paginator.get_page(page)

    return render(
        request,
        "clients/c_orders.html",
        {
            "client_orders": orders_on_page,
            "sort": sort,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def c_order(request, order_id, client_id):
    # Default parts
    statuses = Status.objects.all().order_by("id")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("id")
    search = ""
    clients = []
    elements = []
    element = ""
    value = 0
    date_now = timezone.now()
    if order_id != 0:  # if order exists
        new = False
        order = get_object_or_404(Order, id=order_id)
        client = order.person
        elements = OrderElement.objects.filter(order=order).order_by("id")
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
                order.person = client
                order.modified_at = date_now
            if "order_description" in request.POST:
                order.description = request.POST.get("order_description")
                order.status = statuses[int(request.POST.get("order_status")) - 1]
                for e in elements:
                    e.status = order.status
                    e.save()
                order.currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                deadline_naive = datetime.strptime(
                    f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M"
                )
                order.deadline = timezone.make_aware(deadline_naive)
            if "element_id" in request.POST:
                element_id = int(request.POST.get("element_id"))
                if element_id > 0:  # edit an element
                    element = OrderElement.objects.get(id=element_id)
                    element.service = services[int(request.POST.get("e_service")) - 1]
                    element.description = request.POST.get("e_description")
                    element.units = request.POST.get("e_quantity")
                    element.um = ums[int(request.POST.get("e_um")) - 1]
                    element.price = request.POST.get("e_price")
                    element.status = statuses[int(request.POST.get("e_status")) - 1]
                    element.save()
                else:  # add an element to order
                    element = OrderElement(order=order)
                    element.service = services[int(request.POST.get("e_service")) - 1]
                    element.description = request.POST.get("e_description")
                    element.units = request.POST.get("e_quantity")
                    element.um = ums[int(request.POST.get("e_um")) - 1]
                    element.price = request.POST.get("e_price")
                    element.status = statuses[int(request.POST.get("e_status")) - 1]
                    element.save()
                # setting order status to minimum form elements
                status_elements = sorted(elements, key=lambda x: x.status.id)
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

    else:  # if order is new
        new = True
        client = get_object_or_404(Person, id=client_id)
        order = Order(
            person=client,
            deadline=date_now,
            is_client=True,
            modified_by=request.user,
            created_by=request.user,
            status=statuses[0],
            currency=currencies[0],
        )

    order.save()
    # Calculating the order value
    for e in elements:
        value += e.price * e.units

    return render(
        request,
        "clients/c_order.html",
        {
            "clients": clients,
            "order": order,
            "elements": elements,
            "value": value,
            "currencies": currencies,
            "statuses": statuses,
            "ums": ums,
            "services": services,
            "new": new,
            "element_selected": element,
        },
    )


@login_required(login_url="/login/")
def c_offers(request):
    return render(request, "clients/c_offers.html")


@login_required(login_url="/login/")
def p_orders(request):
    # search elements
    search = ""
    date_now = timezone.now().replace(hour=23, minute=59, second=59, microsecond=0)
    date_before = date_now - timedelta(days=10)
    reg_start = date_before.strftime("%Y-%m-%d")
    filter_start = date_before
    reg_end = date_now.strftime("%Y-%m-%d")
    filter_end = date_now
    if request.method == "POST":
        search = request.POST.get("search")
        if len(search) > 2:
            reg_start = request.POST.get("reg_start")
            filter_start = datetime.strptime(reg_start, "%Y-%m-%d")
            filter_start = timezone.make_aware(filter_start)
            reg_end = request.POST.get("reg_end")
            filter_end = datetime.strptime(reg_end, "%Y-%m-%d")
            filter_end = timezone.make_aware(filter_end).replace(
                hour=23, minute=59, second=59, microsecond=0
            )
        else:
            search = ""
    # PROVIDERS ORDERS
    selected_orders = (
        Order.objects.filter(is_client=False)
        .filter(
            Q(person__firstname__icontains=search)
            | Q(person__lastname__icontains=search)
            | Q(person__company_name__icontains=search)
        )
        .filter(created_at__gte=filter_start, created_at__lte=filter_end)
    )
    provider_orders = []
    for o in selected_orders:
        order_elements = OrderElement.objects.filter(order=o).order_by("id")
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
        provider_orders.append(
            {"order": o, "elements": order_elements, "invoiced": invoiced}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    if sort == "order":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].id, reverse=True
        )
    elif sort == "provider":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].person.firstname
        )
    elif sort == "assignee":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].modified_by.first_name
        )
    elif sort == "registered":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].created_at, reverse=True
        )
    elif sort == "deadline":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].deadline, reverse=True
        )
    elif sort == "status":
        provider_orders = sorted(provider_orders, key=lambda x: x["order"].status.id)
    elif sort == "value":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["value"], reverse=True
        )
    elif sort == "payed":
        provider_orders = sorted(provider_orders, key=lambda x: x["payed"])
    elif sort == "update":
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].modified_at, reverse=True
        )
    else:
        provider_orders = sorted(
            provider_orders, key=lambda x: x["order"].created_at, reverse=True
        )

    paginator = Paginator(provider_orders, 10)
    orders_on_page = paginator.get_page(page)

    return render(
        request,
        "providers/p_orders.html",
        {
            "provider_orders": orders_on_page,
            "sort": sort,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )


@login_required(login_url="/login/")
def p_order(request, order_id, provider_id):
    # Default parts
    statuses = Status.objects.all().order_by("id")
    currencies = Currency.objects.all().order_by("id")
    ums = UM.objects.all().order_by("id")
    services = Service.objects.all().order_by("id")
    search = ""
    providers = []
    elements = []
    element = ""
    value = 0
    date_now = timezone.now()
    if order_id != 0:  # if order exists
        new = False
        order = get_object_or_404(Order, id=order_id)
        provider = order.person
        elements = OrderElement.objects.filter(order=order).order_by("id")
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
                order.person = provider
                order.modified_at = date_now
            if "order_description" in request.POST:
                order.description = request.POST.get("order_description")
                order.status = statuses[int(request.POST.get("order_status")) - 1]
                for e in elements:
                    e.status = order.status
                    e.save()
                order.currency = currencies[int(request.POST.get("order_currency")) - 1]
                deadline_date = request.POST.get("deadline_date")
                deadline_time = request.POST.get("deadline_time")
                deadline_naive = datetime.strptime(
                    f"{deadline_date} {deadline_time}", "%Y-%m-%d %H:%M"
                )
                order.deadline = timezone.make_aware(deadline_naive)
            if "element_id" in request.POST:
                element_id = int(request.POST.get("element_id"))
                if element_id > 0:  # edit an element
                    element = OrderElement.objects.get(id=element_id)
                    element.service = services[int(request.POST.get("e_service")) - 1]
                    element.description = request.POST.get("e_description")
                    element.units = request.POST.get("e_quantity")
                    element.um = ums[int(request.POST.get("e_um")) - 1]
                    element.price = request.POST.get("e_price")
                    element.status = statuses[int(request.POST.get("e_status")) - 1]
                    element.save()
                else:  # add an element to order
                    element = OrderElement(order=order)
                    element.service = services[int(request.POST.get("e_service")) - 1]
                    element.description = request.POST.get("e_description")
                    element.units = request.POST.get("e_quantity")
                    element.um = ums[int(request.POST.get("e_um")) - 1]
                    element.price = request.POST.get("e_price")
                    element.status = statuses[int(request.POST.get("e_status")) - 1]
                    element.save()
                # setting order status to minimum form elements
                status_elements = sorted(elements, key=lambda x: x.status.id)
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

    else:  # if order is new
        new = True
        provider = get_object_or_404(Person, id=provider_id)
        order = Order(
            person=provider,
            deadline=date_now,
            is_client=False,
            modified_by=request.user,
            created_by=request.user,
            status=statuses[0],
            currency=currencies[0],
        )

    order.save()
    # Calculating the order value
    for e in elements:
        value += e.price * e.units

    return render(
        request,
        "providers/p_order.html",
        {
            "providers": providers,
            "order": order,
            "elements": elements,
            "value": value,
            "currencies": currencies,
            "statuses": statuses,
            "ums": ums,
            "services": services,
            "new": new,
            "element_selected": element,
        },
    )
