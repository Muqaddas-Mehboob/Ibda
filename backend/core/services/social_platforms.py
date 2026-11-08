from ..models import ContentPost, SocialAccount
from .facebook_publishing import (
    facebook_publishing_configuration_error,
    facebook_publishing_configured,
)
from .instagram_publishing import (
    instagram_publishing_configuration_error,
    instagram_publishing_configured,
)


SOCIAL_PROVIDERS = (
    {
        "platform": SocialAccount.Platform.INSTAGRAM,
        "name": "Instagram",
        "reason": "Instagram OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.FACEBOOK_PAGES,
        "name": "Facebook Pages",
        "reason": "Facebook OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.LINKEDIN,
        "name": "LinkedIn",
        "reason": "LinkedIn OAuth is not configured for this deployment.",
    },
    {
        "platform": SocialAccount.Platform.TIKTOK,
        "name": "TikTok",
        "reason": "TikTok OAuth is not configured for this deployment.",
    },
)

SCHEDULING_PLATFORM_LABELS = {
    ContentPost.Platform.INSTAGRAM: "Instagram",
    ContentPost.Platform.FACEBOOK: "Facebook",
    ContentPost.Platform.LINKEDIN: "LinkedIn",
    ContentPost.Platform.TIKTOK: "TikTok",
    ContentPost.Platform.X: "X",
    ContentPost.Platform.OTHER: "Other",
}

# A platform may only flip to True once a real publisher (API credentials,
# permissions and a verified publishing call) exists for it. Reporting a post
# as published without that confirmation would be false, so every platform is
# explicitly unavailable until then. Facebook's availability is computed from
# the server-side publishing configuration below.
PUBLISHING_AVAILABILITY = {
    ContentPost.Platform.INSTAGRAM: False,
    ContentPost.Platform.FACEBOOK: False,
    ContentPost.Platform.LINKEDIN: False,
    ContentPost.Platform.TIKTOK: False,
    ContentPost.Platform.X: False,
    ContentPost.Platform.OTHER: False,
}

_NO_INTEGRATION_REASON = (
    "No {platform} publishing integration is configured for this deployment. "
    "The post can be scheduled and managed, but it cannot be published yet."
)


def publishing_available(platform):
    if platform == ContentPost.Platform.FACEBOOK:
        return facebook_publishing_configured()
    if platform == ContentPost.Platform.INSTAGRAM:
        return instagram_publishing_configured()
    return bool(PUBLISHING_AVAILABILITY.get(platform, False))


def publishing_unavailable_reason(platform):
    if platform == ContentPost.Platform.FACEBOOK:
        configuration_error = facebook_publishing_configuration_error()
        if configuration_error:
            return configuration_error
    if platform == ContentPost.Platform.INSTAGRAM:
        configuration_error = instagram_publishing_configuration_error()
        if configuration_error:
            return configuration_error
    label = SCHEDULING_PLATFORM_LABELS.get(platform, platform)
    return _NO_INTEGRATION_REASON.format(platform=label)


def get_publishing_capabilities():
    return [
        {
            "platform": platform,
            "label": SCHEDULING_PLATFORM_LABELS[platform],
            "available": publishing_available(platform),
            "reason": (
                "" if publishing_available(platform)
                else publishing_unavailable_reason(platform)
            ),
        }
        for platform in SCHEDULING_PLATFORM_LABELS
    ]
