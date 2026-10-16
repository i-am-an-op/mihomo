Candidate for review; not deployed or approved for production.

- Add opt-in `dns.disable-cache` to delegate forwarded-answer caching and query isolation to an external resolver while retaining Fake-IP mapping and application routing.
- Update the inherited Go networking dependency set to patched versions and pin the supported official Go toolchain.
- Include native amd64/arm64 regressions, byte-comparison builds, source archives, checksums, module inventory and build attestations.

See `downstream/README.md` for scope, verification, maintenance and rollback. Full router canary, reboot, load and client IPv6 acceptance remain deployment gates. Existing upstream behavior remains the default unless `dns.disable-cache: true` is explicitly configured.
