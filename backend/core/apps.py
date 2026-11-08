import logging
import re

from django.apps import AppConfig


class OAuthCallbackLogFilter(logging.Filter):
    callback_query = re.compile(
        r"(/api/social/oauth/(?:facebook_pages|instagram)/callback/)\?[^\s]*"
    )

    def filter(self, record):
        if record.name == "django.server":
            message = record.getMessage()
            redacted_message = self.callback_query.sub(
                r"\1?[redacted]",
                message,
            )
            if redacted_message != message:
                record.msg = redacted_message
                record.args = ()
        return True


class CoreConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'core'

    def ready(self):
        logging.getLogger("django.server").addFilter(
            OAuthCallbackLogFilter()
        )
        import core.signals  # noqa: F401
