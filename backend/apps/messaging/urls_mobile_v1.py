from django.urls import path

from . import mobile_api_v1

app_name = 'messaging_mobile_v1'

urlpatterns = [
    path('bootstrap', mobile_api_v1.bootstrap, name='bootstrap'),
    path('changes', mobile_api_v1.changes, name='changes'),
    path('conversations/create', mobile_api_v1.conversation_create, name='conversation_create'),
    path('messages/send', mobile_api_v1.messages_send, name='messages_send'),
    path('conversations/<int:conversation_id>/read', mobile_api_v1.messages_read, name='messages_read'),
    path('devices/register', mobile_api_v1.register_device, name='register_device'),
    path('devices/unregister', mobile_api_v1.unregister_device, name='unregister_device'),
]
