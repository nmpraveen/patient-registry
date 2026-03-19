#!/bin/sh
set -eu

python manage.py migrate

python manage.py shell -c "
from django.contrib.auth import get_user_model
from patients.models import DeviceApprovalPolicy

User = get_user_model()
user, _ = User.objects.get_or_create(
    username='admin',
    defaults={
        'is_active': True,
        'is_staff': True,
        'is_superuser': True,
    },
)
user.is_active = True
user.is_staff = True
user.is_superuser = True
user.set_password('pass')
user.save()
DeviceApprovalPolicy.get_solo().target_users.remove(user)
print('Ensured local demo superuser admin')
"

python manage.py seed_mock_data --profile full --count 30 --include-vitals --include-rch-scenarios --reset-all --yes-reset-all

exec python manage.py runserver 0.0.0.0:8000
