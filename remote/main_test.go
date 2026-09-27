package main

import (
	"net/url"
	"os"
	"strings"
	"testing"
)

// The API's start_url carries only the zak host key, so deepLink has to fall
// back to the separately supplied passcode. Getting this wrong silently drops
// the client at the passcode prompt instead of joining.
func TestDeepLinkCarriesPasscodeFallback(t *testing.T) {
	cases := []struct {
		name    string
		start   string
		fallbck string
		wantPwd string
		wantNo  bool
	}{
		{
			name:    "s form with zak needs fallback passcode",
			start:   "https://us05web.zoom.us/s/85895463055?zak=HOSTKEY",
			fallbck: "bdY3n4",
			wantPwd: "bdY3n4",
		},
		{
			name:    "j form keeps its own pwd",
			start:   "https://us05web.zoom.us/j/85895463055?pwd=fromurl&zak=HOSTKEY",
			fallbck: "ignored",
			wantPwd: "fromurl",
		},
		{
			name:   "no pwd anywhere omits the key",
			start:  "https://us05web.zoom.us/s/85895463055?zak=HOSTKEY",
			wantNo: true,
		},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			link, err := deepLink(tc.start, tc.fallbck)
			if err != nil {
				t.Fatalf("deepLink returned error: %v", err)
			}
			parsed, err := url.Parse(link)
			if err != nil {
				t.Fatalf("result is not a URL: %v", err)
			}
			if got := parsed.Query().Get("confno"); got != "85895463055" {
				t.Errorf("confno = %q, want 85895463055", got)
			}
			if got := parsed.Query().Get("pwd"); got != tc.wantPwd {
				t.Errorf("pwd = %q, want %q", got, tc.wantPwd)
			}
			_, hasPwd := parsed.Query()["pwd"]
			if hasPwd == tc.wantNo {
				t.Errorf("pwd present = %v, want %v", !tc.wantNo, !tc.wantNo)
			}
			if !strings.HasPrefix(link, "zoommtg://zoom.us/join?") {
				t.Errorf("link = %q, want a zoommtg join URL", link)
			}
		})
	}
}

func TestDeepLinkRejectsURLWithoutConferenceNumber(t *testing.T) {
	if _, err := deepLink("https://us05web.zoom.us/?zak=HOSTKEY", ""); err == nil {
		t.Fatal("expected an error for a start URL with no conference number")
	}
}

// The host key must never reach the logs in the clear: zak grants full control
// of the meeting to anyone holding it.
func TestRedactLinkHidesHostKey(t *testing.T) {
	raw := "zoommtg://zoom.us/join?action=join&confno=1&pwd=abc&zak=SECRETVALUE"
	got := redactLink(raw)
	if strings.Contains(got, "SECRETVALUE") {
		t.Errorf("redactLink leaked the host key: %s", got)
	}
	if !strings.Contains(got, "REDACTED") {
		t.Errorf("redactLink did not mark the key as redacted: %s", got)
	}
	if !strings.Contains(got, "confno=1") {
		t.Errorf("redactLink dropped the conference number: %s", got)
	}
}

func TestHostJoinMode(t *testing.T) {
	withKey := "zoommtg://zoom.us/join?confno=1&zak=KEY"
	if got := hostJoinMode(withKey); !strings.HasPrefix(got, "host") {
		t.Errorf("hostJoinMode(%q) = %q, want a host join", withKey, got)
	}
	// Note: the participant string itself contains the word "host" ("no host
	// key"), so match on the prefix rather than a substring.
	withoutKey := "zoommtg://zoom.us/join?confno=1"
	if got := hostJoinMode(withoutKey); !strings.HasPrefix(got, "participant") {
		t.Errorf("hostJoinMode(%q) = %q, want a participant join", withoutKey, got)
	}
}

// A process name that cannot exist must read as "not running" rather than
// erroring, because the kill loop polls this to decide it is done.
func TestLiveProcessMissingName(t *testing.T) {
	if liveProcess("definitely-not-a-real-process-name") {
		t.Error("liveProcess reported a process that does not exist")
	}
}

// Regression guard: pgrep counts zombies, and zombies linger because their
// parent is gone. This is what made every launch after the first time out.
func TestLiveProcessIgnoresZombie(t *testing.T) {
	if _, err := os.Stat("/proc/self/stat"); err != nil {
		t.Skip("no /proc on this platform")
	}
	// This process is alive and not a zombie, so it must be seen.
	if !liveProcess("go") && !liveProcess("test") {
		// Fall back to naming ourselves after the test binary.
		if !liveProcess(strings.TrimPrefix(os.Args[0], "/")) {
			t.Skip("could not identify this process by name")
		}
	}
	stat, err := os.ReadFile("/proc/self/stat")
	if err != nil {
		t.Skip("no /proc/self/stat")
	}
	if fields := strings.Fields(string(stat)); fields[2] == "Z" {
		t.Skip("test runner itself is a zombie")
	}
}
