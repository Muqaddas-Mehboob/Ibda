# Subscription and payments foundation

The subscription API and database records are present, but no payment provider,
merchant account, product catalog, or mobile-store billing adapter is
configured. The app therefore displays no prices or billing intervals and
checkout/manage actions remain unavailable. No client request can grant paid
entitlements.

## Decide the billing integration first

Ibda offers digital features in iOS and Android apps. Before adding checkout,
choose a distribution and billing approach that complies with current Apple App
Store and Google Play billing requirements in the intended markets. For web
sales, choose a provider that supports the merchant's country and recurring
billing model. Configure provider products and test-mode credentials only on
the backend. Provider credentials, webhook secrets, and merchant keys must
never be included in the mobile app or source control.

Required backend environment settings once an adapter is implemented:

- `PAYMENT_PROVIDER`: identifier for the implemented provider adapter. Setting
  this alone does not enable checkout.
- `PAYMENT_WEBHOOK_SECRET`: server-side secret for the normalized webhook
  adapter contract below. Use a unique, high-entropy value.
- `PAYMENT_PRODUCT_PREMIUM_MONTHLY` and
  `PAYMENT_PRODUCT_PREMIUM_ANNUAL`: provider product identifiers; these are
  identifiers, not prices.
- `SUBSCRIPTION_ENTITLEMENT_LIMITS`: JSON keyed by `free` and `premium`, with
  integer limits or `null` for unlimited. For example:

  ```json
  {"free":{"saved_brands":2},"premium":{"saved_brands":null}}
  ```

No default limit is imposed. The saved-brand limit is enforced on brand
creation when configured. Do not configure limits for features until their
usage is measured reliably; generated-content usage is not currently tracked
as a billable usage event.

## Normalized webhook contract

`POST /api/payments/webhook/` accepts normalized events from a trusted
server-side provider adapter. It is not a direct Stripe, Apple, Google, or
other provider webhook implementation. That adapter must verify the actual
provider signature and map provider product identifiers and statuses to this
contract before sending events. The endpoint verifies
`X-Ibda-Signature`, a lowercase hexadecimal HMAC-SHA256 of the exact raw
request body using `PAYMENT_WEBHOOK_SECRET`, and deduplicates `event_id` by
provider.

The JSON body has `event_id`, `event_type`, `subscription_id`, and `status`.
`event_type` is `subscription.updated` or `transaction.updated`. Subscription
updates may include `plan_id`, `billing_interval`, `current_period_start`,
`current_period_end`, `cancel_at_period_end`, and `canceled_at`. Transaction
updates must include `transaction_id` and may include `amount_minor`,
three-letter uppercase `currency`, and `occurred_at`. These events are only
accepted for an existing provider subscription record. The adapter must create
that pending record through a future server-side checkout integration before
delivering subscription events.

## API

- `GET /api/subscription/plans/`: authenticated plan catalog; prices and
  intervals are unset until a provider integration is available.
- `GET /api/subscription/me/`: authenticated current subscription, configured
  entitlements, and up to 100 owner-scoped transactions.
- `POST /api/subscription/checkout/`: validates a plan identifier and returns
  `503` while checkout is unconfigured. It never changes subscription state.
- `POST /api/payments/webhook/`: signed normalized adapter events; not an
  authenticated mobile endpoint.

The backend currently has no external checkout, provider portal/cancellation,
provider-specific webhook verification, or Apple/Google purchase validation.
Those require the billing provider, merchant country, store distribution
requirements, product IDs, and credentials to be selected and configured.
