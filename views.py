 from django.shortcuts import render, get_object_or_404
 from django.contrib.auth.decorators import login_required
 from django.views.decorators.http import require_http_methods
 from .models import Organization
 from .forms import OrganizationForm
 
 @login_required
 def organization_list(request):
     """Affiche la page complète avec la liste des organisations."""
     organizations = Organization.objects.all()
     return render(request, 'organizations/organization_list.html', {'organizations': organizations})
 
 @login_required
 def organization_detail(request, pk):
     """Renvoie le fragment HTML pour une seule ligne (mode affichage)."""
     organization = get_object_or_404(Organization, pk=pk)
     return render(request, 'organizations/partials/organization_detail.html', {'org': organization})
 
 @login_required
 def organization_edit(request, pk):
     """Renvoie le fragment HTML du formulaire d'édition pour une ligne."""
     organization = get_object_or_404(Organization, pk=pk)
     form = OrganizationForm(instance=organization)
     return render(request, 'organizations/partials/organization_edit_form.html', {'form': form, 'org': organization})
 
 @login_required
 @require_http_methods(["PUT"])
 def organization_update(request, pk):
     """Traite la mise à jour et renvoie la ligne mise à jour."""
     organization = get_object_or_404(Organization, pk=pk)
     form = OrganizationForm(request.POST, instance=organization)
     if form.is_valid():
         form.save()
         return organization_detail(request, pk)
     
     # En cas d'erreur, renvoyer le formulaire avec les erreurs
     return render(request, 'organizations/partials/organization_edit_form.html', {'form': form, 'org': organization})