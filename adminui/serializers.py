from django.contrib.auth.models import Group, Permission
from rest_framework import serializers

from accounts.models import EmailSettings, Invite, User
from exams.models import AppSettings, Attempt
from multiplayer.models import MultiplayerParticipant, MultiplayerSession


class GroupSerializer(serializers.ModelSerializer):
    permissions = serializers.PrimaryKeyRelatedField(many=True, queryset=Permission.objects.all(), required=False)

    class Meta:
        model = Group
        fields = ['id', 'name', 'permissions']

    def create(self, validated_data):
        permissions = validated_data.pop('permissions', [])
        group = Group.objects.create(**validated_data)
        group.permissions.set(permissions)
        return group

    def update(self, instance, validated_data):
        permissions = validated_data.pop('permissions', None)
        instance.name = validated_data.get('name', instance.name)
        instance.save()
        if permissions is not None:
            instance.permissions.set(permissions)
        return instance


class UserSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)
    groups = serializers.PrimaryKeyRelatedField(many=True, queryset=Group.objects.all(), required=False)

    class Meta:
        model = User
        fields = [
            'id', 'username', 'email', 'first_name', 'last_name', 'password',
            'is_active', 'is_staff', 'is_superuser', 'must_change_password',
            'groups', 'date_joined', 'last_login',
        ]
        read_only_fields = ['date_joined', 'last_login']

    def validate(self, attrs):
        if self.instance is None and not attrs.get('password'):
            raise serializers.ValidationError({'password': 'Password is required when creating a user.'})
        return attrs

    def create(self, validated_data):
        password = validated_data.pop('password')
        groups = validated_data.pop('groups', [])
        user = User(**validated_data)
        user.set_password(password)
        user.save()
        user.groups.set(groups)
        return user

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        groups = validated_data.pop('groups', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.set_password(password)
        instance.save()
        if groups is not None:
            instance.groups.set(groups)
        return instance


class InviteSerializer(serializers.ModelSerializer):
    class Meta:
        model = Invite
        fields = ['id', 'email', 'group', 'token', 'invited_by', 'created_at', 'expires_at', 'accepted_at']
        read_only_fields = ['token', 'invited_by', 'created_at', 'accepted_at']


class AttemptSerializer(serializers.ModelSerializer):
    class Meta:
        model = Attempt
        fields = [
            'id', 'exam', 'user', 'started_at', 'finished_at',
            'num_questions', 'num_correct', 'total_points', 'points_earned',
        ]
        read_only_fields = ['finished_at']


class AppSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = AppSettings
        fields = ['sound_effects_enabled', 'theme', 'max_in_progress_instances']


class EmailSettingsSerializer(serializers.ModelSerializer):
    # Write-only and optional, like UserSerializer's password field - blank
    # means "leave the stored password unchanged" rather than wiping it, and
    # it's never echoed back to the client.
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = EmailSettings
        fields = ['host', 'port', 'use_tls', 'use_ssl', 'username', 'password', 'default_from_email']

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        if password:
            instance.password = password
        instance.save()
        return instance


class MultiplayerParticipantSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultiplayerParticipant
        fields = ['id', 'session', 'client_id', 'display_name', 'score', 'connected', 'joined_at']
        read_only_fields = ['joined_at']


class MultiplayerSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = MultiplayerSession
        fields = [
            'id', 'room_code', 'passcode', 'host_secret', 'exam', 'host', 'status',
            'questions_json', 'current_index', 'time_limit_seconds', 'created_at',
        ]
        read_only_fields = ['created_at']
