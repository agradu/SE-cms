from django.apps import AppConfig


class ServicesConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "core"         # noul path Python
    label = "services"    # IMPORTANT: păstrează label-ul vechi
