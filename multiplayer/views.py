from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render

from exams.models import AppSettings, Exam

from .models import MultiplayerSession


NAV_LINKS = [{'url': '/', 'icon': 'bi-house-door', 'label': 'Library'}]


@login_required
def host_new(request):
    if request.method == 'POST':
        exam = get_object_or_404(Exam, id=request.POST.get('exam_id'))
        host = request.user if request.user.is_authenticated else None
        session = MultiplayerSession.objects.create(exam=exam, host=host)
        return redirect('mp_host_room', room_code=session.room_code, host_secret=session.host_secret)
    exams = Exam.objects.order_by('-created_at')
    return render(request, 'multiplayer/host_new.html', {'exams': exams, 'theme': AppSettings.get_solo().theme, 'nav_links': NAV_LINKS})


@login_required
def host_room(request, room_code, host_secret):
    session = get_object_or_404(MultiplayerSession, room_code=room_code, host_secret=host_secret)
    join_url = request.build_absolute_uri(f'/multiplayer/play/{session.room_code}/')
    return render(request, 'multiplayer/host_room.html', {
        'session': session, 'join_url': join_url, 'theme': AppSettings.get_solo().theme, 'nav_links': NAV_LINKS,
    })


def play_room(request, room_code):
    session = get_object_or_404(MultiplayerSession, room_code=room_code)
    return render(request, 'multiplayer/play_room.html', {'session': session, 'theme': AppSettings.get_solo().theme})
