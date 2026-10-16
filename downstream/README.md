# Maintained DNS downstream

Owner: **i-am-an-op**. Upstream: MetaCubeX/mihomo. This is an independent downstream, not an official MetaCubeX release. GPL-3.0 licensing and upstream notices are retained. No router addresses, subscription URLs, passwords or household configuration belong in this repository.

The default upstream wire-answer cache can reuse responses across different checking flags and serve expired positive/negative answers. Set `dns.disable-cache: true` to bypass the resolver's answer cache, singleflight sharing and its cache-refresh retries. The default remains false. Main, direct, proxy-node and default/bootstrap resolvers created by `NewResolver` inherit the option. The programmatic `NewResolverFromClient` constructor retains its upstream default; callers of that API are outside this feature's configuration contract.

This delegates forwarded-answer caching to a separately configured resolver. It does not implement DNSSEC, change upstream selection, remove Fake-IP mappings, or make synthesized Fake-IP answers authoritative. Use only with a properly configured caching/validating upstream. Costs include more loopback requests and potentially more bootstrap queries. The DNS design uses official CoreDNS and distribution Unbound; no mosdns fork is needed.

## Development and review

`downstream/UPSTREAM.json` records the stable base, full revision and toolchain. The public feature and dependency updates are separate commits. `dns-maintained` accepts reviewed pull requests; force-push and deletion are prohibited after bootstrap. The initial implementation is AI-assisted and still needs the owner's production review. CI is evidence, not independent human approval.

Use official Go 1.26.9. `go mod download && go mod verify` checks the dependency lock; Go's checksum database remains enabled. Run `SKIP_INTEROP_TEST=1 go test -tags with_gvisor -timeout 5m ./...`, then `go test -race -tags with_gvisor ./dns ./config ./hub/executor`. The inherited interop exclusion matches upstream CI. Native amd64 and arm64 jobs build the real executable and run ten protocol regressions for LRU/ARC, CD/DO isolation, concurrent flags, and positive/negative expiry. Unit tests also cover AD/EDNS preservation, zero TTL, option propagation, cancellation and the unchanged default.

`python3 downstream/package.py` builds twice with CGO disabled, gVisor retained, fixed source time, no host paths/VCS injection and an empty build ID. It compares bytes and emits SHA256, source archive, module inventory and build metadata. This is a same-runner reproducibility check, not an independent reproducible-build certification. The CycloneDX 1.6 inventory describes Go modules, including modules not linked into this binary; it is not a complete OS/standard-library SBOM.

## Upstream maintenance

The daily `upstream-sync.yml` job and manual dispatch check the latest stable upstream release. A new stable release is merged onto a candidate branch, preserving downstream changes, and produces an owner-review link in the job summary. The owner opens its promotion PR. It does not execute upstream code in its write-privileged job, activate upstream workflows, auto-merge, publish a release or touch routers. Conflicts fail visibly for manual resolution. CI is explicitly dispatched for token-created branches. Workflow PR-approval rights remain disabled; only explicitly allowlisted pinned Actions run. Alpha changes are not automatically adopted; urgent upstream security commits can be cherry-picked in a separately reviewed PR.

Dependabot proposes weekly Go/Action updates. `govulncheck` is pinned and scans reachable code against the current official database; a failed scan blocks CI. It does not prove absence of vulnerabilities. Review findings before changing the baseline; do not silently suppress them. Check Actions notifications weekly and after upstream security advisories. Scheduled Actions can be delayed, disabled on forks, or disabled after repository inactivity: the owner must monitor them. If maintenance stops, freeze promotion and return to an accepted official architecture/release; do not keep claiming current upstream coverage.

## Release and rollback

Only manual `downstream-release.yml` on the protected default branch creates a **draft prerelease**, after successful CI on that exact commit. Native binaries are retested and GitHub build attestations are generated. The version and `-v` output identify the upstream base, downstream release and source revision. Publishing a production release requires owner review of behavior, vulnerabilities, full DNS integration, ARM router canary, reboot and rollback tests. Never mark a draft as production-ready merely because host/CI tests passed.

Verify `SHA256SUMS-*`, then `gh attestation verify mihomo-linux-arm64 --repo i-am-an-op/mihomo`; inspect the expected workflow and source commit in the verification output. Download the matching source archive/lock files and retain the previous accepted binary and configurations. Never replace published assets in place. OpenClash auto core updates must not replace this binary while `disable-cache` is required; official releases ignore unknown configuration keys, so a version/hash/behavior gate is essential. Official upgrade is preferred once the regression suite passes with equivalent supported behavior.

There is no perpetual service guarantee or claim of SSDF/SLSA certification. The process applies source protection, review/test, integrity/provenance, dependency tracking and vulnerability-response practices from NIST SP 800-218 SSDF 1.1 and SLSA 1.2. Independent audit, a second human reviewer, router-specific acceptance and ongoing owner response are not supplied by workflow files.

References: [SSDF 1.1](https://csrc.nist.gov/pubs/sp/800/218/final), [SLSA 1.2 build requirements](https://slsa.dev/spec/v1.2/build-requirements), [GitHub secure Actions](https://docs.github.com/en/actions/reference/security/secure-use), [Go vulnerability management](https://go.dev/doc/security/vuln/).
