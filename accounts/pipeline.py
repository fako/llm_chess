"""
Steps of the python social auth pipeline for accounts with a username and password.

PSA has no notion of passwords, so the login and signup views check the forms and hand the pipeline a verified user
(password_user) or the hash of a new password (password_hash). Plain passwords never enter the pipeline, which matters
because PSA stores the pipeline data while it waits for an email to get verified.

The views hand over other choices the same way, because pipeline keyword arguments survive that wait.
"""
from social_core.exceptions import AuthAssociationError, AuthPolicyError


def require_password(backend, uid, password_user=None, password_hash=None, *args, **kwargs):
    """
    Stops anyone from posting a username to the complete view directly and getting logged in without a password.
    """
    if backend.name != "username":
        return None
    if password_user is not None:
        return {"user": password_user}
    if password_hash is None:
        raise AuthPolicyError(backend, stage="pipeline")
    if backend.strategy.storage.user.get_social_auth(backend.name, uid) is not None or \
            backend.strategy.storage.user.user_exists(username=uid):
        raise AuthAssociationError(backend, code="username_in_use", stage="pipeline")
    return None


def set_password(user=None, is_new=False, password_hash=None, *args, **kwargs):
    if user is None or not is_new or password_hash is None:
        return None
    user.password = password_hash
    user.save(update_fields=["password"])
    return None


def set_email_opt_in(user=None, is_new=False, email_opt_in=False, *args, **kwargs):
    if user is None or not is_new or not email_opt_in:
        return None
    user.email_opt_in = True
    user.save(update_fields=["email_opt_in"])
    return None


def redirect_to_next(strategy, next_url=None, *args, **kwargs):
    """
    Sends users back to the page they came from, like the puzzle they wanted to play. PSA only remembers that page
    for the request that starts the pipeline, which is not the one that resumes it from a verification link.
    PSA reads the redirect from the session right after the pipeline and checks that it stays on this site.
    """
    strategy.session_set("next", next_url or None)
    return None
