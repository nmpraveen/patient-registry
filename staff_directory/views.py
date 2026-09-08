from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from patients.policy import has_capability
from .access import require_staff, StaleVersion
from .forms import ContactForm, PhoneFormSet
from .services import contacts_for, save_contact, set_favourite


@login_required
def contact_list(request):
    query = request.GET.get("q", "")[:100]
    favourites = request.GET.get("favourites") == "true"
    inactive = request.GET.get("include_inactive") == "true"
    contacts = contacts_for(request.user, q=query, favourites=favourites, include_inactive=inactive)
    page = Paginator(contacts, 50).get_page(request.GET.get("page"))
    return render(request, "staff_directory/list.html", {
        "page_obj": page, "q": query, "favourites": favourites, "include_inactive": inactive,
        "can_manage": has_capability(request.user, "manage_settings"),
    })


@login_required
def contact_detail(request, pk):
    manager = has_capability(request.user, "manage_settings")
    contact = get_object_or_404(contacts_for(request.user, include_inactive=manager), pk=pk)
    return render(request, "staff_directory/detail.html", {"contact": contact, "can_manage": manager})


@login_required
def contact_edit(request, pk=None):
    require_staff(request.user, manage=True)
    contact = get_object_or_404(contacts_for(request.user, include_inactive=True), pk=pk) if pk else None
    form = ContactForm(request.POST or None, instance=contact,
                       initial={"version": contact.version if contact else 1})
    phones = PhoneFormSet(request.POST or None, initial=contact.phones if contact else [], prefix="phones")
    status = 200
    if request.method == "POST":
        valid_form, valid_phones = form.is_valid(), phones.is_valid()
        if valid_form and valid_phones:
            data = {key: form.cleaned_data[key] for key in form.Meta.fields}
            data["version"] = form.cleaned_data["version"]
            data["phones"] = [{key: row.get(key, "") for key in ("label", "number", "extension")}
                              for row in phones.cleaned_data if row and not row.get("DELETE")]
            try:
                saved = save_contact(request.user, data, pk=pk, request=request)
            except StaleVersion:
                form.add_error(None, "This contact changed. Reload before saving.")
                status = 409
            else:
                return redirect("staff_directory:detail", pk=saved.pk)
    return render(request, "staff_directory/form.html", {"form": form, "phones": phones, "contact": contact}, status=status)


@login_required
@require_POST
def contact_favourite(request, pk):
    desired = request.POST.get("is_favourite")
    if desired not in ("true", "false"):
        from django.http import HttpResponseBadRequest
        return HttpResponseBadRequest("Choose a favourite state.")
    set_favourite(request.user, pk, desired == "true", request=request)
    return redirect("staff_directory:detail", pk=pk)
