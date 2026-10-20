from django import forms


class CommentaireRelanceForm(forms.Form):
    """Un formulaire par point d'eau. Journal append-only : la soumission
    cree toujours de nouvelles entrees CommentaireRelance, jamais d'edition
    en place - pas de ModelForm, un formulaire simple suffit."""
    point_eau_id = forms.CharField(widget=forms.HiddenInput, required=False)
    contenu = forms.CharField(
        widget=forms.Textarea(attrs={'rows': 2, 'class': 'textarea textarea-bordered w-full'}),
        required=False,
        max_length=2000,
    )


CommentaireRelanceFormSet = forms.formset_factory(CommentaireRelanceForm, extra=0)
