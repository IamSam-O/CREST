from django.apps import AppConfig
from django.db.backends.signals import connection_created
from django.db.models.signals import post_migrate


def _set_sqlite_pragmas(sender, connection, **kwargs):
    if connection.vendor != 'sqlite':
        return
    cursor = connection.cursor()
    cursor.execute('PRAGMA journal_mode=WAL;')
    cursor.execute('PRAGMA synchronous=NORMAL;')
    cursor.execute('PRAGMA foreign_keys=ON;')


def _seed_bootstrap_admin(sender, **kwargs):
    from django.contrib.auth import get_user_model

    User = get_user_model()
    if User.objects.exists():
        return
    user = User.objects.create_superuser(username='admin', email='', password='admin')
    user.email = None
    user.must_change_password = True
    user.save(update_fields=['email', 'must_change_password'])


class AccountsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'accounts'

    def ready(self):
        connection_created.connect(_set_sqlite_pragmas)
        post_migrate.connect(_seed_bootstrap_admin, sender=self)
