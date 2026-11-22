"""Role-based access control decorators."""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import User


def role_required(*roles):
    """Allow only authenticated, approved users whose role is in ``roles``.

    Anonymous users are sent to the login page; authenticated users with the
    wrong role get a 403 page (so URL tampering never reveals another dashboard).
    """

    allowed = {str(r) for r in roles}

    def decorator(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            user = request.user
            if not user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if not user.is_active or not (user.is_superuser or user.is_approved):
                raise PermissionDenied
            if user.effective_role not in allowed:
                raise PermissionDenied
            return view(request, *args, **kwargs)

        return wrapper

    return decorator


admin_required = role_required(User.Role.ADMIN)
farmer_required = role_required(User.Role.FARMER)
lab_required = role_required(User.Role.LAB)
processor_required = role_required(User.Role.PROCESSOR)
manufacturer_required = role_required(User.Role.MANUFACTURER)
staff_chain_required = role_required(
    User.Role.ADMIN, User.Role.LAB, User.Role.PROCESSOR, User.Role.MANUFACTURER
)
