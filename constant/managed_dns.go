package constant

import "os"

// ManagedDNSFrontend is an opt-in downstream operational contract, not an
// upstream option. Identity verification must reject official binaries that
// do not implement this contract. Keep it off for a transport-only process.
func ManagedDNSFrontend() bool {
	return os.Getenv("MIHOMO_MANAGED_DNS") == "1"
}
