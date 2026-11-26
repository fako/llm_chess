from uuid import uuid4

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    email_opt_out = models.BooleanField(
        default=False,
        db_default=False,  # lets code from before this field create users while a deploy is underway
        help_text="The user wants no emails besides the ones their account needs, like email verification and "
                  "password resets. Check this before sending anything else.",
    )
