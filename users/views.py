from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from .models import CustomUser
from datetime import datetime
from django.core.paginator import Paginator
from django.core.files.uploadedfile import InMemoryUploadedFile
from io import BytesIO
from PIL import Image

import os

# Create your views here.
default_image = "profile_pictures/my-profile-default.jpg"


@login_required(login_url="/login/")
def users(request):
    users = CustomUser.objects.all().order_by("first_name")
    paginator = Paginator(users, 10)
    page = request.GET.get("page")
    users_on_page = paginator.get_page(page)
    return render(request, "settings/users.html", {"users": users_on_page})


@login_required(login_url="/login/")
def user_detail(request, user_id):
    if user_id != 0:
        user = get_object_or_404(CustomUser, id=user_id)
        if request.method == "POST":
            update = "Succesfuly updated"
            user.username = request.POST.get("username")
            user.first_name = request.POST.get("first_name")
            user.last_name = request.POST.get("last_name")
            user.email = request.POST.get("email")
            new_password = request.POST.get("password")
            if new_password != "":
                user.set_password(new_password)
            user_type = request.POST.get("user_type")
            if user_type == "administrator":
                user.is_superuser = True
                user.is_active = True
            elif user_type == "manager":
                user.is_staff = True
                user.is_superuser = False
                user.is_active = True
            elif user_type == "operator":
                user.is_staff = False
                user.is_superuser = False
                user.is_active = True
            else:
                user.is_active = False
            date_of_birth = request.POST.get("date_of_birth")
            user.date_of_birth = datetime.strptime(date_of_birth, "%Y-%m-%d")
            profile_picture = request.FILES.get("profile_picture")
            if profile_picture:
                if user.profile_picture:
                    user.profile_picture.close()
                    os.remove(user.profile_picture.path)
                user.profile_picture = profile_picture
            user.phone = request.POST.get("phone")
            user.address = request.POST.get("address")
            user.save()
        else:
            update = ""
    else:
        if request.method == "POST":
            username = request.POST.get("username")
            try:
                user = CustomUser.objects.get(username=username)
                update = "Username exists. Chose other."
            except:
                update = "User created"
                user_type = request.POST.get("user_type")
                is_staff = True
                is_superuser = True
                is_active = True
                if user_type == "manager":
                    is_superuser = False
                elif user_type == "operator":
                    is_staff = False
                    is_superuser = False
                else:
                    is_staff = False
                    is_superuser = False
                    is_active = False
                date_of_birth = request.POST.get("date_of_birth")
                profile_picture = request.FILES.get("profile_picture")
                if profile_picture:
                    profile_picture = profile_picture
                else:
                    with open(default_image, "rb") as f:
                        image_data = BytesIO(f.read())
                        image = Image.open(image_data)
                        image_size = image.size
                        profile_picture = InMemoryUploadedFile(
                            image_data,
                            None,
                            default_image,
                            "image/jpg",
                            image_size,
                            None,
                        )
                user = CustomUser(
                    username=username,
                    first_name=request.POST.get("first_name"),
                    last_name=request.POST.get("last_name"),
                    email=request.POST.get("email"),
                    is_staff=is_staff,
                    is_superuser=is_superuser,
                    is_active=is_active,
                    date_of_birth=datetime.strptime(date_of_birth, "%Y-%m-%d"),
                    phone=request.POST.get("phone"),
                    address=request.POST.get("address"),
                    profile_picture=profile_picture,
                )
                new_password = request.POST.get("password")
                if new_password != "":
                    user.set_password(new_password)
                else:
                    user.set_password("@Porumbel123")
                user.save()
        else:
            update = ""
            user = ""
    return render(request, "settings/user.html", {"us": user, "update": update})
