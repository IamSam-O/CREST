from django.contrib import admin
from django.contrib.auth.admin import GroupAdmin, UserAdmin
from django.contrib.auth.models import Group

from .emails import send_invite_email
from .models import Invite, User

admin.site.site_header = 'CREST Admin'
admin.site.site_title = 'CREST Admin'
admin.site.index_title = 'Admin'


@admin.register(User)
class StudyGuideUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('CREST', {'fields': ('must_change_password',)}),
    )
    list_display = ('username', 'email', 'is_staff', 'is_superuser', 'must_change_password')


@admin.register(Invite)
class InviteAdmin(admin.ModelAdmin):
    list_display = ('email', 'group', 'created_at', 'expires_at', 'accepted_at')
    readonly_fields = ('token', 'created_at', 'accepted_at')

    def save_model(self, request, obj, form, change):
        is_new = obj.pk is None
        if is_new:
            obj.invited_by = request.user
        super().save_model(request, obj, form, change)
        if is_new:
            send_invite_email(obj, request)
