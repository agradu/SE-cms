from persons.models import Person
import random
import string

def run():
    print("Start")
    for person in Person.objects.all():
        # Generează un token unic
        token = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
        print(person, token)
        # Asigură-te că tokenul este unic
        while Person.objects.filter(token=token).exists():
            print("token gasit!")
            token = ''.join(random.choices(string.ascii_letters + string.digits, k=20))
        person.token = token
        person.save()