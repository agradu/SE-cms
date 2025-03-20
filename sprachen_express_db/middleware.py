from django.http import Http404
from django.shortcuts import render
from django.utils.deprecation import MiddlewareMixin

class CustomErrorMiddleware(MiddlewareMixin):
    def process_exception(self, request, exception):
        """Orice eroare, în afară de 500, va returna template-ul 404."""
        if isinstance(exception, Http404):
            return render(request, "error-404.html", status=404)
        elif isinstance(exception, PermissionError):
            return render(request, "error-404.html", status=403)
        elif isinstance(exception, ValueError):  # Poți adăuga alte excepții aici
            return render(request, "error-404.html", status=400)
        return None  # Lăsăm Django să trateze erorile 500 normal