# Social account integrations

The connected-accounts API and encrypted account storage support separate
server-side Facebook Login for Business and Business Login for Instagram OAuth
flows. Facebook Page publishing and Instagram single-image feed publishing are
implemented. Instagram video, Reels, and carousel publishing are not enabled.
LinkedIn and TikTok remain unavailable until their provider integrations are
implemented and reviewed.

Keep all provider credentials in the backend environment only:

- `SOCIAL_TOKEN_ENCRYPTION_KEY`: Fernet key used to encrypt access/refresh
  tokens before database storage. Generate one with
  `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.
- `SOCIAL_INSTAGRAM_CLIENT_ID`, `SOCIAL_INSTAGRAM_CLIENT_SECRET`,
  `SOCIAL_INSTAGRAM_REDIRECT_URI`, and `SOCIAL_INSTAGRAM_API_VERSION`.
  These are the Instagram App ID, App Secret, exact registered HTTPS callback,
  and Graph API version from the Instagram Login setup. Keep the App Secret
  server-side.
- `SOCIAL_FACEBOOK_CLIENT_ID`: IBDA Meta App ID.
- `SOCIAL_FACEBOOK_CLIENT_SECRET`: IBDA Meta App Secret; server-side only.
- `SOCIAL_FACEBOOK_CONFIG_ID`: Facebook Login for Business configuration
  using a User access token and `pages_show_list`.
- `SOCIAL_FACEBOOK_REDIRECT_URI`: registered HTTPS callback URI:
  `https://<public-backend-host>/api/social/oauth/facebook_pages/callback/`.
- `SOCIAL_FACEBOOK_GRAPH_API_VERSION`: Graph API version in `vNN.N` format.
- `SOCIAL_LINKEDIN_CLIENT_ID`, `SOCIAL_LINKEDIN_CLIENT_SECRET`,
  `SOCIAL_LINKEDIN_REDIRECT_URI`
- `SOCIAL_TIKTOK_CLIENT_ID`, `SOCIAL_TIKTOK_CLIENT_SECRET`,
  `SOCIAL_TIKTOK_REDIRECT_URI`
- `SUPABASE_STORAGE_BUCKET`: explicitly set to the existing public media bucket
  name. There is intentionally no default bucket.
- `SUPABASE_SERVICE_ROLE_KEY`: server-only Supabase key used by the backend to
  upload media. Never put it in the mobile app or expose it to clients.

## Instagram Login and image publishing

Configure the Meta app's Instagram product using **API setup with Instagram
Login** and **Business Login**. Set its OAuth redirect URI to the exact value
of `SOCIAL_INSTAGRAM_REDIRECT_URI`, including the trailing slash:

`https://<public-backend-host>/api/social/oauth/instagram/callback/`

The backend uses the Instagram App ID and App Secret, requests
`instagram_business_basic` and `instagram_business_content_publish`, and
disables the Facebook Login option in the Instagram authorization window.
Instagram Login is a separate flow from Facebook Login for Business; it does
not use the Facebook `config_id`. Use a Business or Creator Instagram
professional account. Standard Access is for accounts you own or manage and
have added to the app; Advanced Access and app review are needed for other
businesses.

Instagram feed publishing accepts one JPEG image up to 8 MB and a caption.
Videos, Reels, and carousels are not supported by this first version. The
backend stores uploaded images in Supabase Storage and passes Instagram a
public HTTPS object URL so Meta can fetch the image. Images in this bucket are
publicly readable; do not upload private or sensitive media.

### Required Supabase Storage bucket

Bucket existence and access settings could not be conclusively verified with
the available project access. The API bucket listing returned no visible
buckets, but that does not prove that no bucket exists. Check the Supabase
Dashboard for the project matching the backend's `SUPABASE_URL` before
creating one. If no suitable bucket exists, create and configure it as follows:

1. In the Supabase Dashboard, select that project, open **Storage**, and
   choose **New bucket**.
2. Name the bucket `content-media` and enable **Public bucket** so Instagram
   can fetch uploaded images.
3. Set the file size limit to **8 MB** and allowed MIME type to **image/jpeg**.
4. Create the bucket. Do not add a public upload/write policy; uploads go
   through the authenticated backend using its server-only service-role key.
