import requests
from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SupabaseUser:
    def __init__(self, user_id, email=None):
        self.id = user_id
        self.email = email
        self.is_authenticated = True
        self.is_anonymous = False


class SupabaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        authorization = request.headers.get("Authorization", "")
        parts = authorization.split()

        if not parts:
            return None

        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed("Invalid authorization header.")

        token = parts[1]

        supabase_url = getattr(settings, "SUPABASE_URL", "").rstrip("/")
        publishable_key = getattr(
            settings, "SUPABASE_PUBLISHABLE_KEY", ""
        )

        if not supabase_url or not publishable_key:
            raise AuthenticationFailed(
                "Supabase authentication is not configured."
            )

        try:
            response = requests.get(
                f"{supabase_url}/auth/v1/user",
                headers={
                    "apikey": publishable_key,
                    "Authorization": f"Bearer {token}",
                },
                timeout=10,
            )
        except requests.RequestException:
            raise AuthenticationFailed(
                "Unable to verify your session. Please try again."
            )

        if response.status_code != 200:
            raise AuthenticationFailed(
                f"Supabase rejected the token (HTTP {response.status_code})."
            )

        try:
            user_data = response.json()
        except ValueError:
            raise AuthenticationFailed(
                "Invalid authentication response."
            )

        user_id = user_data.get("id")
        email = user_data.get("email")

        if not user_id:
            raise AuthenticationFailed("User ID was not returned.")

        return SupabaseUser(user_id, email), token

    def authenticate_header(self, request):
        return "Bearer"
