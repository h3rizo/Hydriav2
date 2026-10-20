"""
Vue pour supprimer un document de documentation comptable.
"""
from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from .models import DocumentationComptable


@csrf_exempt
@require_http_methods(["POST"])
def api_delete_document(request, doc_id):
    """
    API pour supprimer un document de documentation comptable.
    """
    try:
        doc = get_object_or_404(DocumentationComptable, id=doc_id)
        doc.delete()

        return JsonResponse({
            'success': True,
            'message': 'Document supprimé avec succès'
        })
    except Exception as e:
        import traceback
        return JsonResponse({
            'success': False,
            'error': str(e),
            'traceback': traceback.format_exc()
        }, status=500)
