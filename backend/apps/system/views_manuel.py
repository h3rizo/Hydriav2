"""
Vues pour le manuel d'utilisateur
"""
from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
import markdown
import os


@login_required
def manuel_utilisateur(request):
    """
    Affiche le manuel d'utilisateur avec navigation par sections
    """
    # Lire le fichier markdown
    manuel_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'docs',
        'MANUEL_UTILISATEUR.md'
    )

    with open(manuel_path, 'r', encoding='utf-8') as f:
        content_md = f.read()

    # Convertir en HTML avec extensions
    html_content = markdown.markdown(
        content_md,
        extensions=[
            'markdown.extensions.tables',
            'markdown.extensions.fenced_code',
            'markdown.extensions.toc',
            'markdown.extensions.attr_list'
        ]
    )

    # Extraire la table des matières (sections de niveau 2)
    sections = []
    lines = content_md.split('\n')
    for line in lines:
        if line.startswith('## '):
            # Extraire le titre et créer un ID
            titre = line.replace('## ', '').strip()
            # Enlever les numéros et emojis au début
            titre_clean = titre
            if '. ' in titre[:5]:
                titre_clean = titre.split('. ', 1)[1] if '. ' in titre else titre

            # Créer un ID pour l'ancre
            section_id = titre_clean.lower()
            section_id = section_id.replace(' ', '-')
            section_id = section_id.replace('é', 'e').replace('è', 'e').replace('ê', 'e')
            section_id = section_id.replace('à', 'a').replace('â', 'a')
            section_id = section_id.replace('ô', 'o').replace('î', 'i')
            section_id = ''.join(c for c in section_id if c.isalnum() or c == '-')

            sections.append({
                'titre': titre_clean,
                'id': section_id,
                'numero': titre.split('.')[0] if '. ' in titre[:5] else ''
            })

    context = {
        'html_content': html_content,
        'sections': sections
    }

    return render(request, 'system/manuel_utilisateur.html', context)


@login_required
def telecharger_manuel(request):
    """
    Télécharge le manuel d'utilisateur au format Markdown
    """
    manuel_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))),
        'docs',
        'MANUEL_UTILISATEUR.md'
    )

    with open(manuel_path, 'r', encoding='utf-8') as f:
        content = f.read()

    response = HttpResponse(content, content_type='text/markdown')
    response['Content-Disposition'] = 'attachment; filename="Manuel_Utilisateur_Hydria.md"'
    return response
