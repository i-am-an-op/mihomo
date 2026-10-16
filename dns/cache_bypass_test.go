package dns

import (
	"context"
	"fmt"
	"sync/atomic"
	"testing"
	"time"

	D "github.com/miekg/dns"
)

type bypassFixture struct {
	calls atomic.Int32
	reply func(context.Context, *D.Msg) (*D.Msg, error)
}

func (f *bypassFixture) Address() string  { return "fixture" }
func (f *bypassFixture) ResetConnection() {}
func (f *bypassFixture) ExchangeContext(ctx context.Context, q *D.Msg) (*D.Msg, error) {
	f.calls.Add(1)
	return f.reply(ctx, q)
}

func TestDisableCachePreservesQueriesAndFreshAnswers(t *testing.T) {
	for _, kind := range []uint16{D.TypeA, D.TypeAAAA, D.TypeTXT, D.TypeCAA} {
		t.Run(D.TypeToString[kind], func(t *testing.T) {
			var expected *D.Msg
			f := &bypassFixture{reply: func(_ context.Context, q *D.Msg) (*D.Msg, error) {
				if q.String() != expected.String() {
					t.Error("request semantics changed")
				}
				r := new(D.Msg).SetReply(q)
				r.Ns = []D.RR{&D.SOA{Hdr: D.RR_Header{Name: q.Question[0].Name, Rrtype: D.TypeSOA, Class: D.ClassINET, Ttl: 0}, Minttl: 0}}
				return r, nil
			}}
			r := &Resolver{disableCache: true, main: []dnsClient{f}, cache: Config{}.newCache()}
			for flags := 0; flags < 8; flags++ {
				q := new(D.Msg).SetQuestion("flags.example.", kind)
				q.CheckingDisabled = flags&1 != 0
				q.AuthenticatedData = flags&2 != 0
				q.SetEdns0(1232, flags&4 != 0)
				q.IsEdns0().Option = append(q.IsEdns0().Option, &D.EDNS0_LOCAL{Code: 65001, Data: []byte{byte(flags)}})
				expected = q.Copy()
				got, err := r.ExchangeContext(context.Background(), q)
				if err != nil {
					t.Fatal(err)
				}
				if got.Ns[0].Header().Ttl != 0 {
					t.Fatal("zero TTL inflated")
				}
			}
			if f.calls.Load() != 8 {
				t.Fatalf("forwarded %d of 8 distinct requests", f.calls.Load())
			}
		})
	}
}

func TestDisableCacheDoesNotShareInflightFlags(t *testing.T) {
	entered := make(chan bool, 2)
	release := make(chan struct{})
	f := &bypassFixture{reply: func(ctx context.Context, q *D.Msg) (*D.Msg, error) {
		entered <- q.CheckingDisabled
		select {
		case <-release:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
		return new(D.Msg).SetReply(q), nil
	}}
	r := &Resolver{disableCache: true, main: []dnsClient{f}, cache: Config{}.newCache()}
	ctx, cancel := context.WithTimeout(context.Background(), time.Second)
	defer cancel()
	errs := make(chan error, 2)
	for _, cd := range []bool{true, false} {
		q := new(D.Msg).SetQuestion("same.example.", D.TypeA)
		q.CheckingDisabled = cd
		go func() {
			m, e := r.ExchangeContext(ctx, q)
			if e == nil && m.CheckingDisabled != q.CheckingDisabled {
				e = fmt.Errorf("shared CD result")
			}
			errs <- e
		}()
	}
	seen := map[bool]bool{}
	for i := 0; i < 2; i++ {
		select {
		case cd := <-entered:
			seen[cd] = true
		case <-ctx.Done():
			t.Fatal("independent request was coalesced")
		}
	}
	close(release)
	for i := 0; i < 2; i++ {
		if err := <-errs; err != nil {
			t.Fatal(err)
		}
	}
	if len(seen) != 2 {
		t.Fatal("checking flags lost")
	}
}

func TestDisableCacheCancellationDoesNotRetry(t *testing.T) {
	entered := make(chan struct{})
	f := &bypassFixture{reply: func(ctx context.Context, q *D.Msg) (*D.Msg, error) {
		close(entered)
		<-ctx.Done()
		return nil, ctx.Err()
	}}
	r := &Resolver{disableCache: true, main: []dnsClient{f}, cache: Config{}.newCache()}
	ctx, cancel := context.WithCancel(context.Background())
	defer cancel()
	done := make(chan error, 1)
	go func() { _, e := r.ExchangeContext(ctx, new(D.Msg).SetQuestion("cancel.example.", D.TypeA)); done <- e }()
	<-entered
	cancel()
	select {
	case e := <-done:
		if e == nil {
			t.Fatal("cancellation accepted")
		}
	case <-time.After(time.Second):
		t.Fatal("cancellation ignored")
	}
	time.Sleep(20 * time.Millisecond)
	if f.calls.Load() != 1 {
		t.Fatal("unexpected background retry")
	}
}

func TestDisableCachePropagation(t *testing.T) {
	ns := []NameServer{{Net: "udp", Addr: "127.0.0.1:1"}}
	rs := NewResolver(Config{DisableCache: true, Main: ns, Default: ns, ProxyServer: ns, DirectServer: ns})
	for _, r := range []*Resolver{rs.Resolver, rs.ProxyResolver, rs.DirectResolver, rs.defaultResolver} {
		if r == nil || !r.disableCache {
			t.Fatal("configuration not propagated to every configured resolver")
		}
	}
}

func TestCacheEnabledDefaultUnchanged(t *testing.T) {
	f := &bypassFixture{reply: func(_ context.Context, q *D.Msg) (*D.Msg, error) {
		r := new(D.Msg).SetReply(q)
		rr, _ := D.NewRR("default.example. 60 IN A 192.0.2.1")
		r.Answer = []D.RR{rr}
		return r, nil
	}}
	r := &Resolver{main: []dnsClient{f}, cache: Config{}.newCache()}
	for i := 0; i < 2; i++ {
		_, e := r.ExchangeContext(context.Background(), new(D.Msg).SetQuestion("default.example.", D.TypeA))
		if e != nil {
			t.Fatal(e)
		}
	}
	if f.calls.Load() != 1 {
		t.Fatal("legacy default cache behavior changed")
	}
	if _, e := r.ExchangeContext(context.Background(), new(D.Msg)); e == nil || e.Error() != "should have one question at least" {
		t.Fatal(e)
	}
}
