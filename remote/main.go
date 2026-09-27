package main

import (
	"crypto/subtle"
	"encoding/json"
	"errors"
	"log"
	"net/http"
	"net/url"
	"os"
	"os/exec"
	"path/filepath"
	"strings"
	"sync"
	"time"
)

type controllerState struct {
	MeetingID   string `json:"meeting_id,omitempty"`
	Status      string `json:"status"`
	RequestedBy int64  `json:"requested_by,omitempty"`
	LaunchedAt  int64  `json:"launched_at,omitempty"`
	LastError   string `json:"last_error,omitempty"`
}

type launchRequest struct {
	StartURL    string `json:"start_url"`
	RequestedBy int64  `json:"requested_by"`
	// Passcode is sent separately because the API's start_url only carries the
	// zak host key. Without pwd the client stops at the passcode prompt.
	Passcode string `json:"passcode"`
}

const (
	// xdg-open routes the https:// start_url through Firefox, which then has to
	// hand the zoommtg:// deep link back to Zoom. That round trip is where the
	// join silently dies, so we skip it and drive the launcher ourselves.
	zoomLauncher = "/opt/zoom/ZoomLauncher"

	// A stale "opened"/"launch_requested" state used to pin the host forever:
	// nothing on this side ever advanced it, so the next launch of a different
	// meeting got 409 until someone hit restart by hand.
	stateTTL = 10 * time.Minute

	killTimeout   = 10 * time.Second
	handshakeWait = 20 * time.Second
)

// Kasm images vary the profile path, so read it from the environment the
// startup script can export rather than hardcoding a guess.
var zoomHome = envOr("ZOOM_HOME_DIR", "/home/kasm-user/.zoom")

func envOr(key, fallback string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return fallback
}

var (
	apiToken       = os.Getenv("REMOTE_API_TOKEN")
	allowedDomains = domainList(os.Getenv("REMOTE_ALLOWED_ZOOM_DOMAINS"))
	state          = controllerState{Status: "idle"}
	stateMu        sync.Mutex
)

// deepLink converts the API's https://us05web.zoom.us/s/<id>?zak=<hostkey> start_url
// into the zoommtg:// form ZoomLauncher understands. This skips the browser round
// trip that xdg-open forces (Firefox opens the page, which then redirects back
// into Zoom as a single-instance IPC message - the exact step that was dropping
// the join).
//
// fallbackPasscode fills in pwd when the start_url has none, which is the normal
// case: the API only ever puts the zak host key in the query string.
//
// zak is Zoom's "host key": carrying it means Zoom starts this meeting as the
// host, with no sign-in prompt in the container. That is what removes the
// one-time manual VNC login.
func deepLink(startURL, fallbackPasscode string) (string, error) {
	parsed, err := url.Parse(startURL)
	if err != nil {
		return "", err
	}
	// /j/85895463055 or /s/85895463055 -> confno=85895463055
	confno := strings.Trim(parsed.Path, "/")
	if parts := strings.Split(confno, "/"); len(parts) > 0 {
		confno = parts[len(parts)-1]
	}
	if confno == "" {
		return "", errors.New("start URL carries no conference number")
	}
	q := url.Values{}
	q.Set("action", "join")
	q.Set("confno", confno)
	pwd := parsed.Query().Get("pwd")
	if pwd == "" {
		pwd = fallbackPasscode
	}
	if pwd != "" {
		q.Set("pwd", pwd)
	}
	// Without the host key Zoom shows a sign-in prompt on the container's own
	// display and the host never joins. zak turns this into a host join.
	if zak := parsed.Query().Get("zak"); zak != "" {
		q.Set("zak", zak)
	}
	return "zoommtg://zoom.us/join?" + q.Encode(), nil
}

// redactLink hides the host key so a launch URL can be logged. The bare
// conference number and passcode are not secret; zak grants full host control
// of the meeting to anyone holding it.
func redactLink(link string) string {
	if parsed, err := url.Parse(link); err == nil {
		if parsed.Query().Get("zak") != "" {
			q := parsed.Query()
			q.Set("zak", "REDACTED")
			parsed.RawQuery = q.Encode()
			return parsed.String()
		}
	}
	return link
}

func domainList(raw string) []string {
	if raw == "" {
		raw = ".zoom.us"
	}
	items := strings.Split(strings.ToLower(raw), ",")
	out := make([]string, 0, len(items))
	for _, item := range items {
		if item = strings.TrimSpace(item); item != "" {
			out = append(out, item)
		}
	}
	return out
}

func authorized(r *http.Request) bool {
	provided := r.Header.Get("Authorization")
	expected := "Bearer " + apiToken
	return apiToken != "" && len(provided) == len(expected) &&
		subtle.ConstantTimeCompare([]byte(provided), []byte(expected)) == 1
}

func auth(next http.HandlerFunc) http.HandlerFunc {
	return func(w http.ResponseWriter, r *http.Request) {
		if !authorized(r) {
			http.Error(w, "unauthorized", http.StatusUnauthorized)
			return
		}
		next(w, r)
	}
}

