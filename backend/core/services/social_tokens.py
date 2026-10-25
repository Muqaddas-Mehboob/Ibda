from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings


class SocialTokenEncryptionError(ValueError):
    pass


def _cipher():
    key = settings.SOCIAL_TOKEN_ENCRYPTION_KEY
    if not key:
        raise SocialTokenEncryptionError(
            "SOCIAL_TOKEN_ENCRYPTION_KEY is not configured."
        )
    try:
        return Fernet(key.encode("ascii"))
    except (UnicodeEncodeError, ValueError) as error:
        raise SocialTokenEncryptionError(
            "SOCIAL_TOKEN_ENCRYPTION_KEY must be a valid Fernet key."
        ) from error


def encrypt_social_token(token):
    if not token:
        return ""
    return _cipher().encrypt(token.encode("utf-8")).decode("ascii")


def decrypt_social_token(ciphertext):
    if not ciphertext:
        return ""
    try:
        return _cipher().decrypt(ciphertext.encode("ascii")).decode("utf-8")
    except (InvalidToken, UnicodeEncodeError, UnicodeDecodeError) as error:
        raise SocialTokenEncryptionError(
            "Stored social token could not be decrypted."
        ) from error
