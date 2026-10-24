import logging
import requests

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


class SupabaseUser:
    def __init__(self, user_id, email=None):
        self.id = user_id
        self.email = email
        self.is_authenticated = True
        self.is_anonymous = False


class SupabaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        authorization = request.headers.get("Authorization", "")
        print("AUTHORIZATION HEADER RECEIVED:", bool(authorization))
        print("AUTHORIZATION PREFIX:", authorization.split()[0] if authorization.split() else "MISSING")
        parts = authorization.split()

        if not parts:
            logger.warning(
                "Supabase auth: Authorization header is MISSING on %s %s",
                request.method,
                request.path,
            )
            return None

        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed(
                "Invalid Authorization header format."
            )

        token = parts[1]
        supabase_url = getattr(
            settings, "SUPABASE_URL", ""
        ).rstrip("/")
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
            logger.exception("Supabase user verification request failed")
            raise AuthenticationFailed(
                "Could not verify the Supabase session."
            )

        if response.status_code != 200:
            logger.warning(
                "Supabase rejected access token: HTTP %s",
                response.status_code,
            )
            raise AuthenticationFailed(
                f"Supabase rejected the access token (HTTP {response.status_code})."
            )

        try:
            user_data = response.json()
        except ValueError:
            raise AuthenticationFailed(
                "Invalid response from Supabase."
            )

        user_id = user_data.get("id")
        email = user_data.get("email")

        if not user_id:
            raise AuthenticationFailed(
                "Supabase response did not include a user ID."
            )

        return SupabaseUser(user_id, email), token

    def authenticate_header(self, request):
        return "Bearer"
