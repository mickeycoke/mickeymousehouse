"""Which environment is this process running in?

There is one gotcha this module exists to remove. Production is marked with
**`APP_ENV=production`** (set in `docker-compose.prod.yml`, and what
`main.py`'s `/api/health` reports), but three separate safety guards were
written against a differently-named `ENVIRONMENT` variable that the
deployment never sets:

  * `utils/tokens.py` — refuse to boot with the dev `JWT_SECRET`
  * `utils/crypto.py` — refuse to boot with the dev cloud-storage key
  * `routes/cloud_storage.py` — mark the OAuth nonce cookie `Secure`

So all three silently behaved as "development" ON PRODUCTION: the two
refuse-to-boot guards could never fire, and the cookie went out without
`Secure`.

`is_production()` accepts EITHER name, so a guard cannot be defeated again by
whichever spelling a compose file happens to use.
"""
import os

_PRODUCTION_VALUES = ("production", "prod")


def is_production() -> bool:
    """True if either `APP_ENV` or `ENVIRONMENT` marks this as production.

    Deliberately checks both: `APP_ENV` is what this repo's production compose
    file actually sets, `ENVIRONMENT` is what several guards were originally
    written against. Either one counts, so a mismatch fails SAFE (guard fires)
    rather than silently disabling a protection.
    """
    for var in ("APP_ENV", "ENVIRONMENT"):
        if os.getenv(var, "").strip().lower() in _PRODUCTION_VALUES:
            return True
    return False
