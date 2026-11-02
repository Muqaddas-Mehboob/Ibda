# Subscription payments

The backend uses provider-neutral `UserSubscription`, `PaymentTransaction`,
and `ProviderWebhookEvent` records. Stripe is implemented as a server-side
test-mode checkout and webhook adapter. Subscription entitlements are granted
only after a verified Stripe subscription event; opening a checkout URL or
receiving `checkout.session.completed` does not activate a plan.

## Plan catalog and configuration

The server allowlists `starter`, `pro`, and `enterprise` with `monthly` and
`annual` billing intervals. Checkout resolves the Stripe Price ID on the
server. It ignores client-supplied Price IDs and redirect URLs.

Add these values to the backend `.env` for Stripe test mode:

- `STRIPE_SECRET_KEY`
- `STRIPE_WEBHOOK_SECRET`
- `STRIPE_CHECKOUT_SUCCESS_URL_WEB`
- `STRIPE_CHECKOUT_CANCEL_URL_WEB`
- `STRIPE_CHECKOUT_SUCCESS_URL_MOBILE`
- `STRIPE_CHECKOUT_CANCEL_URL_MOBILE`
- `STRIPE_PRICE_STARTER_MONTHLY`
- `STRIPE_PRICE_STARTER_ANNUAL`
- `STRIPE_PRICE_PRO_MONTHLY`
- `STRIPE_PRICE_PRO_ANNUAL`
- `STRIPE_PRICE_ENTERPRISE_MONTHLY`
- `STRIPE_PRICE_ENTERPRISE_ANNUAL`

For compatibility, the annual Price ID settings also accept their legacy
`*_YEARLY` environment-variable spelling. The Pro settings fall back to the
existing `PAYMENT_PRODUCT_PREMIUM_MONTHLY` and
`PAYMENT_PRODUCT_PREMIUM_ANNUAL` identifiers.

The plans API retrieves configured Stripe Price amounts and currencies from
Stripe. An unset, inactive, or unavailable Price is not offered for checkout.
The repository does not define the Starter, Pro, or Enterprise feature lists;
the API reports those definitions as unconfigured rather than inventing them.
Configure Stripe Products and recurring Prices in the Stripe dashboard, then
copy each test Price ID into its matching backend setting. Do not put secret
keys, webhook secrets, or credentials in the mobile app or source control.

Configure fixed web and mobile return URLs on the backend. For web, use the
deployed app origin and the Expo Router routes `/subscription/success` and
`/subscription/cancel` (for example,
`https://<your-web-host>/subscription/success`). For mobile, the Expo
configuration declares the `ibda` scheme; use
`ibda://subscription/success` for success and the success route for the
auth-session callback on cancellation (`ibda://subscription/success`). The
backend adds `checkout=success` or `checkout=cancelled` and adds
`session_id={CHECKOUT_SESSION_ID}` to success URLs. It preserves Stripe's
placeholder literally. Verify these URLs against the routes and scheme in
`mobile/app.json` before deploying. `STRIPE_CHECKOUT_SUCCESS_URL` and
`STRIPE_CHECKOUT_CANCEL_URL` remain web-only fallbacks when they point to the documented web routes; mobile
checkout requires the mobile-specific values.

The app sends only its platform (`web` or `mobile`) when starting checkout.
The backend selects a fixed configured URL; client-supplied redirect URLs are
never accepted. A successful redirect is not proof of payment. The authenticated
`GET /api/subscription/checkout/verify/?session_id=...` endpoint retrieves the
session with the server-side Stripe key and checks its owner, local
subscription, customer, plan, and billing interval. It reports success only
when payment and webhook-backed subscription records confirm it. If Stripe
webhooks are delayed, the app polls for a limited time and allows a retry.

For Expo Web, add the exact app origin (for example,
`http://localhost:8081`) to `CORS_ALLOWED_ORIGINS`. The API also allows the
`Idempotency-Key` request header used by checkout; do not enable all origins.

## Local Stripe CLI test

1. Install and authenticate the Stripe CLI against a Stripe test account.
2. Configure all required test-mode values above in `backend/.env`, including
   the recurring Price IDs and fixed success/cancellation URLs.
3. For a native app on a physical device, start Django from `backend` with
   `python manage.py runserver 0.0.0.0:8000` and include the development
   machine's LAN hostname or IP in `DJANGO_ALLOWED_HOSTS`. Expo native
   development resolves a loopback `EXPO_PUBLIC_API_URL` to the Expo host;
   production builds must use a reachable backend URL rather than loopback.
4. In a separate terminal, forward the supported events:

   ```text
   stripe listen --forward-to localhost:8000/api/payments/stripe/webhook/ --events checkout.session.completed,checkout.session.async_payment_succeeded,checkout.session.async_payment_failed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,invoice.paid,invoice.payment_failed
   ```

5. Copy the signing secret printed by `stripe listen` into the backend
   `STRIPE_WEBHOOK_SECRET`, restart Django, then start a checkout from the app.
   Complete it with a Stripe test card such as `4242 4242 4242 4242`, any
   future expiry date, and any CVC. Use only Stripe test mode; this test card
   does not charge real money.
6. Confirm the subscription and invoice events were delivered, then check
   `GET /api/subscription/me/` with the signed-in user's Supabase access token.

The CLI signing secret is local test configuration. Never commit it, paste it
into the mobile project, or share it. The Stripe webhook endpoint is
`POST /api/payments/stripe/webhook/`; it verifies Stripe's `Stripe-Signature`
header over the exact request body. The separate
`POST /api/payments/webhook/` endpoint retains the legacy provider-neutral
`X-Ibda-Signature` HMAC contract and is not a Stripe webhook endpoint.

## Implementation boundaries

- Checkout requires a valid Supabase-authenticated user, a server-configured
  plan Price ID, Stripe credentials, webhook signing secret, and fixed
  redirect URLs.
- A local pending record is created before Stripe checkout. An active
  subscription blocks another checkout; a same-plan retry reuses its pending
  local record.
- The checkout API accepts a UUID `Idempotency-Key` header. Clients should
  reuse the same key when retrying the same checkout request.
- Stripe customer, checkout session, and webhook failures do not activate
  entitlements. Stripe webhook deliveries are signature-verified,
  provider/event-ID deduplicated, and processed transactionally.
- `checkout.session.completed` and asynchronous checkout events associate the
  Stripe session with the local pending subscription, but never activate it.
  Verified subscription and invoice events remain the source of truth; unpaid
  or delayed payment sessions remain pending until Stripe confirms payment.
- `trialing` maps to the existing `active` status. `past_due` remains
  non-entitled under the current entitlement service; unpaid, incomplete,
  canceled, expired, and paused subscriptions do not receive active
  entitlements.
- Subscription lifecycle timestamps are compared to prevent older Stripe
  events from overwriting newer state.
- The Stripe adapter is isolated under `core/services/payments/`; provider
  credentials and integration details are not part of the mobile API.

Run the schema migration separately when ready:

```text
python manage.py migrate
```
