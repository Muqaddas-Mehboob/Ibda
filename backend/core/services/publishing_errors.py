class PublishingError(Exception):
    """A publishing failure, classified as transient (retryable) or not."""

    def __init__(self, message, transient=True):
        self.transient = transient
        super().__init__(message)
