package route

import (
	"github.com/metacubex/http"
	"github.com/metacubex/http/httptest"
	"testing"
)

func TestManagedDNSMutationCannotReachUpdater(t *testing.T) {
	t.Setenv("MIHOMO_MANAGED_DNS", "1")
	for _, method := range []string{"POST", "PUT", "PATCH"} {
		called := false
		handler := managedDNSMutation(func(w http.ResponseWriter, r *http.Request) { called = true })
		recorder := httptest.NewRecorder()
		handler(recorder, httptest.NewRequest(method, "/", nil))
		if called || recorder.Code != http.StatusConflict {
			t.Fatal("mutation not rejected", method, recorder.Code)
		}
	}
}

func TestUnmanagedDNSMutationRetainsHandler(t *testing.T) {
	t.Setenv("MIHOMO_MANAGED_DNS", "")
	called := false
	handler := managedDNSMutation(func(w http.ResponseWriter, r *http.Request) { called = true })
	handler(httptest.NewRecorder(), httptest.NewRequest("POST", "/", nil))
	if !called {
		t.Fatal("unmanaged handler changed")
	}
}
