from django import template

register = template.Library()

@register.simple_tag
def user_has_liked(post, user):
    """Vérifie si l'utilisateur a liké le post"""
    return post.user_has_liked(user)

@register.simple_tag
def user_has_disliked(post, user):
    """Vérifie si l'utilisateur a disliké le post"""
    return post.user_has_disliked(user)
