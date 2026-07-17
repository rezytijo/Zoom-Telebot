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
}

var (
	apiToken       = os.Getenv("REMOTE_API_TOKEN")
	allowedDomains = domainList(os.Getenv("REMOTE_ALLOWED_ZOOM_DOMAINS"))
	state          = controllerState{Status: "idle"}
	stateMu        sync.Mutex
)

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

func zoomRunning() bool { return exec.Command("pgrep", "-x", "zoom").Run() == nil }

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
	if state.MeetingID != "" && state.MeetingID != id && (state.Status == "launch_requested" || state.Status == "opened") {
		http.Error(w, "another meeting is assigned to this host", http.StatusConflict)
		return
	}
	state = controllerState{MeetingID: id, Status: "launch_requested", RequestedBy: body.RequestedBy, LaunchedAt: time.Now().Unix()}
	_ = exec.Command("pkill", "-9", "-x", "zoom").Run()
	_ = exec.Command("pkill", "-9", "-x", "ZoomLauncher").Run()
	_ = exec.Command("pkill", "-9", "-f", "ZoomWebviewHost").Run()
	cmd := exec.Command("/usr/bin/xdg-open", body.StartURL)
	cmd.Stdout, cmd.Stderr = nil, nil
	if err := cmd.Start(); err != nil {
		state.Status, state.LastError = "failed", "launch_failed"
		log.Printf("Zoom launch failed for meeting %s", id)
		http.Error(w, "failed to launch Zoom", http.StatusInternalServerError)
		return
	}
	state.Status = "opened"
	respond(w, http.StatusOK, map[string]any{"accepted": true, "state": state.Status, "meeting_id": id})
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
	_ = exec.Command("pkill", "-TERM", "-x", "zoom").Run()
	_ = exec.Command("pkill", "-TERM", "-f", "chrome").Run()
	state = controllerState{Status: "idle"}
	respond(w, http.StatusOK, map[string]bool{"stopped": true})
}

func restart(w http.ResponseWriter, _ *http.Request) {
	_ = exec.Command("pkill", "-TERM", "-x", "zoom").Run()
	_ = exec.Command("pkill", "-TERM", "-f", "chrome").Run()
	stateMu.Lock()
	state = controllerState{Status: "idle"}
	stateMu.Unlock()
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
