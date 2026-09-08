from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from patients.policy import has_capability
from staff_directory.access import require_staff, StaleVersion
from .forms import AnnouncementForm
from .services import announcements_for, banner_for, save_announcement


@login_required
def announcement_list(request):
    manage = request.GET.get("manage") == "true"
    rows = announcements_for(request.user, manage=manage)
    return render(request, "staff_announcements/list.html", {
        "page_obj": Paginator(rows, 50).get_page(request.GET.get("page")), "manage": manage,
        "can_manage": has_capability(request.user, "manage_settings"), "server_now": timezone.now(),
    })


@login_required
def announcement_detail(request, pk):
    manage = request.GET.get("manage") == "true"
    item = get_object_or_404(announcements_for(request.user, manage=manage), pk=pk)
    return render(request, "staff_announcements/detail.html", {
        "announcement": item, "manage": manage,
        "can_manage": has_capability(request.user, "manage_settings"), "server_now": timezone.now(),
    })


@login_required
def announcement_edit(request, pk=None):
    require_staff(request.user, manage=True)
    item = get_object_or_404(announcements_for(request.user, manage=True), pk=pk) if pk else None
    form = AnnouncementForm(request.POST or None, instance=item,
                            initial={"version": item.version if item else 1})
    status = 200
    if request.method == "POST" and form.is_valid():
        data = {key: form.cleaned_data[key] for key in form.Meta.fields}
        data["version"] = form.cleaned_data["version"]
        try:
            saved = save_announcement(request.user, data, pk=pk, request=request)
        except StaleVersion:
            form.add_error(None, "This announcement changed. Reload before saving.")
            status = 409
        else:
            return redirect(f"/staff/announcements/{saved.pk}/?manage=true")
    return render(request, "staff_announcements/form.html", {"form": form, "announcement": item}, status=status)


@login_required
def announcement_banner(request):
    require_staff(request.user)
    return render(request, "staff_announcements/banner.html", {
        "staff_announcement_banner": banner_for(request.user), "server_now": timezone.now(),
    })
