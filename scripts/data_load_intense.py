from persons.models import Person
import os
import random
import requests
api_url = 'https://api.api-ninjas.com/v1/randomuser'


def run():
    services = ["","","","","notar","traducator","grafician","curier"]
    for i in range(0,1000):
        response = requests.get(api_url, headers={'X-Api-Key': '8TqedOdrbAh8WZKAZJrILg==bwehGu1FNqpfDDAm'})
        data = response.json()
        names = data["name"].split(" ")
        firstname = names[0]
        lastname = names[1]
        service = services[random.randrange(0, 7)]
        email = data["email"]
        address = data["address"]
        Person.objects.get_or_create(
            firstname=firstname, 
            lastname=lastname, 
            services=service, 
            email=email,
            address=address
            )
    
