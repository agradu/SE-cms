from django.shortcuts import render, get_object_or_404, redirect
from .models import Status, UM, Currency, Service
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator

# Create your views here.


@login_required(login_url="/login/")
def services(request):
    services = Service.objects.all().order_by('id')
    paginator = Paginator(services, 10)
    page = request.GET.get("page")
    services_on_page = paginator.get_page(page)
    return render(request, "services/services.html", {"services": services_on_page})


@login_required(login_url="/login/")
def service_detail(request, service_id):
    currencies = Currency.objects.all().order_by("name").values()
    units = UM.objects.all().order_by("id").values()
    if service_id != 0:
        service = get_object_or_404(Service, id=service_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            service.icon = request.POST.get("icon")
            service.name = request.POST.get("name")
            service.price_min = request.POST.get("price_min")
            service.price_max = request.POST.get("price_max")
            currency_id = request.POST.get("currency")
            service.currency = Currency.objects.get(id=currency_id)
            um_id = request.POST.get("um")
            service.um = UM.objects.get(id=um_id)
            service.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            name = request.POST.get("name")
            currency_id = request.POST.get("currency")
            um_id = request.POST.get("um")
            try:
                service = Service.objects.get(name=name)
                update = "Service name exists. Chose other."
            except:
                update = "Service created"
                service = Service(
                    name=name,
                    icon=request.POST.get("icon"),
                    price_min=request.POST.get("price_min"),
                    price_max=request.POST.get("price_max"),
                    currency=Currency.objects.get(id=currency_id),
                    um=UM.objects.get(id=um_id),
                )
                service.save()
        else:
            update = ""
            service = ""
    return render(
        request,
        "services/service.html",
        {
            "service": service,
            "update": update,
            "currencies": currencies,
            "units": units,
        },
    )


@login_required(login_url="/login/")
def statuses(request):
    statuses = Status.objects.all().order_by("percent")
    return render(request, "services/statuses.html", {"statuses": statuses})


@login_required(login_url="/login/")
def status_detail(request, status_id):
    if status_id != 0:
        status = get_object_or_404(Status, id=status_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            status.name = request.POST.get("name")
            status.style = request.POST.get("style")
            status.percent = request.POST.get("percent")
            status.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            name = request.POST.get("name")
            style = request.POST.get("style")
            percent = request.POST.get("percent")
            try:
                status = Status.objects.get(name=name)
                update = "Status name exists. Chose other."
            except:
                update = "Status created"
                status = Status(
                    name=name,
                    style = request.POST.get("style"),
                    percent = request.POST.get("percent"),
                )
                status.save()
        else:
            update = ""
            status = ""
    return render(request, "services/status.html", {"status": status, "update": update})


@login_required(login_url="/login/")
def currencies(request):
    currencies = Currency.objects.all()
    return render(request, "services/currencies.html", {"currencies": currencies})


@login_required(login_url="/login/")
def currency_detail(request, currency_id):
    if currency_id != 0:
        currency = get_object_or_404(Currency, id=currency_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            currency.symbol = request.POST.get("symbol")
            currency.name = request.POST.get("name")
            currency.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            name = request.POST.get("name")
            style = request.POST.get("style")
            try:
                currency = Currency.objects.get(name=name)
                update = "Currency name exists. Chose other."
            except:
                update = "Currency created"
                currency = Currency(
                    name=name,
                    style = request.POST.get("style"),
                )
                currency.save()
        else:
            update = ""
            currency = ""
    return render(
        request, "services/currency.html", {"currency": currency, "update": update}
    )


@login_required(login_url="/login/")
def units(request):
    units = UM.objects.all()
    return render(request, "services/units.html", {"units": units})


@login_required(login_url="/login/")
def unit_detail(request, unit_id):
    if unit_id != 0:
        unit = get_object_or_404(UM, id=unit_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            unit.name = request.POST.get("name")
            unit.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            name = request.POST.get("name")
            try:
                unit = UM.objects.get(name=name)
                update = "Unit name exists. Chose other."
            except:
                update = "Unit created"
                unit = UM(
                    name=name,
                )
                unit.save()
        else:
            update = ""
            unit = ""
    return render(request, "services/unit.html", {"unit": unit, "update": update})
