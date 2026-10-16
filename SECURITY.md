# Security policy

This independent downstream maintains only its latest reviewed stable-base release candidate. See `downstream/UPSTREAM.json`; old release candidates are not security-maintained. Owner: @i-am-an-op. No response-time SLA is promised.

Use GitHub private vulnerability reporting when enabled. Do not publish router configuration, credentials or exploit details in public issues. Upstream issues should follow MetaCubeX's own reporting policy; this fork does not act on behalf of that project.

Maintainer triage: reproduce with synthetic data, identify affected upstream/downstream versions and reachable configurations, prepare a minimal fix and regression, run CI and the DNS integration acceptance suite, review compatibility/rollback, then issue a new immutable release and advisory. Retire the downstream change when an official release satisfies the same tests.
