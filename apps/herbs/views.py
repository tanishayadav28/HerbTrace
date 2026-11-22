from django.contrib import messages
from django.db.models import Count, Q, ProtectedError
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.permissions import admin_required
from apps.core.pagination import paginate

from .forms import ApprovedRegionForm, HerbForm
from .models import ApprovedRegion, Herb


@admin_required
def herb_list(request):
    q = request.GET.get("q", "").strip()
    qs = Herb.objects.annotate(n_collections=Count("collections")).order_by("name")
    if q:
        qs = qs.filter(Q(name__icontains=q) | Q(botanical_name__icontains=q))
    page, params = paginate(request, qs, 10)
    return render(request, "herbs/herb_list.html", {"page": page, "qs_params": params, "q": q})


@admin_required
def herb_create(request):
    form = HerbForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        herb = form.save()
        messages.success(request, f"Herb '{herb.name}' added.")
        return redirect("herbs:herb_list")
    return render(request, "herbs/form.html", {"form": form, "title": "Add herb", "back": "herbs:herb_list"})


@admin_required
def herb_edit(request, pk):
    herb = get_object_or_404(Herb, pk=pk)
    form = HerbForm(request.POST or None, instance=herb)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Herb '{herb.name}' updated.")
        return redirect("herbs:herb_list")
    return render(request, "herbs/form.html", {"form": form, "title": f"Edit {herb.name}", "back": "herbs:herb_list"})


@admin_required
@require_POST
def herb_delete(request, pk):
    herb = get_object_or_404(Herb, pk=pk)
    try:
        herb.delete()
        messages.success(request, f"Herb '{herb.name}' deleted.")
    except ProtectedError:
        messages.error(
            request,
            f"'{herb.name}' already has collections and cannot be deleted. "
            "Mark it inactive instead so it disappears from new collection forms.",
        )
    return redirect("herbs:herb_list")


@admin_required
def region_list(request):
    qs = ApprovedRegion.objects.annotate(n_collections=Count("collections")).prefetch_related("herbs").order_by("name")
    page, params = paginate(request, qs, 10)
    return render(request, "herbs/region_list.html", {"page": page, "qs_params": params})


@admin_required
def region_create(request):
    form = ApprovedRegionForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        region = form.save()
        messages.success(request, f"Region '{region.name}' added.")
        return redirect("herbs:region_list")
    return render(request, "herbs/region_form.html", {"form": form, "title": "Add approved region"})


@admin_required
def region_edit(request, pk):
    region = get_object_or_404(ApprovedRegion, pk=pk)
    form = ApprovedRegionForm(request.POST or None, instance=region)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, f"Region '{region.name}' updated.")
        return redirect("herbs:region_list")
    return render(request, "herbs/region_form.html", {"form": form, "title": f"Edit {region.name}", "region": region})


@admin_required
@require_POST
def region_delete(request, pk):
    region = get_object_or_404(ApprovedRegion, pk=pk)
    if region.collections.exists():
        messages.error(
            request,
            f"'{region.name}' is referenced by existing collections and cannot be deleted. "
            "Mark it inactive instead so it is no longer used for new collections.",
        )
        return redirect("herbs:region_list")
    name = region.name
    region.delete()
    messages.success(request, f"Region '{name}' deleted.")
    return redirect("herbs:region_list")