func validZoomURL(raw string) bool {
	parsed, err := url.Parse(raw)
	if err != nil || parsed.Scheme != "https" || parsed.Hostname() == "" {
		return false
	}
	host := strings.ToLower(parsed.Hostname())
	for _, suffix := range allowedDomains {
		bare := strings.TrimPrefix(suffix, ".")
		if host == bare || strings.HasSuffix(host, suffix) {
			return true
		}
	}
	return false
}

// zoomRunning reports whether a real (non-zombie) zoom client is alive.
// pgrep counts zombies, and a SIGKILLed process that nobody reaps lingers in
// state Z forever because its parent is already gone. Treating that as "still
// running" made killZoomAndWait time out on every launch after the first.
func zoomRunning() bool {
	return liveProcess("zoom")
}

func liveProcess(name string) bool {
	out, err := exec.Command("pgrep", "-x", name).Output()
	if err != nil {
		return false
	}
	for _, field := range strings.Fields(string(out)) {
		pid := strings.TrimSpace(field)
		if pid == "" {
			continue
		}
		// Field 3 of /proc/<pid>/stat is the single-letter process state.
		stat, readErr := os.ReadFile("/proc/" + pid + "/stat")
		if readErr != nil {
			continue // already gone
		}
		fields := strings.Fields(string(stat))
		if len(fields) > 2 && fields[2] != "Z" {
			return true
		}
	}
	return false
}

// killZoomAndWait stops every Zoom process and blocks until they are actually
// gone. pkill returning only means a signal was delivered; launching the
// replacement immediately after used to race the dying instance, and the
// replacement then saw "another zoom instance is running" and exited - a loop
// that produced zero joins.
func killZoomAndWait() error {
	for _, name := range []string{"ZoomWebviewHost", "ZoomLauncher", "zoom"} {
		_ = exec.Command("pkill", "-9", "-x", name).Run()
		_ = exec.Command("pkill", "-9", "-f", name+".bin").Run()
	}
	deadline := time.Now().Add(killTimeout)
	for time.Now().Before(deadline) {
		if !liveProcess("zoom") && !liveProcess("ZoomLauncher") && !liveProcess("ZoomWebviewHost") {
// Chromium's CEF view keeps two kinds of stale state that outlive the
		// process which created it:
		//   cefIpcChannel/  - one unix socket per webview
		//   cefcache/       - SingletonLock / SingletonSocket / SingletonCookie
		// Either one makes the next start abort with "The profile appears to be in
		// use by another Chromium process" and ContentMainRun exit code 21, which
		// surfaces as a live zoom process over a black VNC screen. Clearing them
		// is safe precisely because we only get here once nothing is running.
		clearCEFState(zoomHome + "/data/cefIpcChannel")
		clearCEFState(zoomHome + "/data/cefcache")
		return nil
		}
		time.Sleep(200 * time.Millisecond)
	}
	return errors.New("Zoom processes did not exit within " + killTimeout.String())
}

// clearCEFState removes only the singleton/lock entries named in keep-vs-drop
// form: everything except the CEF cache the image ships with.
func clearCEFState(dir string) {
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if strings.HasPrefix(e.Name(), "Singleton") {
			_ = os.RemoveAll(filepath.Join(dir, e.Name()))
		}
	}
}

func respond(w http.ResponseWriter, status int, payload any) {
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(payload)
}

func health(w http.ResponseWriter, _ *http.Request) {
	respond(w, http.StatusOK, map[string]any{"ok": true, "zoom_running": zoomRunning()})
}

func status(w http.ResponseWriter, _ *http.Request) {
	stateMu.Lock()
	snapshot := state
	stateMu.Unlock()
	respond(w, http.StatusOK, struct {
		controllerState
		ZoomRunning bool `json:"zoom_running"`
	}{snapshot, zoomRunning()})
}

func meetingID(path, action string) (string, error) {
	prefix := "/meetings/"
	if !strings.HasPrefix(path, prefix) || !strings.HasSuffix(path, action) {
		return "", errors.New("invalid path")
	}
	id := strings.TrimSuffix(strings.TrimPrefix(path, prefix), action)
	id = strings.Trim(id, "/")
	if id == "" {
		return "", errors.New("missing meeting id")
	}
	return id, nil
}

