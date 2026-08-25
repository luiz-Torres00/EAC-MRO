from rest_framework import generics, permissions, status
from rest_framework.views import APIView
from rest_framework.response import Response
from .models import Notificacao
from .serializers import NotificacaoSerializer


class NotificacaoListView(generics.ListAPIView):
    """GET /api/notificacoes/ — retorna as do usuário logado."""
    permission_classes = [permissions.IsAuthenticated]
    serializer_class   = NotificacaoSerializer

    def get_queryset(self):
        qs = Notificacao.objects.filter(destinatario=self.request.user)
        apenas_nao_lidas = self.request.query_params.get('nao_lidas')
        if apenas_nao_lidas:
            qs = qs.filter(lida=False)
        return qs


class MarcarLidaView(APIView):
    """PATCH /api/notificacoes/<id>/lida/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request, pk):
        try:
            notif = Notificacao.objects.get(pk=pk, destinatario=request.user)
        except Notificacao.DoesNotExist:
            return Response({'detail': 'Não encontrada.'}, status=404)
        notif.lida = True
        notif.save()
        return Response({'ok': True})


class MarcarTodasLidasView(APIView):
    """PATCH /api/notificacoes/marcar-todas/"""
    permission_classes = [permissions.IsAuthenticated]

    def patch(self, request):
        Notificacao.objects.filter(destinatario=request.user, lida=False).update(lida=True)
        return Response({'ok': True})
