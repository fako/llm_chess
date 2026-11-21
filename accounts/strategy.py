from social_django.strategy import DjangoStrategy


class AccountsStrategy(DjangoStrategy):

    def validate_email(self, email: str, code) -> bool:
        # When PSA replays the data of a validation link after its confirmation page, Django's QueryDict values
        # come back as lists.
        if isinstance(code, (list, tuple)):
            code = code[-1] if code else ""
        return super().validate_email(email, code)
