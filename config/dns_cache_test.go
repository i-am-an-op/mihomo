package config

import "testing"

func TestDNSDisableCacheParsing(t *testing.T) {
	for _, enabled := range []bool{false, true} {
		raw := DefaultRawConfig()
		raw.DNS.DisableCache = enabled
		cfg, err := parseDNS(raw, nil)
		if err != nil {
			t.Fatal(err)
		}
		if cfg.DisableCache != enabled {
			t.Fatal("disable-cache not propagated")
		}
	}
	raw, err := UnmarshalRawConfig([]byte("dns:\n  disable-cache: true\n"))
	if err != nil || !raw.DNS.DisableCache {
		t.Fatalf("YAML option lost: %v", err)
	}
}
