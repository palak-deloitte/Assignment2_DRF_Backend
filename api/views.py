from rest_framework import status
from rest_framework.views import APIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from .serializers import RegisterSerializer, LoginSerializer
from .models import UserSession
from django.contrib.auth import authenticate

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