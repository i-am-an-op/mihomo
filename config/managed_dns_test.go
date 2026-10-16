package config

import "testing"

func TestManagedDNSFrontendRequiresDelegation(t *testing.T) {
	t.Setenv("MIHOMO_MANAGED_DNS", "1")
	for _, config := range []string{"dns: {enable: true}", "dns: {enable: true, disable-cache: false}", "dns: {enable: false, disable-cache: true}"} {
		if _, err := UnmarshalRawConfig([]byte(config)); err == nil {
			t.Fatal("accepted configuration that loses the required frontend behavior")
		}
	}
	if _, err := UnmarshalRawConfig([]byte("dns: {enable: true, disable-cache: true}")); err != nil {
		t.Fatal(err)
	}
}

func TestUnmanagedDNSFrontendRetainsDefault(t *testing.T) {
	t.Setenv("MIHOMO_MANAGED_DNS", "")
	cfg, err := UnmarshalRawConfig([]byte("dns: {enable: true}"))
	if err != nil || cfg.DNS.DisableCache {
		t.Fatal("unmanaged default changed", err)
	}
}