func launch(w http.ResponseWriter, r *http.Request) {
	id, err := meetingID(r.URL.Path, "/launch")
	if err != nil {
		http.NotFound(w, r)
		return
	}
	var body launchRequest
	decoder := json.NewDecoder(http.MaxBytesReader(w, r.Body, 64*1024))
	if decoder.Decode(&body) != nil || !validZoomURL(body.StartURL) {
		http.Error(w, "invalid Zoom start URL", http.StatusBadRequest)
		return
	}
	stateMu.Lock()
	defer stateMu.Unlock()

	// A previous launch that never confirmed must not pin the host forever.
	if state.MeetingID != "" && state.MeetingID != id &&
		(state.Status == "launch_requested" || state.Status == "opened") &&
		time.Since(time.Unix(state.LaunchedAt, 0)) < stateTTL {
		http.Error(w, "another meeting is assigned to this host", http.StatusConflict)
		return
	}

	link, err := deepLink(body.StartURL, body.Passcode)
	if err != nil {
		http.Error(w, "invalid Zoom start URL: "+err.Error(), http.StatusBadRequest)
		return
	}

	state = controllerState{MeetingID: id, Status: "launch_requested", RequestedBy: body.RequestedBy, LaunchedAt: time.Now().Unix()}

	if err := killZoomAndWait(); err != nil {
		state.Status, state.LastError = "failed", "kill_timeout"
		log.Printf("could not free host for meeting %s: %v", id, err)
		http.Error(w, "failed to free host", http.StatusInternalServerError)
		return
	}

	// /usr/bin/zoom is a wrapper that probes seccomp and re-execs
	// ZoomLauncher; calling the launcher directly is one process instead of two
	// and keeps the seccomp probe out of the launch path.
	cmd := exec.Command(zoomLauncher, "--no-sandbox", link)
	cmd.Stdout, cmd.Stderr = nil, nil
	if err := cmd.Start(); err != nil {
		state.Status, state.LastError = "failed", "launch_failed"
		log.Printf("Zoom launch failed for meeting %s: %v", id, err)
		http.Error(w, "failed to launch Zoom", http.StatusInternalServerError)
		return
	}
	// ZoomLauncher is a launcher: it hands the link to (or spawns) the real
	// client and exits. Reap it so it cannot linger and trip the next launch's
	// single-instance check.
	go func() { _ = cmd.Wait() }()

	// Give the client a moment to claim the single-instance slot; if it never
	// appears the join will not happen and the bot should hear about it now
	// rather than after the full confirmation timeout.
	deadline := time.Now().Add(handshakeWait)
	appeared := false
	for time.Now().Before(deadline) {
		if zoomRunning() {
			appeared = true
			break
		}
		time.Sleep(500 * time.Millisecond)
	}
	if !appeared {
		state.Status, state.LastError = "failed", "zoom_client_not_started"
		log.Printf("Zoom client never came up for meeting %s (link=%s)", id, redactLink(link))
		http.Error(w, "Zoom client did not start", http.StatusInternalServerError)
		return
	}

	state.Status = "opened"
	log.Printf("meeting %s: Zoom client up, joining as %s via %s", id,
		hostJoinMode(link), redactLink(link))
	respond(w, http.StatusOK, map[string]any{"accepted": true, "state": state.Status, "meeting_id": id})
}

// hostJoinMode reports whether this launch carries a host key, so the log says
// plainly whether the container still needs a manual sign-in.
func hostJoinMode(link string) string {
	if parsed, err := url.Parse(link); err == nil && parsed.Query().Get("zak") != "" {
		return "host (zak present)"
	}
	return "participant (no host key)"
}

func stop(w http.ResponseWriter, r *http.Request) {
	id, err := meetingID(r.URL.Path, "/stop")
	if err != nil {
		http.NotFound(w, r)
		return
	}
	stateMu.Lock()
	defer stateMu.Unlock()
	if state.MeetingID != "" && state.MeetingID != id {
		http.Error(w, "meeting does not own host", http.StatusConflict)
		return
	}
	if err := killZoomAndWait(); err != nil {
		log.Printf("stop for meeting %s: %v", id, err)
	}
	state = controllerState{Status: "idle"}
	respond(w, http.StatusOK, map[string]bool{"stopped": true})
}

func restart(w http.ResponseWriter, _ *http.Request) {
	_ = exec.Command("pkill", "-TERM", "-x", "zoom").Run()
	_ = exec.Command("pkill", "-TERM", "-f", "chrome").Run()
	stateMu.Lock()
	state = controllerState{Status: "idle"}
	stateMu.Unlock()
	// Deliberately not killZoomAndWait: restart is the operator's escape hatch
	// and must return immediately, even if Zoom is wedged.
	respond(w, http.StatusOK, map[string]bool{"restarted": true})
}

func main() {
	port := os.Getenv("REMOTE_API_PORT")
	if port == "" {
		port = "8080"
	}
	http.HandleFunc("/health", health)
	http.HandleFunc("/status", auth(status))
	http.HandleFunc("/meetings/", auth(func(w http.ResponseWriter, r *http.Request) {
		if r.Method != http.MethodPost {
			http.Error(w, "method not allowed", http.StatusMethodNotAllowed)
			return
		}
		if strings.HasSuffix(r.URL.Path, "/launch") {
			launch(w, r)
			return
		}
		if strings.HasSuffix(r.URL.Path, "/stop") {
			stop(w, r)
			return
		}
		http.NotFound(w, r)
	}))
	http.HandleFunc("/zoom/restart", auth(restart))
	log.Printf("Remote Zoom controller listening on :%s", port)
	log.Fatal(http.ListenAndServe("0.0.0.0:"+port, nil))
}
