from django import template
from django.utils.safestring import mark_safe
import markdown as md
import re

register = template.Library()

@register.filter(name='markdown')
def markdown_format(text):
    """
    Convertit le texte markdown en HTML
    """
    if not text:
        return ''
    
    # Configuration markdown avec extensions
    html = md.markdown(
        text,
        extensions=[
            'nl2br',  # Convertir les sauts de ligne en <br>
            'fenced_code',  # Support des blocs de code
            'tables',  # Support des tableaux
        ]
    )
    
    # Ajouter des classes DaisyUI aux liens
    html = re.sub(
        r'<a href="([^"]+)">([^<]+)</a>',
        r'<a href="\1" class="link link-primary">\2</a>',
        html
    )
    
    return mark_safe(html)
