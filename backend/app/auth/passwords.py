from pwdlib import PasswordHash
from pwdlib.exceptions import UnknownHashError

password_hash = PasswordHash.recommended()
# Used when an email address is unknown so login performs comparable password work.
DUMMY_PASSWORD_HASH = password_hash.hash("not-a-real-user-password")


def hash_password(password: str) -> str:
    return password_hash.hash(password)


def verify_password(password: str, encoded_hash: str) -> bool:
    verified, _ = verify_and_update_password(password, encoded_hash)
    return verified


def verify_and_update_password(password: str, encoded_hash: str) -> tuple[bool, str | None]:
    try:
        return password_hash.verify_and_update(password, encoded_hash)
    except UnknownHashError:
        return False, None
