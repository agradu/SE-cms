from django.contrib.auth.models import User
from services.models import Status, UM, Service, Currency, Serial
from users.models import CustomUser
from django.core.files.uploadedfile import InMemoryUploadedFile
from io import BytesIO
from PIL import Image
import os


def run():
    default_image = "media/profile_pictures/my-profile-default.jpg"
    username = os.environ.get("DJANGO_USER")
    statuses = [
        ["Waiting", "danger", 20],
        ["Confirmed", "primary", 40],
        ["In progress", "info", 60],
        ["In verification", "warning", 80],
        ["Delivered", "success", 100],
        ["Canceled", "dark", 100],
    ]
    for status in statuses:
        Status.objects.get_or_create(name=status[0], style=status[1], percent=status[2])
    ums = ["pieces", "pages", "lines", "days", "hours", "minutes"]
    for um in ums:
        UM.objects.get_or_create(name=um)
    um = UM.objects.filter(name="pieces").first()

    Serial.objects.get_or_create(
        offer_serial='A',
        offer_number=1,
        order_serial='B',
        order_number=1,
        proforma_serial='PRO',
        proforma_number=1,
        invoice_serial='RE',
        invoice_number=1,
        receipt_serial='BE',
        receipt_number=1,
    )

    currencies = [("€", "Euro"), ("$", "Dollar"), ("ron", "Leu")]
    for currency in currencies:
        Currency.objects.get_or_create(symbol=currency[0], name=currency[1])
    currency = Currency.objects.filter(name="Euro").first()

    services = [
        ("mdi-google-translate", "Übersetzung", 20, 30),
        ("mdi-file-word-box", "Redaktionsservice", 20, 30),
        ("mdi-seal", "Vermitlung Notar", 20, 30),
        ("mdi-star-circle", "Vermitlung Apostille", 20, 30),
    ]
    for service in services:
        Service.objects.get_or_create(
            icon=service[0],
            name=service[1],
            price_min=service[2],
            price_max=service[3],
            currency=currency,
            um=um,
        )
    with open(default_image, "rb") as f:
        image_data = BytesIO(f.read())
        image = Image.open(image_data)
        image_size = image.size
        profile_picture = InMemoryUploadedFile(
            image_data, None, default_image, "image/jpg", image_size, None
        )
        user = CustomUser.objects.filter(username=username).first()
        print(f"Setting the username '{username}'")
        user.profile_picture = profile_picture
        user.first_name = "Adrian George"
        user.last_name = "Radu"
        user.email = "adrian.george.radu@gmail.com"
        user.save()
