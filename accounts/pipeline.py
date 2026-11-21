"""
Steps of the python social auth pipeline for accounts with a username and password.

PSA has no notion of passwords, so the login and signup views check the forms and hand the pipeline a verified user
(password_user) or the hash of a new password (password_hash). Plain passwords never enter the pipeline, which matters
because PSA stores the pipeline data while it waits for an email to get verified.
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
