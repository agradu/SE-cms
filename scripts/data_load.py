from django.contrib.auth.models import User
from services.models import Status, UM, Service, Currency


def run():
    statuses = [
        ["Wartet","danger",20],
        ["Bestätigt","primary",40],
        ["Bearbeitung","info",60],
        ["Überprüfung","warning",80],
        ["Geliefert","success",100],
        ["Abgesagt","dark",100]
    ]
    for status in statuses:
        Status.objects.get_or_create(name=status[0], style=status[1], percent=status[2])
    ums = ["Stk.", "Seiten", "Zeilen", "Tage", "Stunden", "Minuten"]
    for um in ums:
        UM.objects.get_or_create(name=um)
    um = UM.objects.filter(name="Stk.").first()

    currencies = [("€", "Euro"), ("$", "Dollar"), ("ron", "Leu")]
    for currency in currencies:
        Currency.objects.get_or_create(symbol=currency[0], name=currency[1])
    currency = Currency.objects.filter(name="Euro").first()

    services = [
        ("mdi-google-translate", "Übersetzung", 20, 30),
        ("mdi-file-word-box", "Redactionsservice", 20, 30),
        ("mdi-seal", "Vermittlung beim Notar", 20, 30),
        ("mdi-star-circle", "Vermittlung Apostille", 20, 30),
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
