import json
import os
import uuid
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from django.conf import settings
from rest_framework.authentication import BaseAuthentication
from rest_framework.exceptions import AuthenticationFailed


class SupabaseAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = request.headers.get("Authorization", "")
        if not header:
            return None

        parts = header.split()
        if len(parts) != 2 or parts[0].lower() != "bearer":
            raise AuthenticationFailed("Use a valid Bearer token.")

        supabase_url = settings.SUPABASE_URL.rstrip("/")
        api_key = settings.SUPABASE_PUBLISHABLE_KEY

        if not supabase_url or not api_key:
            raise AuthenticationFailed("Supabase authentication is not configured.")

        auth_request = Request(
            f"{supabase_url}/auth/v1/user",
            headers={
                "Authorization": f"Bearer {parts[1]}",
                "apikey": api_key,
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(auth_request, timeout=10) as response:
                user_data = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if exc.code in (400, 401, 403):
                raise AuthenticationFailed("Invalid or expired access token.")
            raise AuthenticationFailed("Supabase authentication is temporarily unavailable.")
        except (URLError, TimeoutError, OSError, ValueError):
            raise AuthenticationFailed("Could not verify your Supabase session.")

        try:
            user_id = uuid.UUID(user_data["id"])
        except (KeyError, ValueError, TypeError):
            raise AuthenticationFailed("Supabase returned an invalid user.")

        user = SimpleNamespace(
            id=user_id,
            email=user_data.get("email"),
            is_authenticated=True,
        )
        return user, parts[1]