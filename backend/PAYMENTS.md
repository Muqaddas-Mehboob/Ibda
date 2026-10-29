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
- `STRIPE_CHECKOUT_SUCCESS_URL`
- `STRIPE_CHECKOUT_CANCEL_URL`
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

Configure fixed success and cancellation URLs on the backend. The success URL
may contain Stripe's `{CHECKOUT_SESSION_ID}` placeholder. Do not accept
redirect URLs from the app. A successful redirect is not proof of payment.

## Local Stripe CLI test

1. Install and authenticate the Stripe CLI against a Stripe test account.
2. Configure all required test-mode values above in `backend/.env`, including
   the recurring Price IDs and fixed success/cancellation URLs.
3. Start Django from `backend` with `python manage.py runserver`.
4. In a separate terminal, forward the supported events:

   ```text
   stripe listen --forward-to localhost:8000/api/payments/stripe/webhook/ --events checkout.session.completed,customer.subscription.created,customer.subscription.updated,customer.subscription.deleted,invoice.paid,invoice.payment_failed
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
