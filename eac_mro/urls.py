from django.contrib import admin
from django.urls import path, include
from rest_framework_simplejwt.views import TokenRefreshView

urlpatterns = [
    path('admin/',           admin.site.urls),
    path('api/auth/',        include('accounts.urls')),
    path('api/auth/refresh/',TokenRefreshView.as_view(), name='token_refresh'),
    path('api/pedidos/',     include('pedidos.urls')),
    path('api/produtos/',    include('produtos.urls')),
    path('api/notificacoes/',include('notificacoes.urls')),
]
