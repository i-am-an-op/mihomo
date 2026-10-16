package dns

import (
	"context"
	"errors"
	"testing"
	"time"

	"github.com/metacubex/http"
	C "github.com/metacubex/mihomo/constant"
)

// This adapter never opens a socket. It observes the context handed to the real
// HTTP transport's detached dial and waits for that context to expire.
type deadlineOnlyAdapter struct {
	C.ProxyAdapter
	entered chan context.Context
	ended   chan error
}

func (a *deadlineOnlyAdapter) Name() string                  { return "deadline-fixture" }
func (a *deadlineOnlyAdapter) Type() C.AdapterType           { return C.Direct }
func (a *deadlineOnlyAdapter) IsL3Protocol(*C.Metadata) bool { return false }

func (a *deadlineOnlyAdapter) DialContext(ctx context.Context, _ *C.Metadata) (C.Conn, error) {
	a.entered <- ctx
	<-ctx.Done()
	a.ended <- ctx.Err()
	return nil, ctx.Err()
}

func TestDoHAbandonedDialTerminates(t *testing.T) {
	a := &deadlineOnlyAdapter{
		entered: make(chan context.Context, 1), ended: make(chan error, 1),
	}
	d := newDoHClient("https://192.0.2.1/dns-query", nil, false, nil, a, "").(*dnsOverHTTPS)
	rt, err := d.createTransport(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	tr := rt.(*http.Transport)
	defer tr.CloseIdleConnections()
	if tr.TLSHandshakeTimeout <= 0 || tr.TLSHandshakeTimeout > dialTimeout {
		t.Fatalf("unbounded TLS handshake: %s", tr.TLSHandshakeTimeout)
	}
	requestCtx, cancel := context.WithCancel(context.Background())
	defer cancel()
	req, err := http.NewRequestWithContext(requestCtx, "POST", "https://192.0.2.1/dns-query", nil)
	if err != nil {
		t.Fatal(err)
	}
	finished := make(chan error, 1)
	go func() { _, err := tr.RoundTrip(req); finished <- err }()
	var dialCtx context.Context
	select {
	case dialCtx = <-a.entered:
	case <-time.After(time.Second):
		t.Fatal("dial did not enter fixture")
	}
	deadline, ok := dialCtx.Deadline()
	if !ok || time.Until(deadline) > dialTimeout {
		t.Fatal("detached DoH dial has no bounded deadline")
	}
	cancel()
	select {
	case err := <-finished:
		if !errors.Is(err, context.Canceled) {
			t.Fatalf("query cancellation: %v", err)
		}
	case <-time.After(time.Second):
		t.Fatal("abandoned query did not return")
	}
	select {
	case err := <-a.ended:
		if !errors.Is(err, context.DeadlineExceeded) {
			t.Fatalf("detached dial termination: %v", err)
		}
	case <-time.After(dialTimeout + 2*time.Second):
		t.Fatal("abandoned dial survived its timeout")
	}
}

func TestDoHDialPreservesEarlierCallerDeadline(t *testing.T) {
	a := &deadlineOnlyAdapter{
		entered: make(chan context.Context, 1), ended: make(chan error, 1),
	}
	d := newDoHClient("http://192.0.2.1/dns-query", nil, false, nil, a, "").(*dnsOverHTTPS)
	rt, err := d.createTransport(context.Background())
	if err != nil {
		t.Fatal(err)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 25*time.Millisecond)
	defer cancel()
	_, err = rt.(*http.Transport).DialContext(ctx, "tcp", "192.0.2.1:80")
	if !errors.Is(err, context.DeadlineExceeded) {
		t.Fatalf("earlier deadline lost: %v", err)
	}
	got := <-a.entered
	wantDeadline, _ := ctx.Deadline()
	gotDeadline, ok := got.Deadline()
	if !ok || !gotDeadline.Equal(wantDeadline) {
		t.Fatal("caller deadline replaced")
	}
}
