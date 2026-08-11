"""Results-row schema: versioning, per-sample identity, and sampling seeds.

A generation row used to be identified by its item id alone. Multi-sampling makes the identity
(id, sample), and every row now carries `schema_version` so a reader knows what to expect.

v1 rows (everything currently on both boxes) have neither field. They are defined as "sample 0
of an otherwise-v2 row" rather than handled by a separate code path, so grading a v1 file gives
the same numbers it always did.

WHY SEEDS ARE MANDATORY, not a nicety (measured against the live server, 2026-08-11): with no
`seed` in the request, three draws of the same prompt at temperature 0.8 came back BYTE-IDENTICAL.
The serving path keys its sampler deterministically per request (`DEFAULT_SEED = 0`), and the
suffix-decoding path shipped on both winners keys off `(seed, row_id, position)`. So k samples
WITHOUT distinct seeds are k copies of one generation: pass^k would collapse to pass@1 and
reliability would report perfect stability while measuring nothing. Passing an explicit
per-(item, sample) seed both fixes that and makes the draws reproducible, which is what lets a
resume be distinguished from a re-draw.
"""
import hashlib

SCHEMA_VERSION = 2


def migrate(row: dict) -> dict:
    """A v2 view of `row`. Returns a NEW dict (never edits the caller's row): grading iterates
    rows read from disk, and mutating them in place would make a second pass see different data."""
    out = dict(row)
    out.setdefault("sample", 0)
    out.setdefault("schema_version", SCHEMA_VERSION)
    return out


def key(item_id, sample: int = 0) -> tuple:
    return (item_id, int(sample))


def row_key(row: dict) -> tuple:
    """The row's (id, sample) identity. A v1 row (no `sample`) is sample 0."""
    return key(row.get("id"), row.get("sample", 0))


def display_key(row: dict) -> str:
    """Human-facing form, e.g. `Mbpp/610#2`. For logs and reports only — never for lookups
    (an item id containing '#' would be ambiguous)."""
    k = row_key(row)
    return f"{k[0]}#{k[1]}"


def sample_seed(item_id, sample: int = 0, base: int = 0) -> int:
    """A stable PRNG seed for one (item, sample) draw.

    Derived with blake2b, NOT Python's `hash()`: string hashing is salted per process
    (PYTHONHASHSEED), so `hash()` would give a resumed run different seeds than the original —
    silently re-drawing instead of reproducing, and making a partial file's provenance a lie.

    Depends only on (item, sample, base) — deliberately NOT on queue position, so changing
    `--limit` or the ordering does not change which draws you get. It is also identical across
    models, so every model draws sample s of item i under the same seed: the paired /
    common-random-numbers choice, which removes one nuisance source from cross-model comparison.

    Returns a positive 31-bit int (every layer down to mlx accepts that range).
    """
    h = hashlib.blake2b(f"{base}\x00{item_id}\x00{int(sample)}".encode(), digest_size=4)
    return int.from_bytes(h.digest(), "big") & 0x7FFFFFFF
