# Social account integrations

The connected-accounts API and encrypted account storage are present, but no
provider OAuth adapter is enabled. Instagram, Facebook Pages, LinkedIn, and
TikTok therefore remain unavailable and the API deliberately refuses to start
an authorization flow. Adding credentials alone does not enable a provider;
its OAuth exchange, account-identity lookup, token-refresh policy, scopes, and
platform app review must also be implemented and verified before advertising
the provider as configured.

Keep all provider credentials in the backend environment only:

- `SOCIAL_TOKEN_ENCRYPTION_KEY`: Fernet key used to encrypt access/refresh
  tokens before database storage. Generate one with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `SOCIAL_INSTAGRAM_CLIENT_ID`, `SOCIAL_INSTAGRAM_CLIENT_SECRET`,
  `SOCIAL_INSTAGRAM_REDIRECT_URI`
- `SOCIAL_FACEBOOK_CLIENT_ID`, `SOCIAL_FACEBOOK_CLIENT_SECRET`,
  `SOCIAL_FACEBOOK_REDIRECT_URI`
- `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`,
  `SOCIAL_LINKEDIN_REDIRECT_URI`
- `SOCIAL_TIKTOK_CLIENT_ID`, `SOCIAL_TIKTOK_CLIENT_SECRET`,
  `SOCIAL_TIKTOK_REDIRECT_URI`

Register each redirect URI with the corresponding provider developer
application. Meta account requirements, provider permissions, app review, and
business verification may apply. Never put these values or the encryption key
in the mobile app, source control, or logs.

The callback endpoint rejects requests when no OAuth flow is active. No
provider tokens or callback codes are accepted or returned by the current
implementation.
