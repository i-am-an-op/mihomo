package route

import (
	"github.com/metacubex/chi/render"
	"github.com/metacubex/http"
	C "github.com/metacubex/mihomo/constant"
)

// managedDNSMutation keeps core/config replacement and restart in the
// external verified transaction. Read APIs and proxy selection are unchanged.
func managedDNSMutation(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if C.ManagedDNSFrontend() {
			render.Status(r, http.StatusConflict)
			render.JSON(w, r, newError("managed DNS frontend: use the reviewed offline promotion procedure"))
			return
		}
		next(w, r)
	}
}
