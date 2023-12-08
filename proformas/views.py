from django.shortcuts import render, redirect, get_object_or_404
from django.template.loader import render_to_string
from django.http import HttpResponse
from django.contrib.auth.decorators import login_required
from django.db.models import Q
from orders.models import Order, OrderElement
from persons.models import Person
from .models import Proforma, ProformaElement
from services.models import Serial
from django.core.paginator import Paginator
from datetime import datetime, timedelta
from django.utils import timezone
from weasyprint import HTML, CSS
import base64

# Create your views here.


@login_required(login_url="/login/")
def proformas(request):
    # search elements
    search = request.GET.get("search")
    if search == None:
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
    # CLIENT/PROVIDER PROFORMAS
    selected_proformas = Proforma.objects.filter(
        Q(person__firstname__icontains=search)
        | Q(person__lastname__icontains=search)
        | Q(person__company_name__icontains=search)
    ).filter(created_at__gte=filter_start, created_at__lte=filter_end)
    person_proformas = []
    for p in selected_proformas:
        proforma_elements = ProformaElement.objects.filter(proforma=p).order_by("id")
        p_orders = []
        for e in proforma_elements:
            if e.element.order not in p_orders:
                p_orders.append(e.element.order)
        person_proformas.append(
            {"proforma": p, "value": p.value, "orders": p_orders}
        )
    # sorting types
    page = request.GET.get("page")
    sort = request.GET.get("sort")
    def get_sort_key(x):
        if sort == "proforma":
            return (x["proforma"].serial, x["proforma"].number)
        elif sort == "person":
            return x["proforma"].person.firstname
        elif sort == "assignee":
            return x["proforma"].modified_by.first_name
        elif sort == "registered":
            return x["proforma"].created_at
        elif sort == "deadline":
            return x["proforma"].deadline
        elif sort == "status":
            return x["proforma"].status.id
        elif sort == "value":
            return x["value"]
        elif sort == "update":
            return x["proforma"].modified_at
        else:
            return x["proforma"].created_at
    person_proformas = sorted(person_proformas, key=get_sort_key, reverse=(sort != "person" and sort != "payed"))

    paginator = Paginator(person_proformas, 10)
    proformas_on_page = paginator.get_page(page)

    return render(
        request,
        "payments/proformas.html",
        {
            "person_proformas": proformas_on_page,
            "sort": sort,
            "search": search,
            "reg_start": reg_start,
            "reg_end": reg_end,
        },
    )

@login_required(login_url="/login/")
def proforma(request, proforma_id, person_id, order_id):
    # Default parts
    proforma_elements = []
    unproformed_elements = []
    date_now = timezone.now()
    person = get_object_or_404(Person, id=person_id)
    serials = Serial.objects.get(id=1)
    proforma_serial = serials.proforma_serial
    proforma_number = serials.proforma_number
    if order_id > 0:
        order = get_object_or_404(Order, id=order_id)
    else:
        order = ""
    if proforma_id > 0:
        proforma = get_object_or_404(Proforma, id=proforma_id)
        new = False
    else:
        proforma =""
        new = True
    all_orders_elements = OrderElement.objects.exclude(status__id='6').filter(order__person=person).order_by("id")
    proformed_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma__person=person).order_by("id")
    unproformed_elements = all_orders_elements.exclude(id__in=proformed_elements.values_list('element__id', flat=True))
    def set_value(proforma): # calculate and save the value of the proforma
        proforma_elements = ProformaElement.objects.filter(proforma=proforma).order_by("id")
        proforma.value = 0
        for e in proforma_elements:
            proforma.value += (e.element.price * e.element.quantity)
        proforma.save()
    if proforma_id > 0:  # if proforma exists
        proforma_serial = proforma.serial
        proforma_number = proforma.number
        proforma_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma=proforma).order_by('element__order__created_at')
        if request.method == "POST":
            if "proforma_description" in request.POST:
                proforma.description = request.POST.get("proforma_description")
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    proforma.deadline = timezone.make_aware(deadline_naive)
                except:
                    proforma.deadline = date_now  
            if "proforma_element_id" in request.POST:
                proforma_element_id = int(request.POST.get("proforma_element_id"))
                try: # delete an element
                    element = ProformaElement.objects.get(id=proforma_element_id)
                    if ProformaElement.objects.filter(proforma=proforma).count() > 1:
                        element.delete()
                except:
                    print("Element",proforma_element_id,"is missing!")
            if "unproformed_element_id" in request.POST:
                unproformed_element_id = int(request.POST.get("unproformed_element_id"))
                try: # add an element
                    element = unproformed_elements.get(id=unproformed_element_id)
                    ProformaElement.objects.get_or_create(
                        proforma=proforma,
                        element=element
                    )
                except:
                    print("Element",unproformed_element_id,"is missing!")
            # Setting the modiffied user and date
            proforma.modified_by = request.user
            proforma.modified_at = date_now
            # Save the proforma value
            set_value(proforma)

    else:  # if proforma is new
        if request.method == "POST":
            if "proforma_description" in request.POST:
                proforma_description = request.POST.get("proforma_description")     
                deadline_date = request.POST.get("deadline_date")
                try:
                    deadline_naive = datetime.strptime(f"{deadline_date}", "%Y-%m-%d")
                    proforma_deadline = timezone.make_aware(deadline_naive)
                except:
                    proforma_deadline = date_now
                proforma = Proforma(
                    description = proforma_description,
                    serial = proforma_serial,
                    number = proforma_number,
                    person = person,
                    deadline = proforma_deadline,
                    is_client = order.is_client,
                    modified_by = request.user,
                    created_by = request.user,
                    currency = order.currency,
                )
                proforma.save()
                # Add all unproformed elements to this proforma
                for element in unproformed_elements:
                    ProformaElement.objects.get_or_create(
                        proforma=proforma,
                        element=element
                    )
                # Save the proforma value
                set_value(proforma)
                new = False
                serials.proforma_number += 1
                serials.save()
                return redirect(
                    "proforma",
                    proforma_id = proforma.id,
                    order_id = order.id,
                    person_id = person.id,
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
            "new": new
        },
    )

@login_required(login_url="/login/")
def print_proforma(request, proforma_id):
    proforma = get_object_or_404(Proforma, id=proforma_id)
    proforma_elements = ProformaElement.objects.exclude(element__status__id='6').filter(proforma=proforma).order_by("id")
    date1 = proforma.created_at.date()
    date2 = proforma.deadline
    day_left = (date2 - date1).days
    leading_number = proforma.number.rjust(3,'0')

    # Open the logo image
    with open('static/images/logo-se.jpeg', 'rb') as f:
        svg_content = f.read()
    # Encode the image în base64
    logo_base64 = base64.b64encode(svg_content).decode('utf-8')
    # Open the CSS content
    with open('static/css/invoice.css', 'rb') as f:
        proforma_content = f.read()

    context = {
        "proforma": proforma,
        "day_left": day_left,
        "leading_number": leading_number,
        "proforma_elements": proforma_elements,
        "logo_base64": logo_base64
    }
    html_content = render_to_string("payments/print_proforma.html", context)

    pdf_file = HTML(string=html_content).write_pdf(stylesheets=[CSS(string=proforma_content)])
    response = HttpResponse(pdf_file, content_type='application/pdf')
    response['Content-Disposition'] = f'filename=proforma-{proforma.serial}-{proforma.number}.pdf'
    return response