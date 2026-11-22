from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import LoginView, PasswordChangeView
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.core.pagination import paginate

from .forms import FarmerRegistrationForm, LoginForm, StaffUserForm, StyledPasswordChangeForm
from .models import User
from .permissions import admin_required

ROLE_HOME = {
    User.Role.ADMIN: "accounts:admin_dashboard",
    User.Role.FARMER: "traceability:farmer_dashboard",
    User.Role.LAB: "laboratory:dashboard",
    User.Role.PROCESSOR: "processing:dashboard",
    User.Role.MANUFACTURER: "manufacturing:dashboard",
}


def home(request):
    from apps.manufacturing.models import FinalFormulation
    from apps.traceability.models import Batch

    context = {
        "stats": {
            "batches": Batch.objects.count(),
            "products": FinalFormulation.objects.count(),
        }
    }
    return render(request, "home.html", context)


class RoleLoginView(LoginView):
    template_name = "accounts/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


class PasswordChange(PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:dashboard")

    def form_valid(self, form):
        messages.success(self.request, "Your password was changed.")
        return super().form_valid(form)


@login_required
def dashboard_router(request):
    """Send each user to the dashboard of their own role."""
    target = ROLE_HOME.get(request.user.effective_role)
    if not target:
        return redirect("home")
    return redirect(target)


def register(request):
    """Public farmer / wild-collector registration (needs admin approval)."""
    if request.user.is_authenticated:
        return redirect("accounts:dashboard")
    form = FarmerRegistrationForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(
            request,
            "Registration received. An administrator must approve your account before you can sign in.",
        )
        return redirect("accounts:login")
    return render(request, "accounts/register.html", {"form": form})


# --------------------------------------------------------------- admin area
@admin_required
def admin_dashboard(request):
    from apps.herbs.models import Herb
    from apps.manufacturing.models import FinalFormulation
    from apps.traceability.models import BlockchainRecord, Batch, Collection
    from apps.verification.models import Verification

    status_counts = {row["status"]: row["n"] for row in Batch.objects.values("status").annotate(n=Count("id"))}
    total_batches = Batch.objects.count()
    breakdown = [
        {
            "code": code,
            "label": label,
            "count": status_counts.get(code, 0),
            "percent": round(100 * status_counts.get(code, 0) / total_batches) if total_batches else 0,
        }
        for code, label in Batch.Status.choices
    ]
    context = {
        "stats": {
            "users": User.objects.count(),
            "herbs": Herb.objects.count(),
            "collections": Collection.objects.count(),
            "batches": total_batches,
            "pending_lab": status_counts.get(Batch.Status.AWAITING_LAB, 0),
            "processed": status_counts.get(Batch.Status.PROCESSED, 0),
            "products": FinalFormulation.objects.count(),
            "pending_region": status_counts.get(Batch.Status.PENDING_REVIEW, 0),
            "pending_users": User.objects.filter(approval_status=User.Approval.PENDING).count(),
            "ledger_records": BlockchainRecord.objects.count(),
        },
        "breakdown": breakdown,
        "recent_batches": Batch.objects.select_related("collection__herb", "collection__collector")[:6],
        "last_verification": Verification.objects.first(),
    }
    return render(request, "accounts/admin_dashboard.html", context)


@admin_required
def user_list(request):
    qs = User.objects.all()
    q = request.GET.get("q", "").strip()
    role = request.GET.get("role", "")
    approval = request.GET.get("approval", "")
    if q:
        qs = qs.filter(
            Q(username__icontains=q) | Q(email__icontains=q)
            | Q(first_name__icontains=q) | Q(last_name__icontains=q)
        )
    if role in User.Role.values:
        qs = qs.filter(role=role)
    if approval in User.Approval.values:
        qs = qs.filter(approval_status=approval)
    page, qs_params = paginate(request, qs, 10)
    return render(request, "accounts/user_list.html", {
        "page": page, "qs_params": qs_params, "q": q, "role": role, "approval": approval,
        "roles": User.Role.choices, "approvals": User.Approval.choices,
    })


@admin_required
def user_create(request):
    form = StaffUserForm(request.POST or None, initial={"is_active": True, "approval_status": User.Approval.APPROVED})
    if request.method == "POST" and form.is_valid():
        user = form.save()
        messages.success(request, f"User '{user.username}' created as {user.get_role_display()}.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": "Create user"})


@admin_required
def user_edit(request, pk):
    user = get_object_or_404(User, pk=pk)
    form = StaffUserForm(request.POST or None, instance=user)
    if user == request.user:
        # An administrator must not lock themselves out or demote themselves.
        for name in ("role", "approval_status", "is_active"):
            form.fields[name].disabled = True
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"User '{user.username}' updated.")
        return redirect("accounts:user_list")
    return render(request, "accounts/user_form.html", {"form": form, "title": f"Edit {user.username}", "edited": user})


@admin_required
@require_POST
def user_approval(request, pk, decision):
    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, "You cannot change your own approval status.")
    elif decision == "approve":
        user.approval_status = User.Approval.APPROVED
        user.save(update_fields=["approval_status"])
        messages.success(request, f"{user.username} approved. They can now sign in.")
    elif decision == "reject":
        user.approval_status = User.Approval.REJECTED
        user.save(update_fields=["approval_status"])
        messages.warning(request, f"{user.username} was rejected.")
    target = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(target, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        target = "accounts:user_list"
    return redirect(target)
