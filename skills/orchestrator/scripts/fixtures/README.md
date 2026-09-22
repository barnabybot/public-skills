Capacity-meter JSON, trimmed to the fields `resolve.py` reads. This is the
shape a meter must produce, and not a recording of anyone's real allowance:
every figure here is invented.

`scarce/` is the same pair with `provider_a`'s long window pushed past the
threshold, which is what exercises the backup and the exit-3 path. Tests pin
`ROUTING_NOW` so hours-to-reset stay stable.

Both providers ship `codexbar: null` in `references/routing-metadata.yaml`, so
these fixtures are exercised only by the tests until you wire a real meter in.
