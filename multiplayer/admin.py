from django.contrib import admin

from .models import MultiplayerParticipant, MultiplayerSession


class ParticipantInline(admin.TabularInline):
    model = MultiplayerParticipant
    extra = 0


@admin.register(MultiplayerSession)
class MultiplayerSessionAdmin(admin.ModelAdmin):
    list_display = ('room_code', 'exam', 'host', 'status', 'created_at')
    inlines = [ParticipantInline]
