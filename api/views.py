from django.conf import settings
from django.contrib.auth import authenticate
from rest_framework import generics, status
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import Document, QueryLog, UserSession
from .serializers import DocumentSerializer, LoginSerializer, QueryLogSerializer, RegisterSerializer
from .uploads import PayloadTooLarge, extract_text
from rest_framework.permissions import SAFE_METHODS, AllowAny, IsAuthenticated
from .permissions import IsOwner

def session_payload(session):
    return {"token": session.token, "expires_at": session.expires_at}

class RegisterView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()
        session = UserSession.objects.create(user=user)
        return Response(
            {"user": serializer.data, **session_payload(session=session)},
            status=status.HTTP_201_CREATED
        )

class LoginView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = authenticate(
            username=serializer.validated_data["username"],
            password=serializer.validated_data["password"]
        )

        if user is None:
            return Response(
                {"detail": "Invalid Username or password"},
                status=status.HTTP_401_UNAUTHORIZED
            )
        session = UserSession.objects.create(user=user)
        return Response(session_payload(session=session))


class LogoutView(APIView):
    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)

class DocumentListCreateView(generics.ListCreateAPIView):
    serializer_class = DocumentSerializer
    parser_classes = [JSONParser, MultiPartParser]

    def get_queryset(self):
        return Document.objects.filter(owner=self.request.user)

    def create(self, request, *args, **kwargs):
        upload = request.FILES.get("file")
        if upload is not None:
            data = {
                "title": request.data.get("title") or upload.name[:255],
                "content": extract_text(upload),
            }
        else:
            data = request.data

        serializer = self.get_serializer(data=data)
        serializer.is_valid(raise_exception = True)

        if len(serializer.validated_data["content"].encode("utf-8")) > settings.MAX_UPLOAD_BYTES:
            raise PayloadTooLarge("Content exceeds the maximum allowed size.")

        serializer.save(owner=request.user)
        return Response(serializer.data, status=status.HTTP_201_CREATED)

class DocumentDetailView(generics.RetrieveDestroyAPIView):
    serializer_class = DocumentSerializer
    permission_classes = [IsAuthenticated, IsOwner]

    def get_queryset(self):
        qs = Document.objects.all()
        if self.request.method in SAFE_METHODS:
            return qs.filter(owner=self.request.user)
        return qs

class QueryListView(generics.ListAPIView):
    serializer_class = QueryLogSerializer

    def get_queryset(self):
        return QueryLog.objects.filter(user=self.request.user)

class QueryCreateView(generics.CreateAPIView):
    serializer_class = QueryLogSerializer

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)
