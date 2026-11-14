import logging
from datetime import datetime, timedelta, timezone as datetime_timezone
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

from cryptography.fernet import Fernet
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from rest_framework import status
from rest_framework.test import APITestCase

from .apps import OAuthCallbackLogFilter
from .models import Brand, ContentPost, Notification, ScheduledPost, SocialAccount
from .services.instagram_oauth import (
    INSTAGRAM_SCOPES,
    InstagramOAuthError,
    _exchange_code,
    _fetch_client_business_id,
    create_instagram_authorization_url,
    _fetch_assigned_instagram_accounts,
    _log_instagram_token_debug,
)
from .services.instagram_publishing import build_instagram_caption
from .services.scheduling import publish_due_posts
from .services.social_tokens import decrypt_social_token, encrypt_social_token

NOW = datetime(2030, 1, 16, tzinfo=datetime_timezone.utc)
IG_ID = "17841400000000000"
TOKEN = "ig-long-lived-token-secret"
TEST_KEY = "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 32


def graph_response(status_code, payload):
    return SimpleNamespace(status_code=status_code, json=lambda: payload)


def social_settings():
    return override_settings(
        SOCIAL_INSTAGRAM_META_APP_ID="meta-app-id",
        SOCIAL_INSTAGRAM_META_APP_SECRET="meta-app-secret",
        SOCIAL_INSTAGRAM_CONFIG_ID="instagram-config-id",
        SOCIAL_INSTAGRAM_REDIRECT_URI=(
            "https://social.example/api/social/oauth/instagram/callback/"
        ),
        SOCIAL_INSTAGRAM_API_VERSION="v27.0",
        SOCIAL_TOKEN_ENCRYPTION_KEY=TEST_KEY,
        SUPABASE_URL="https://supabase.example.invalid",
        SUPABASE_SERVICE_ROLE_KEY="service-role-test-key",
        SUPABASE_STORAGE_BUCKET="content-media",
    )


class InstagramOAuthTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)

    def test_connect_reports_unconfigured_without_claiming_success(self):
        response = self.client.post(
            "/api/social/accounts/instagram/connect/", {}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertFalse(response.data["configured"])
        self.assertFalse(SocialAccount.objects.exists())

    @social_settings()
    def test_connect_returns_a_unified_login_authorization_url(self):
        response = self.client.post(
            "/api/social/accounts/instagram/connect/",
            {"response_mode": "web"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        url = response.data["authorization_url"]
        self.assertTrue(
            url.startswith("https://www.facebook.com/dialog/oauth?")
        )
        self.assertIn("config_id=instagram-config-id", url)
        self.assertIn("prompt=login", url)
        self.assertIn("response_type=code", url)
        self.assertNotIn("scope=", url)
        state = SocialAccount.objects.none()
        self.assertFalse(state.exists())
        from .models import SocialOAuthState

        oauth_state = SocialOAuthState.objects.get()
        self.assertEqual(oauth_state.platform, SocialAccount.Platform.INSTAGRAM)
        self.assertEqual(oauth_state.owner_id, self.user.id)
        self.assertEqual(oauth_state.response_mode, "web")

    @social_settings()
    def test_code_exchange_sends_the_dialog_redirect_uri(self):
        dialog_query = parse_qs(
            urlsplit(
                create_instagram_authorization_url(self.user.id)
            ).query
        )

        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=graph_response(200, {"access_token": TOKEN}),
        ) as meta_get:
            _exchange_code("authorization-code")

        exchange_params = meta_get.call_args.kwargs["params"]
        self.assertEqual(
            exchange_params["redirect_uri"],
            dialog_query["redirect_uri"][0],
        )
        self.assertEqual(
            exchange_params["redirect_uri"],
            "https://social.example/api/social/oauth/instagram/callback/",
        )

    @social_settings()
    def test_dialog_and_exchange_follow_a_reconfigured_redirect_uri(self):
        alternate = (
            "https://login.example.test/api/social/oauth/instagram/callback/"
        )

        with self.settings(SOCIAL_INSTAGRAM_REDIRECT_URI=alternate):
            authorization_url = create_instagram_authorization_url(
                self.user.id
            )
            with patch(
                "core.services.instagram_oauth.requests.get",
                return_value=graph_response(200, {"access_token": TOKEN}),
            ) as meta_get:
                _exchange_code("authorization-code")

        dialog_uri = parse_qs(
            urlsplit(authorization_url).query
        )["redirect_uri"][0]
        self.assertEqual(dialog_uri, alternate)
        self.assertEqual(
            meta_get.call_args.kwargs["params"]["redirect_uri"],
            dialog_uri,
        )

    @social_settings()
    def test_callback_exchange_reuses_the_authorization_url_redirect_uri(self):
        connect = self.client.post(
            "/api/social/accounts/instagram/connect/", {}, format="json"
        )
        self.assertEqual(connect.status_code, status.HTTP_200_OK)
        dialog_query = parse_qs(
            urlsplit(connect.data["authorization_url"]).query
        )

        with patch(
            "core.services.instagram_oauth.requests.get"
        ) as meta_get:
            meta_get.side_effect = [
                graph_response(200, {"access_token": TOKEN}),
                graph_response(200, {"client_business_id": "biz-123"}),
                graph_response(200, {"data": []}),
                graph_response(
                    200,
                    {"data": [{"id": IG_ID, "username": "ibda.studio"}]},
                ),
            ]

            callback = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {
                    "code": "authorization-code",
                    "state": dialog_query["state"][0],
                },
            )

        self.assertIn("status=connected", callback["Location"])
        self.assertEqual(
            meta_get.call_args_list[0].kwargs["params"]["redirect_uri"],
            dialog_query["redirect_uri"][0],
        )

    @social_settings()
    def test_callback_connects_accounts_from_unified_login(self):
        from .models import SocialOAuthState
        import hashlib

        state = "instagram-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )

        with patch(
            "core.services.instagram_oauth.requests.get"
        ) as meta_get:
            meta_get.side_effect = [
                graph_response(200, {"access_token": TOKEN}),
                graph_response(200, {"client_business_id": "biz-123"}),
                graph_response(200, {"data": []}),
                graph_response(
                    200,
                    {
                        "data": [
                            {"id": IG_ID, "username": "ibda.studio"},
                            {"id": f"{IG_ID}-2", "username": "ibda.creator"},
                        ]
                    },
                ),
            ]

            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": "authorization-code", "state": state},
            )

        self.assertEqual(response.status_code, status.HTTP_302_FOUND)
        self.assertIn("status=connected", response["Location"])
        account = SocialAccount.objects.get(
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=IG_ID,
        )
        self.assertEqual(account.platform_account_id, IG_ID)
        self.assertEqual(account.display_name, "ibda.studio")
        self.assertEqual(account.scopes, INSTAGRAM_SCOPES)
        self.assertEqual(decrypt_social_token(account.access_token_encrypted), TOKEN)
        self.assertIsNone(account.token_expires_at)
        self.assertEqual(account.client_business_id, "biz-123")
        self.assertEqual(account.oauth_config_id, "instagram-config-id")
        self.assertEqual(
            SocialAccount.objects.filter(
                owner_id=self.user.id,
                platform=SocialAccount.Platform.INSTAGRAM,
                status=SocialAccount.Status.CONNECTED,
            ).count(),
            2,
        )
        exchange_call = meta_get.call_args_list[0]
        self.assertEqual(
            exchange_call.args[0],
            "https://graph.facebook.com/v27.0/oauth/access_token",
        )
        self.assertEqual(
            exchange_call.kwargs["params"]["client_id"], "meta-app-id"
        )
        self.assertIn("client_secret", exchange_call.kwargs["params"])
        self.assertEqual(
            exchange_call.kwargs["params"]["redirect_uri"],
            "https://social.example/api/social/oauth/instagram/callback/",
        )
        self.assertNotIn(TOKEN, str(exchange_call.kwargs))
        self.assertEqual(
            meta_get.call_args_list[1].kwargs["headers"]["Authorization"],
            f"Bearer {TOKEN}",
        )

    @social_settings()
    def test_callback_requires_an_assigned_instagram_account(self):
        from .models import SocialOAuthState
        import hashlib

        state = "personal-state"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )

        with patch(
            "core.services.instagram_oauth.requests.get"
        ) as meta_get:
            meta_get.side_effect = [
                graph_response(200, {"access_token": TOKEN}),
                graph_response(200, {"client_business_id": "biz-123"}),
                graph_response(200, {"data": []}),
                graph_response(200, {"data": []}),
                graph_response(
                    200,
                    {
                        "data": {
                            "is_valid": True,
                            "type": "SYSTEM_USER",
                            "app_id": "meta-app-id",
                            "profile_id": "private-profile-id",
                            "scopes": ["instagram_basic", "instagram_content_publish"],
                            "granular_scopes": [
                                {
                                    "scope": "instagram_basic",
                                    "target_ids": ["private-asset-id"],
                                }
                            ],
                        }
                    },
                ),
            ]

            with self.assertLogs(level="INFO") as captured:
                response = self.client.get(
                    "/api/social/oauth/instagram/callback/",
                    {"code": "authorization-code", "state": state},
                )

        self.assertIn("status=failed", response["Location"])
        lookup = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.assigned_accounts_lookup"
        )
        self.assertEqual(lookup.http_status_code, 200)
        self.assertTrue(lookup.request_succeeded)
        self.assertEqual(lookup.account_count, 0)
        token_debug = next(
            record
            for record in captured.records
            if getattr(record, "event", "") == "instagram_oauth.token_debug"
        )
        self.assertEqual(token_debug.token_type, "SYSTEM_USER")
        self.assertTrue(token_debug.token_valid)
        self.assertTrue(token_debug.app_matches)
        self.assertTrue(token_debug.business_context_present)
        self.assertEqual(token_debug.granular_scope_target_count, 1)
        self.assertNotIn("private-profile-id", token_debug.getMessage())
        self.assertNotIn("private-asset-id", token_debug.getMessage())
        callback_failure = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.callback_failed"
        )
        self.assertEqual(
            callback_failure.failure_category, "instagram_oauth_error"
        )
        self.assertEqual(
            callback_failure.detail,
            "No Instagram professional accounts were shared with IBDA.",
        )
        business_lookup = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.business_portfolio"
        )
        self.assertTrue(business_lookup.request_succeeded)
        self.assertTrue(business_lookup.portfolio_found)
        account_validation = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.account_validation"
        )
        self.assertEqual(account_validation.returned_accounts, 0)
        self.assertEqual(account_validation.accepted_accounts, 0)
        self.assertEqual(account_validation.rejected_accounts, 0)
        self.assertFalse(
            SocialAccount.objects.filter(
                platform=SocialAccount.Platform.INSTAGRAM
            ).exists()
        )

    def test_instagram_callback_query_is_redacted_from_server_logs(self):
        record = logging.LogRecord(
            "django.server",
            logging.INFO,
            __file__,
            1,
            'GET /api/social/oauth/instagram/callback/?code=secret HTTP/1.1',
            (),
            None,
        )

        OAuthCallbackLogFilter().filter(record)

        self.assertNotIn("secret", record.getMessage())
        self.assertIn("[redacted]", record.getMessage())

    @social_settings()
    def test_assigned_account_diagnostics_redact_provider_secrets(self):
        opaque_secret = "opaque-unrecognized-secret-value-1234567890"
        error_message = (
            f"token {TOKEN}; code=auth-code-secret; "
            f"client_secret=meta-app-secret; "
            f"encryption_key={TEST_KEY}; "
            f"{opaque_secret}; "
            "https://graph.example/?access_token=url-token"
        )
        response = graph_response(
            400,
            {
                "error": {
                    "code": 190,
                    "type": "OAuthException",
                    "error_subcode": 36008,
                    "message": error_message,
                }
            },
        )

        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="WARNING"
        ) as captured:
            with self.assertRaises(InstagramOAuthError):
                _fetch_assigned_instagram_accounts(TOKEN)

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.assigned_accounts_lookup"
        )
        self.assertEqual(diagnostic.http_status_code, 400)
        self.assertFalse(diagnostic.request_succeeded)
        self.assertEqual(diagnostic.account_count, 0)
        self.assertEqual(diagnostic.graph_error_code, 190)
        self.assertEqual(diagnostic.graph_error_type, "OAuthException")
        self.assertEqual(diagnostic.graph_error_subcode, 36008)
        log_output = (
            diagnostic.getMessage()
            + str(diagnostic.graph_error_message)
        )
        for sensitive_value in (
            TOKEN,
            "auth-code-secret",
            "meta-app-secret",
            TEST_KEY,
            opaque_secret,
            "url-token",
        ):
            self.assertNotIn(sensitive_value, log_output)
        self.assertIn("[redacted-credential]", log_output)
        self.assertIn("[redacted-url]", log_output)

    @social_settings()
    def test_callback_diagnostics_redact_sensitive_exception_details(self):
        from .models import SocialOAuthState
        import hashlib

        state = "diagnostic-state"
        authorization_code = "callback-code-secret"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )
        error_detail = (
            f"access_token={TOKEN}; code={authorization_code}; "
            "client_secret=meta-app-secret; "
            f"encryption_key={TEST_KEY}"
        )

        with patch(
            "core.views.connect_instagram_account",
            side_effect=InstagramOAuthError(error_detail),
        ), self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": authorization_code, "state": state},
            )

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.callback_failed"
        )
        self.assertEqual(
            diagnostic.failure_category, "instagram_oauth_error"
        )
        self.assertEqual(
            diagnostic.detail,
            "[redacted-credential]; " * 3 + "[redacted-credential]",
        )
        self.assertIn("status=failed", response["Location"])
        log_output = diagnostic.getMessage() + diagnostic.detail
        for sensitive_value in (
            TOKEN,
            authorization_code,
            "meta-app-secret",
            TEST_KEY,
        ):
            self.assertNotIn(sensitive_value, log_output)

    @social_settings()
    def test_unexpected_callback_diagnostics_do_not_log_exception_text(self):
        from .views import SocialOAuthCallbackView

        sensitive_error = (
            f"{TOKEN} callback-code-secret meta-app-secret {TEST_KEY}"
        )
        with patch.object(
            SocialOAuthCallbackView,
            "_instagram_callback_response",
            side_effect=RuntimeError(sensitive_error),
        ), self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": "callback-code-secret"},
            )

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.callback_failed"
        )
        self.assertEqual(diagnostic.failure_category, "unexpected")
        self.assertEqual(
            diagnostic.detail, "Unexpected Instagram OAuth callback error."
        )
        self.assertIn("status=failed", response["Location"])
        log_output = diagnostic.getMessage() + diagnostic.detail
        for sensitive_value in (
            TOKEN,
            "callback-code-secret",
            "meta-app-secret",
            TEST_KEY,
        ):
            self.assertNotIn(sensitive_value, log_output)

    @social_settings()
    @patch("core.services.instagram_oauth.requests.get")
    def test_connection_fails_if_meta_shares_no_instagram_accounts(self, meta_get):
        from .services.instagram_oauth import (
            InstagramOAuthError,
            connect_instagram_account,
        )

        meta_get.side_effect = [
            graph_response(200, {"access_token": TOKEN}),
            graph_response(200, {"client_business_id": "biz-123"}),
            graph_response(200, {"data": []}),
            graph_response(200, {"data": []}),
            graph_response(
                200,
                {
                    "data": {
                        "is_valid": True,
                        "type": "USER",
                        "app_id": "meta-app-id",
                        "scopes": ["instagram_basic"],
                    }
                },
            ),
        ]

        with self.assertRaises(InstagramOAuthError):
            connect_instagram_account(self.user.id, "authorization-code")

        self.assertFalse(SocialAccount.objects.exists())

    @social_settings()
    def test_code_exchange_failure_logs_sanitized_meta_error(self):
        authorization_code = "exchange-code-secret-0123456789abcdef"
        meta_message = (
            f"Invalid OAuth access token: code={authorization_code}; "
            f"client_secret=meta-app-secret; access_token={TOKEN}; "
            "https://graph.example/oauth?code=url-code-value"
        )
        response = graph_response(
            400,
            {
                "error": {
                    "code": 190,
                    "type": "OAuthException",
                    "error_subcode": 463,
                    "message": meta_message,
                }
            },
        )

        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="WARNING"
        ) as captured:
            with self.assertRaises(InstagramOAuthError) as raised:
                _exchange_code(authorization_code)

        self.assertEqual(
            str(raised.exception),
            "Meta authorization could not be completed.",
        )
        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "") == "instagram_oauth.code_exchange"
        )
        self.assertEqual(diagnostic.http_status_code, 400)
        self.assertEqual(diagnostic.graph_error_code, 190)
        self.assertEqual(diagnostic.graph_error_type, "OAuthException")
        self.assertEqual(diagnostic.graph_error_subcode, 463)
        log_output = (
            diagnostic.getMessage()
            + str(diagnostic.graph_error_message)
            + str(diagnostic.graph_error_type)
        )
        for sensitive_value in (
            TOKEN,
            authorization_code,
            "meta-app-secret",
            "url-code-value",
        ):
            self.assertNotIn(sensitive_value, log_output)
        self.assertIn("[redacted-credential]", log_output)
        self.assertIn("[redacted-url]", log_output)

    @social_settings()
    def test_code_exchange_failure_tolerates_a_non_json_body(self):
        def invalid_json():
            raise ValueError("Expecting value: line 1 column 1 (char 0)")

        response = SimpleNamespace(status_code=502, json=invalid_json)

        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="WARNING"
        ) as captured:
            with self.assertRaises(InstagramOAuthError):
                _exchange_code("exchange-code")

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "") == "instagram_oauth.code_exchange"
        )
        self.assertEqual(diagnostic.http_status_code, 502)
        self.assertIsNone(diagnostic.graph_error_code)
        self.assertIsNone(diagnostic.graph_error_type)
        self.assertIsNone(diagnostic.graph_error_subcode)
        self.assertIsNone(diagnostic.graph_error_message)
        self.assertIn("graph_error_code=-", diagnostic.getMessage())

    @social_settings()
    def test_callback_logs_redacted_code_exchange_failure(self):
        from .models import SocialOAuthState
        import hashlib

        state = "exchange-diagnostic-state"
        authorization_code = "callback-exchange-code-secret"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )

        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=graph_response(
                400,
                {
                    "error": {
                        "code": 100,
                        "type": "OAuthException",
                        "error_subcode": 36009,
                        "message": (
                            "This authorization code has already been used: "
                            f"code={authorization_code}; "
                            f"access_token={TOKEN}"
                        ),
                    }
                },
            ),
        ), self.assertLogs(level="WARNING") as captured:
            response = self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"code": authorization_code, "state": state},
            )

        self.assertIn("status=failed", response["Location"])
        exchange = next(
            record
            for record in captured.records
            if getattr(record, "event", "") == "instagram_oauth.code_exchange"
        )
        self.assertEqual(exchange.graph_error_code, 100)
        self.assertEqual(exchange.graph_error_subcode, 36009)
        callback_failure = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.callback_failed"
        )
        self.assertEqual(
            callback_failure.detail,
            "Meta authorization could not be completed.",
        )
        log_output = "\n".join(
            record.getMessage() for record in captured.records
        )
        for sensitive_value in (
            TOKEN,
            authorization_code,
            "meta-app-secret",
            TEST_KEY,
        ):
            self.assertNotIn(sensitive_value, log_output)
        self.assertFalse(
            SocialAccount.objects.filter(
                platform=SocialAccount.Platform.INSTAGRAM
            ).exists()
        )

    @social_settings()
    def test_business_portfolio_graph_error_is_rendered_and_redacted(self):
        access_token = "business-access-token-secret"
        message = (
            f"Invalid token access_token={access_token}; "
            "https://graph.example/business?code=url-code-secret"
        )
        response = graph_response(
            400,
            {
                "error": {
                    "code": 100,
                    "type": "OAuthException",
                    "error_subcode": 36008,
                    "message": message,
                }
            },
        )
        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="WARNING"
        ) as captured:
            with self.assertRaises(InstagramOAuthError):
                _fetch_client_business_id(access_token)

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.business_portfolio"
        )
        self.assertEqual(diagnostic.http_status_code, 400)
        self.assertFalse(diagnostic.request_succeeded)
        self.assertFalse(diagnostic.portfolio_found)
        self.assertEqual(diagnostic.graph_error_code, 100)
        self.assertEqual(diagnostic.graph_error_type, "OAuthException")
        self.assertEqual(diagnostic.graph_error_subcode, 36008)
        rendered = diagnostic.getMessage() + str(diagnostic.graph_error_message)
        for secret in (access_token, "url-code-secret"):
            self.assertNotIn(secret, rendered)
        self.assertIn("[redacted-credential]", rendered)
        self.assertIn("[redacted-url]", rendered)

    @social_settings()
    def test_invalid_assigned_account_logs_rejection_reason(self):
        response = graph_response(
            200,
            {"data": [{"username": "no-account-id"}]},
        )
        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="WARNING"
        ) as captured:
            with self.assertRaises(InstagramOAuthError):
                _fetch_assigned_instagram_accounts("internal-token")

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "")
            == "instagram_oauth.account_validation"
        )
        self.assertEqual(diagnostic.returned_accounts, 1)
        self.assertEqual(diagnostic.accepted_accounts, 0)
        self.assertEqual(diagnostic.rejected_accounts, 1)
        self.assertEqual(diagnostic.rejection_reason, "invalid_id")
        self.assertNotIn("internal-token", diagnostic.getMessage())

    @social_settings()
    def test_token_debug_logs_principal_metadata_without_identifiers(self):
        response = graph_response(
            200,
            {
                "data": {
                    "is_valid": True,
                    "type": "SYSTEM_USER",
                    "app_id": "meta-app-id",
                    "user_id": "private-user-id",
                    "profile_id": "private-profile-id",
                    "scopes": [
                        "instagram_basic",
                        "instagram_content_publish",
                        "unexpected-token-like-value",
                    ],
                    "granular_scopes": [
                        {
                            "scope": "instagram_basic",
                            "target_ids": ["private-asset-id"],
                        }
                    ],
                }
            },
        )
        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=response,
        ) as meta_get, self.assertLogs(
            "core.services.instagram_oauth", level="INFO"
        ) as captured:
            _log_instagram_token_debug(TOKEN, True)

        diagnostic = next(
            record
            for record in captured.records
            if getattr(record, "event", "") == "instagram_oauth.token_debug"
        )
        self.assertEqual(diagnostic.token_type, "SYSTEM_USER")
        self.assertTrue(diagnostic.token_valid)
        self.assertTrue(diagnostic.app_matches)
        self.assertTrue(diagnostic.business_context_present)
        self.assertEqual(
            diagnostic.scope_names,
            "instagram_basic,instagram_content_publish",
        )
        self.assertEqual(diagnostic.granular_scope_target_count, 1)
        self.assertEqual(
            meta_get.call_args.args[0],
            "https://graph.facebook.com/v27.0/debug_token",
        )
        self.assertNotIn("?", meta_get.call_args.args[0])
        rendered = "\n".join(record.getMessage() for record in captured.records)
        for secret in (
            TOKEN,
            "meta-app-secret",
            TEST_KEY,
            "private-user-id",
            "private-profile-id",
            "private-asset-id",
            "unexpected-token-like-value",
        ):
            self.assertNotIn(secret, rendered)

    @social_settings()
    def test_encryption_and_database_save_stages_log_only_safe_counts(self):
        from .services.instagram_oauth import connect_instagram_account

        authorization_code = "callback-code-secret"
        meta_get_responses = [
            graph_response(200, {"access_token": TOKEN}),
            graph_response(200, {"client_business_id": "business-id-secret"}),
            graph_response(200, {"data": []}),
            graph_response(
                200,
                {"data": [{"id": IG_ID, "username": "ibda.studio"}]},
            ),
        ]
        with patch(
            "core.services.instagram_oauth.requests.get",
            side_effect=meta_get_responses,
        ), self.assertLogs(
            "core.services.instagram_oauth", level="INFO"
        ) as captured:
            self.assertEqual(
                connect_instagram_account(self.user.id, authorization_code),
                1,
            )

        events = {
            record.event: record
            for record in captured.records
            if getattr(record, "event", "").startswith("instagram_oauth.")
        }
        self.assertTrue(events["instagram_oauth.token_encryption"].encryption_succeeded)
        self.assertEqual(events["instagram_oauth.token_encryption"].account_count, 1)
        self.assertTrue(events["instagram_oauth.database_save"].save_succeeded)
        self.assertEqual(events["instagram_oauth.database_save"].account_count, 1)
        rendered = "\n".join(record.getMessage() for record in captured.records)
        for secret in (
            TOKEN,
            authorization_code,
            "business-id-secret",
            "meta-app-secret",
            TEST_KEY,
        ):
            self.assertNotIn(secret, rendered)

    @social_settings()
    def test_callback_logs_state_and_code_validation_without_values(self):
        import hashlib
        from .models import SocialOAuthState

        private_state = "private-state-value"
        with self.assertLogs("core.views", level="WARNING") as invalid_state_logs:
            self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"state": private_state},
            )
        invalid_state_record = next(
            record
            for record in invalid_state_logs.records
            if getattr(record, "event", "")
            == "instagram_oauth.state_validation"
        )
        self.assertFalse(invalid_state_record.state_valid)
        self.assertNotIn(private_state, invalid_state_record.getMessage())

        valid_state = "valid-state-without-code"
        SocialOAuthState.objects.create(
            state_digest=hashlib.sha256(valid_state.encode("ascii")).hexdigest(),
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            expires_at=NOW,
        )
        with self.assertLogs(level="WARNING") as missing_code_logs:
            self.client.get(
                "/api/social/oauth/instagram/callback/",
                {"state": valid_state},
            )
        code_record = next(
            record
            for record in missing_code_logs.records
            if getattr(record, "event", "")
            == "instagram_oauth.authorization_code_validation"
        )
        self.assertFalse(code_record.code_present)
        self.assertFalse(code_record.code_valid)
        self.assertNotIn(valid_state, "\n".join(
            record.getMessage() for record in missing_code_logs.records
        ))

    @social_settings()
    def test_exchange_redirect_uri_is_byte_identical_to_dialog(self):
        dialog_uri = parse_qs(
            urlsplit(create_instagram_authorization_url(self.user.id)).query
        )["redirect_uri"][0]
        with patch(
            "core.services.instagram_oauth.requests.get",
            return_value=graph_response(200, {"access_token": TOKEN}),
        ) as meta_get:
            _exchange_code("authorization-code")
        sent = meta_get.call_args.kwargs["params"]["redirect_uri"]
        self.assertEqual(sent, dialog_uri)
        for variant in (
            dialog_uri.replace("https://", "http://"),
            dialog_uri.replace("social.example", "other.example"),
            dialog_uri.rstrip("/"),
            dialog_uri.replace("/oauth/", "/auth/"),
        ):
            self.assertNotEqual(sent, variant)

