from django.apps import apps
from django.template.loader import select_template

def sidebar_templates(request):
    template_list = []
    for app in apps.get_app_configs():
        try:
            template_name = f"{app.label}/sidebar_{app.label}.html"
            select_template([template_name])
            template_list.append(template_name)
        except:
            continue
    return {'sidebar_app_templates': template_list}

def background_image(request):
    path = request.path.strip("/").split("/")
    if path[0]:
        background_file = f"bg-{path[0]}.jpg"
    else:
        background_file = "bg-dashboard.jpg"

    return {'background_image': background_file}