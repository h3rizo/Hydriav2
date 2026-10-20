from django.urls import path

from . import mobile_api_v1


app_name = 'mobile_api_v1'

urlpatterns = [
    path('auth/login', mobile_api_v1.login, name='login'),
    path('auth/refresh', mobile_api_v1.refresh, name='refresh'),
    path('me', mobile_api_v1.me, name='me'),
    path('bootstrap', mobile_api_v1.bootstrap, name='bootstrap'),
    path('changes', mobile_api_v1.changes, name='changes'),
    path('purchases/<uuid:purchase_id>/receive', mobile_api_v1.receive_purchase, name='receive_purchase'),
    path('deliveries', mobile_api_v1.create_delivery, name='create_delivery'),
    path('transfers', mobile_api_v1.create_transfer, name='create_transfer'),
    path('transfers/<uuid:transfer_id>/status', mobile_api_v1.update_transfer, name='update_transfer'),
    path('inventories', mobile_api_v1.create_inventory, name='create_inventory'),
    path('stocks/<uuid:stock_id>/adjust', mobile_api_v1.adjust_stock, name='adjust_stock'),
    path('field-returns', mobile_api_v1.create_field_return, name='create_field_return'),
]
