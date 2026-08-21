import bcrypt


def hash_password(plain: str) -> str:
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(plain.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain: str, hashed: str) -> bool:
    return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))


def normalize_pin(pin: str) -> str:
    """Instructor PINs are matched case-insensitively — a PIN typed "ABcd" must
    accept the stored "abcd". Normalize at BOTH hash time and verify time
    (always through hash_pin/verify_pin below) so the two never drift; a
    lowercase-at-verify-only change would break any PIN hashed from an
    upper-case source."""
    return (pin or "").lower()


def hash_pin(pin: str) -> str:
    return hash_password(normalize_pin(pin))


def verify_pin(pin: str, hashed: str) -> bool:
    return verify_password(normalize_pin(pin), hashed)
