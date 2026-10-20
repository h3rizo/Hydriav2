 from django import forms
 from .models import Organization
 
 class OrganizationForm(forms.ModelForm):
     class Meta:
         model = Organization
         fields = ['name', 'address', 'is_active']
         widgets = {
             'name': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
             'address': forms.TextInput(attrs={'class': 'input input-bordered w-full'}),
             'is_active': forms.CheckboxInput(attrs={'class': 'checkbox'}),
         }