5. In the backend's private runtime environment, set
   `SUPABASE_STORAGE_BUCKET=content-media` and configure
   `SUPABASE_SERVICE_ROLE_KEY`. Keep both out of the mobile environment and
   client bundles.
6. Confirm the bucket appears as public in **Storage** before enabling
   Instagram publishing. The application does not assume a default bucket.

For Facebook Pages, configure the Meta app with Facebook Login for Business and
select the User access token type and `pages_show_list` permission. This
integration uses the configuration ID from `SOCIAL_FACEBOOK_CONFIG_ID` and
requests the authorization-code response. App Review/Advanced Access and
business verification may be required to serve businesses that IBDA does not
own or manage. The Pages API `/me/accounts` edge is used to discover only the
Pages authorized by the connecting Meta user.

The exact Facebook callback URI must be registered with Meta and supplied as
`SOCIAL_FACEBOOK_REDIRECT_URI`. Use the current public backend host and ensure
it is also allowed by Django's `DJANGO_ALLOWED_HOSTS`. Update both values when
the public backend host changes; do not hardcode a temporary tunnel host.

Each connect endpoint stores only a hash of a random, expiring, single-use
OAuth state, bound to the initiating IBDA user and provider. The public
Facebook callback consumes that state atomically, exchanges the authorization
code server-side, fetches Page IDs, names, and Page access tokens, and saves
each Page under the bound IBDA user. The Instagram callback exchanges the
authorization code, verifies the granted permissions and professional
account, and stores the Instagram account under the same owner. Both providers'
tokens are encrypted with `SOCIAL_TOKEN_ENCRYPTION_KEY`. Native clients receive
a redirect to the fixed `ibda://social-accounts` route with status only. Web
clients open a popup synchronously from the user's click, then navigate it to
the returned `authorization_url`; after the backend callback completes, it
posts status only to that popup's opener and closes the popup. Neither callback
mode returns provider codes or tokens to the client. Apply database migrations
before using the updated connect endpoints.

Never put credentials, encryption keys, authorization codes, or tokens in the
mobile app, source control, or logs. Do not use a shared system-user token as
a substitute for each customer's authorization.

## Scheduled Facebook Page publishing

Each Facebook schedule stores the connected Page it targets
(`ScheduledPost.social_account`). A single connected Page is selected
automatically; when the owner has several, the client must send
`social_account_id`. The publisher decrypts that Page's token in memory and
posts the content body plus hashtags to
`POST https://graph.facebook.com/<version>/<page-id>/feed` with the token in
the request body, never in a URL. The returned post ID is stored as
`external_post_id` and the schedule becomes `published`.

Publishing requires the worker to be running; saving a schedule only queues
it. Run one long-lived worker per deployment (it is safe to run several):

```
cd backend
.venv\Scripts\Activate.ps1
python manage.py process_scheduled_posts --loop --interval 60
```

On Windows, `backend\scripts\run-scheduler.bat` starts the same worker. The
worker polls every 60 seconds, claims due rows with
`SELECT ... FOR UPDATE SKIP LOCKED`, recovers rows stuck in `publishing` for
more than 15 minutes, and retries transient Graph API failures up to three
times with a 5/10-minute backoff. Permanent failures (invalid or expired
tokens, missing permissions, malformed requests) and missing Page links are
not retried forever: they end in `failed` or `blocked` with a stored
error message. Facebook `pages_manage_posts`, `pages_show_list`,
`pages_read_engagement` and `business_management` permissions plus a valid
Page token are required.

## Scheduled Instagram feed publishing

Each Instagram schedule targets one connected Instagram professional account.
When the owner has multiple accounts, the client selects the target account.
Scheduling requires an approved post with a public HTTPS JPEG image; Instagram
fetches that image from Supabase Storage, creates a media container, and
publishes it after the container is ready. The returned media ID is saved as
`external_post_id`. Start the scheduled-post worker described above to publish
due posts. Do not schedule a real post until the account owner has reviewed and
approved the content.

The Django development-server access log redacts query strings for both OAuth
callbacks. Configure any production reverse proxy, WSGI server, APM, and
centralized access-log pipeline not to retain OAuth callback or token-exchange
query parameters; those systems are outside Django's logging filter.