@social_settings()
class InstagramPublishingTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(
            owner_id=self.user.id, name="Ibda Project"
        )
        self.account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=IG_ID,
            display_name="ibda.studio",
            access_token_encrypted=encrypt_social_token(TOKEN),
            token_expires_at=NOW + timedelta(days=30),
            client_business_id="biz-123",
            oauth_config_id="instagram-config-id",
        )

    def create_post(self, **overrides):
        values = {
            "brand": self.brand,
            "title": "Launch",
            "body": "Hello from IBDA",
            "hashtags": ["ibda", "launch"],
            "platform": ContentPost.Platform.INSTAGRAM,
            "status": ContentPost.Status.APPROVED,
            "image_url": "https://cdn.example/post.jpg",
        }
        values.update(overrides)
        return ContentPost.objects.create(**values)

    def due_post(self, post, account=None):
        return ScheduledPost.objects.create(
            post=post,
            platform=ContentPost.Platform.INSTAGRAM,
            social_account=self.account if account is None else account,
            scheduled_for=NOW - timedelta(minutes=2),
            timezone_name="UTC",
        )

    @patch("core.services.instagram_publishing.time.sleep")
    @patch("core.services.instagram_publishing.requests.get")
    @patch("core.services.instagram_publishing.requests.post")
    def test_due_image_post_publishes_to_instagram(
        self, graph_post, graph_get, _sleep
    ):
        graph_post.side_effect = [
            graph_response(200, {"id": "container-1"}),
            graph_response(200, {"id": "media-1"}),
        ]
        graph_get.return_value = graph_response(
            200, {"status_code": "FINISHED"}
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["published"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PUBLISHED)
        self.assertEqual(scheduled.external_post_id, "media-1")
        self.assertEqual(scheduled.published_at, NOW)
        self.assertEqual(scheduled.error_message, "")
        scheduled.post.refresh_from_db()
        self.assertEqual(scheduled.post.status, ContentPost.Status.PUBLISHED)

        container_url = graph_post.call_args_list[0].args[0]
        self.assertEqual(
            container_url,
            f"https://graph.facebook.com/v27.0/{IG_ID}/media",
        )
        container_data = graph_post.call_args_list[0].kwargs["data"]
        self.assertEqual(
            container_data["image_url"], "https://cdn.example/post.jpg"
        )
        self.assertEqual(
            container_data["caption"], "Hello from IBDA\n\n#ibda #launch"
        )
        self.assertEqual(container_data["access_token"], TOKEN)
        self.assertEqual(
            graph_get.call_args.kwargs["headers"]["Authorization"],
            f"Bearer {TOKEN}",
        )

        publish_data = graph_post.call_args_list[1].kwargs["data"]
        self.assertEqual(publish_data["creation_id"], "container-1")
        self.assertNotIn(TOKEN, publish_data["creation_id"])
        self.assertTrue(
            Notification.objects.filter(
                related_object_id=scheduled.id,
                notification_type=Notification.Type.POST_PUBLISHED,
            ).exists()
        )

    @patch("core.services.instagram_publishing.requests.post")
    def test_post_without_an_image_fails_without_network_calls(self, graph_post):
        scheduled = self.due_post(self.create_post(image_url=""))

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertIn("no public image", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.instagram_publishing.requests.post")
    def test_unlinked_instagram_post_is_blocked(self, graph_post):
        scheduled = self.due_post(self.create_post(), account=None)
        scheduled.social_account = None
        scheduled.save(update_fields=["social_account"])

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["blocked"], 1)
        scheduled.refresh_from_db()
        self.assertIn("not linked to an Instagram account", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.instagram_publishing.requests.post")
    def test_legacy_instagram_login_account_requires_reconnection(self, graph_post):
        legacy_account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=f"{IG_ID}-legacy",
            display_name="legacy.account",
            access_token_encrypted=encrypt_social_token(TOKEN),
        )
        scheduled = self.due_post(
            self.create_post(),
            account=legacy_account,
        )

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertIn("previous login flow", scheduled.error_message)
        graph_post.assert_not_called()

    @patch("core.services.instagram_publishing.time.sleep")
    @patch("core.services.instagram_publishing.requests.get")
    @patch("core.services.instagram_publishing.requests.post")
    def test_processing_containers_are_retried(
        self, graph_post, graph_get, _sleep
    ):
        graph_post.return_value = graph_response(200, {"id": "container-2"})
        graph_get.return_value = graph_response(
            200, {"status_code": "IN_PROGRESS"}
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["retried"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.PENDING)
        self.assertEqual(scheduled.attempts, 1)
        self.assertGreater(scheduled.scheduled_for, NOW)
        self.assertIn("still processing", scheduled.error_message)

    @patch("core.services.instagram_publishing.requests.post")
    def test_permanent_token_error_is_not_retried_and_redacts_the_token(
        self, graph_post
    ):
        graph_post.return_value = graph_response(
            400,
            {"error": {"code": 190, "message": f"Invalid token {TOKEN}"}},
        )
        scheduled = self.due_post(self.create_post())

        counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        scheduled.refresh_from_db()
        self.assertEqual(scheduled.status, ScheduledPost.Status.FAILED)
        self.assertEqual(scheduled.attempts, 1)
        self.assertNotIn(TOKEN, scheduled.error_message)
        self.assertIn("[redacted]", scheduled.error_message)

    def test_expired_token_requires_reconnect_without_network_calls(self):
        from django.utils import timezone

        self.account.token_expires_at = timezone.now() - timedelta(minutes=1)
        self.account.save(update_fields=["token_expires_at"])
        scheduled = self.due_post(self.create_post())

        with patch(
            "core.services.instagram_publishing.requests.post"
        ) as graph_post:
            counts = publish_due_posts(now=NOW)

        self.assertEqual(counts["failed"], 1)
        graph_post.assert_not_called()
        scheduled.refresh_from_db()
        self.assertIn("expired", scheduled.error_message)

    def test_caption_is_capped_at_instagram_limits(self):
        post = ContentPost(
            body="x" * 3000,
        )

        caption = build_instagram_caption(post)

        self.assertLessEqual(len(caption), 2200)

    def test_caption_includes_at_most_30_hashtags(self):
        post = ContentPost(
            body="Short caption",
            hashtags=[f"tag{index}" for index in range(40)],
        )

        caption = build_instagram_caption(post)

        self.assertEqual(caption.count("#"), 30)


class InstagramSchedulingTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(owner_id=self.user.id, name="Brand")
        self.post = ContentPost.objects.create(
            brand=self.brand,
            title="Caption",
            body="Hello",
            platform=ContentPost.Platform.INSTAGRAM,
            status=ContentPost.Status.APPROVED,
            image_url="https://cdn.example/post.jpg",
        )

    def schedule(self, **overrides):
        payload = {
            "post_id": str(self.post.id),
            "platforms": ["instagram"],
            "scheduled_for": "2030-01-15T09:30:00+00:00",
            "timezone_name": "UTC",
        }
        payload.update(overrides)
        return self.client.post(
            "/api/calendar/scheduled-posts/create/", payload, format="json"
        )

    def create_account(self, owner_id=None, account_id=IG_ID, name="IG"):
        return SocialAccount.objects.create(
            owner_id=owner_id or self.user.id,
            platform=SocialAccount.Platform.INSTAGRAM,
            platform_account_id=account_id,
            display_name=name,
            access_token_encrypted=encrypt_social_token(TOKEN),
        )

    @social_settings()
    def test_single_account_is_selected_automatically(self):
        account = self.create_account()

        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = ScheduledPost.objects.get(post=self.post)
        self.assertEqual(scheduled.social_account_id, account.id)
        self.assertEqual(
            response.data[0]["social_account"]["display_name"], "IG"
        )

    @social_settings()
    def test_requires_a_connected_account(self):
        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(
            response.data["code"], "instagram_account_not_connected"
        )

    @social_settings()
    def test_multiple_accounts_require_a_choice(self):
        self.create_account(account_id="111")
        second = self.create_account(account_id="222", name="Second")

        ambiguous = self.schedule()
        self.assertEqual(ambiguous.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(ambiguous.data["code"], "instagram_account_required")

        chosen = self.schedule(social_account_id=str(second.id))
        self.assertEqual(chosen.status_code, status.HTTP_201_CREATED)
        self.assertEqual(
            ScheduledPost.objects.get(post=self.post).social_account_id,
            second.id,
        )

    @social_settings()
    def test_requires_a_public_image_before_scheduling(self):
        self.create_account()
        self.post.image_url = ""
        self.post.save(update_fields=["image_url"])

        response = self.schedule()

        self.assertEqual(response.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(response.data["code"], "instagram_image_required")
        self.assertFalse(ScheduledPost.objects.filter(post=self.post).exists())

    @social_settings()
    def test_separate_accounts_can_be_selected_for_facebook_and_instagram(self):
        instagram_account = self.create_account()
        facebook_account = SocialAccount.objects.create(
            owner_id=self.user.id,
            platform=SocialAccount.Platform.FACEBOOK_PAGES,
            platform_account_id="page-1",
            display_name="Page",
            access_token_encrypted=encrypt_social_token(TOKEN),
        )

        response = self.schedule(
            platforms=["facebook", "instagram"],
            social_account_ids={
                "facebook": str(facebook_account.id),
                "instagram": str(instagram_account.id),
            },
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        scheduled = {
            item.platform: item
            for item in ScheduledPost.objects.filter(post=self.post)
        }
        self.assertEqual(
            scheduled["facebook"].social_account_id, facebook_account.id
        )
        self.assertEqual(
            scheduled["instagram"].social_account_id, instagram_account.id
        )

    @social_settings()
    def test_cannot_schedule_to_another_users_account(self):
        foreign = self.create_account(owner_id=uuid4(), account_id="333")

        response = self.schedule(social_account_id=str(foreign.id))

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        self.assertEqual(
            response.data["code"], "instagram_account_not_found"
        )


@social_settings()
class ContentImageUploadTests(APITestCase):
    def setUp(self):
        self.user = SimpleNamespace(id=uuid4(), is_authenticated=True)
        self.client.force_authenticate(user=self.user)
        self.brand = Brand.objects.create(owner_id=self.user.id, name="Brand")
        self.post = ContentPost.objects.create(
            brand=self.brand,
            title="Caption",
            body="Hello",
            platform=ContentPost.Platform.INSTAGRAM,
            status=ContentPost.Status.DRAFT,
        )

    def upload(self, content=JPEG_BYTES, content_type="image/jpeg", name="post.jpg"):
        return self.client.post(
            f"/api/content/posts/{self.post.id}/image/",
            {"image": SimpleUploadedFile(name, content, content_type=content_type)},
            format="multipart",
        )

    @patch("core.services.media_storage.requests.post")
    def test_upload_stores_a_public_url(self, storage_post):
        storage_post.return_value = graph_response(200, {"Key": "stored"})

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.post.refresh_from_db()
        self.assertTrue(
            self.post.image_url.startswith(
                "https://supabase.example.invalid/storage/v1/object/public/"
                "content-media/posts/"
            )
        )
        self.assertTrue(self.post.image_url.endswith(".jpg"))
        self.assertNotIn("service-role-test-key", str(response.data))
        url = storage_post.call_args.args[0]
        self.assertIn("/storage/v1/object/content-media/posts/", url)
        self.assertEqual(
            storage_post.call_args.kwargs["headers"]["Content-Type"],
            "image/jpeg",
        )

    @patch("core.services.media_storage.requests.post")
    def test_non_jpeg_uploads_are_rejected(self, storage_post):
        response = self.upload(content=b"\x89PNG\r\n", content_type="image/png")

        self.assertEqual(response.status_code, status.HTTP_415_UNSUPPORTED_MEDIA_TYPE)
        storage_post.assert_not_called()

    @patch("core.services.media_storage.requests.post")
    def test_oversized_images_are_rejected(self, storage_post):
        response = self.upload(content=JPEG_BYTES + b"0" * (8 * 1024 * 1024))

        self.assertEqual(response.status_code, status.HTTP_413_REQUEST_ENTITY_TOO_LARGE)
        storage_post.assert_not_called()

    def test_upload_reports_missing_storage_configuration(self):
        with override_settings(SUPABASE_SERVICE_ROLE_KEY=""):
            response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("not configured", response.data["detail"])

    def test_upload_requires_an_explicitly_configured_bucket(self):
        with override_settings(SUPABASE_STORAGE_BUCKET=""):
            with patch("core.services.media_storage.requests.post") as storage_post:
                response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_503_SERVICE_UNAVAILABLE)
        self.assertIn("SUPABASE_STORAGE_BUCKET", response.data["detail"])
        storage_post.assert_not_called()

    @patch("core.services.media_storage.requests.post")
    def test_other_owners_cannot_attach_images(self, storage_post):
        self.post.brand = Brand.objects.create(owner_id=uuid4(), name="Other")
        self.post.save(update_fields=["brand"])

        response = self.upload()

        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
        storage_post.assert_not_called()
