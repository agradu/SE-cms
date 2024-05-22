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
    language = input("Language (1-English, 2-German)")
    if language == "2":
        statuses = [
            ["Warten", "danger", 20],
            ["Bestätigt", "primary", 40],
            ["In Bearbeitung", "info", 60],
            ["In Überprüfung", "warning", 80],
            ["Geliefert", "success", 100],
            ["Abgebrochen", "dark", 100],
        ]
        ums = ["Stk.", "S.", "Zl.", "Tg.", "Std.", "Min."]
        um = UM.objects.filter(name="Stk.").first()
        print("German:",um)
    else:
        statuses = [
            ["Waiting", "danger", 20],
            ["Confirmed", "primary", 40],
            ["In progress", "info", 60],
            ["In verification", "warning", 80],
            ["Delivered", "success", 100],
            ["Canceled", "dark", 100],
        ]
        ums = ["pcs", "pgs", "lns", "d", "h", "min"]
        um = UM.objects.filter(name="pcs").first()
        print("English:",um)
            
    for s in statuses:
        Status.objects.get_or_create(name=s[0], style=s[1], percent=s[2])
    for u in ums:
        UM.objects.get_or_create(name=u)

    Serial.objects.get_or_create(
        offer_serial='A',
        offer_number=1,
        order_serial='B',
        order_number=1,
        p_order_serial='P',
        p_order_number=1,
        proforma_serial='PRO',
        proforma_number=1,
        invoice_serial='RE',
        invoice_number=1,
        receipt_serial='BE',
        receipt_number=1,
    )

    currencies = [("€", "Euro"), ("$", "Dollar"), ("ron", "Leu")]
    for c in currencies:
        Currency.objects.get_or_create(symbol=c[0], name=c[1])
    currency = Currency.objects.filter(name="Euro").first()

    if language == "2":
        services = [
            ("mdi-google-translate", "Übersetzung", 20, 30),
            ("mdi-file-word-box", "Redaktionsservice", 20, 30),
            ("mdi-seal", "Vermitlung Notar", 20, 30),
            ("mdi-star-circle", "Vermitlung Apostille", 20, 30),
        ]
    else:
        services = [
            ("mdi-google-translate", "Translation", 20, 30),
            ("mdi-file-word-box", "Editorial Service", 20, 30),
            ("mdi-seal", "Notary Mediation", 20, 30),
            ("mdi-star-circle", "Apostille Mediation", 20, 30),
        ]
    for s in services:
        Service.objects.get_or_create(
            icon=s[0],
            name=s[1],
            price_min=s[2],
            price_max=s[3],
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
