from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from exams.models import AppSettings


@login_required
def admin_ui_index(request):
    return render(request, 'adminui/index.html', {
        'theme': AppSettings.get_solo().theme,
        'nav_links': [
            {'url': '/', 'icon': 'bi-house-door', 'label': 'Home'},
        ],
    })
