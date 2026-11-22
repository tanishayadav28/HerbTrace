from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.permissions import manufacturer_required
from apps.core.pagination import paginate
from apps.traceability.models import Batch

from .forms import BatchSelectionForm, FormulationForm, ManufacturingForm
from .models import FinalFormulation, Manufacturing
from .services import create_formulation, eligible_batches


@manufacturer_required
def dashboard(request):
    return render(request, "manufacturing/dashboard.html", {
        "stats": {
            "eligible": eligible_batches().count(),
            "in_processing": Batch.objects.filter(status__in=[Batch.Status.PROCESSING, Batch.Status.LAB_PASSED]).count(),
            "products": FinalFormulation.objects.filter(created_by=request.user).count(),
            "all_products": FinalFormulation.objects.count(),
        },
        "recent": FinalFormulation.objects.filter(created_by=request.user).select_related("qr_code")[:6],
        "eligible_batches": eligible_batches().select_related("collection__herb")[:6],
    })


@manufacturer_required
def create(request):
    initial_batches = request.GET.getlist("batch")
    sel_form = BatchSelectionForm(request.POST or None, initial={"batches": Batch.objects.filter(batch_id__in=initial_batches)})
    mfg_form = ManufacturingForm(request.POST or None, initial={"manufacturer_name": request.user.organization})
    frm_form = FormulationForm(request.POST or None)
    if request.method == "POST":
        valid = all([sel_form.is_valid(), mfg_form.is_valid(), frm_form.is_valid()])
        if valid:
            try:
                formulation = create_formulation(
                    user=request.user,
                    batches=sel_form.cleaned_data["batches"],
                    manufacturing=mfg_form.save(commit=False),
                    formulation=frm_form.save(commit=False),
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, f"Formulation '{formulation.product_name}' created and QR code generated.")
                return redirect("manufacturing:detail", pk=formulation.pk)
    return render(request, "manufacturing/create.html", {
        "sel_form": sel_form, "mfg_form": mfg_form, "frm_form": frm_form,
        "has_eligible": sel_form.fields["batches"].queryset.exists(),
    })


@manufacturer_required
def history(request):
    qs = FinalFormulation.objects.select_related("manufacturing", "created_by", "qr_code")
    q = request.GET.get("q", "").strip()
    if q:
        qs = qs.filter(
            Q(product_name__icontains=q) | Q(formulation_code__icontains=q)
            | Q(manufacturing__batches__batch_id__icontains=q)
        ).distinct()
    page, params = paginate(request, qs, 10)
    return render(request, "manufacturing/history.html", {"page": page, "qs_params": params, "q": q})


@manufacturer_required
def detail(request, pk):
    formulation = get_object_or_404(
        FinalFormulation.objects.select_related("manufacturing", "created_by", "qr_code"), pk=pk
    )
    return render(request, "manufacturing/detail.html", {
        "formulation": formulation,
        "batches": formulation.manufacturing.batches.select_related("collection__herb"),
    })
