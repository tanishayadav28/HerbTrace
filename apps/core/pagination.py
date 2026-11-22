from django.core.paginator import Paginator


def paginate(request, queryset, per_page: int = 10):
    """Return a Page for ``?page=N`` and a querystring (without page) for links."""
    paginator = Paginator(queryset, per_page)
    page = paginator.get_page(request.GET.get("page"))
    params = request.GET.copy()
    params.pop("page", None)
    return page, params.urlencode()
