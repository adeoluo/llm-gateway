package gateway

import (
	"bytes"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"io"
	"net/http"
	"strings"
	"sync"
	"time"
)

// Config configures a Proxy.
type Config struct {
	// Upstream is the base URL of an OpenAI-compatible API, for example https://api.openai.com/v1.
	Upstream string
	// UpstreamKey is sent upstream as the bearer token. Client keys are never forwarded.
	UpstreamKey string
	// ClientKeys, if non-empty, is the set of accepted client bearer tokens.
	ClientKeys map[string]bool
	Threshold  float64
	Limiter    *RateLimiter
	Client     *http.Client
	MaxBody    int64
}

// Proxy screens chat completion requests and forwards the allowed ones upstream:
// authenticate, rate limit per client key, block prompt injection in user messages,
// redact PII in every message, forward, and redact PII in the response.
type Proxy struct {
	cfg     Config
	mu      sync.Mutex
	metrics map[string]int
}

// NewProxy validates cfg and fills defaults.
func NewProxy(cfg Config) (*Proxy, error) {
	if cfg.Upstream == "" {
		return nil, fmt.Errorf("upstream URL is required")
	}
	if cfg.Threshold == 0 {
		cfg.Threshold = DefaultThreshold
	}
	if cfg.Limiter == nil {
		cfg.Limiter = NewRateLimiter(60, 1, nil)
	}
	if cfg.Client == nil {
		cfg.Client = &http.Client{Timeout: 60 * time.Second}
	}
	if cfg.MaxBody == 0 {
		cfg.MaxBody = 1 << 20
	}
	cfg.Upstream = strings.TrimRight(cfg.Upstream, "/")
	return &Proxy{cfg: cfg, metrics: map[string]int{}}, nil
}

type message struct {
	Role    string `json:"role"`
	Content any    `json:"content"`
}

func (p *Proxy) count(name string) {
	p.mu.Lock()
	p.metrics[name]++
	p.mu.Unlock()
}

func writeError(w http.ResponseWriter, status int, kind, msg string, extra map[string]any) {
	body := map[string]any{"type": kind, "message": msg}
	for k, v := range extra {
		body[k] = v
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(map[string]any{"error": body})
}

// ServeHTTP routes /healthz, /metrics, and POST /v1/chat/completions.
func (p *Proxy) ServeHTTP(w http.ResponseWriter, r *http.Request) {
	switch {
	case r.URL.Path == "/healthz":
		_, _ = io.WriteString(w, "ok\n")
	case r.URL.Path == "/metrics":
		p.writeMetrics(w)
	case r.URL.Path == "/v1/chat/completions" && r.Method == http.MethodPost:
		p.chat(w, r)
	case r.URL.Path == "/v1/chat/completions":
		writeError(w, http.StatusMethodNotAllowed, "method_not_allowed", "use POST", nil)
	default:
		writeError(w, http.StatusNotFound, "not_found", "no such route", nil)
	}
}

func (p *Proxy) chat(w http.ResponseWriter, r *http.Request) {
	p.count("requests")
	key := strings.TrimSpace(strings.TrimPrefix(r.Header.Get("Authorization"), "Bearer "))
	if key == "" || (len(p.cfg.ClientKeys) > 0 && !p.cfg.ClientKeys[key]) {
		p.count("unauthorized")
		writeError(w, http.StatusUnauthorized, "unauthorized", "missing or unknown API key", nil)
		return
	}
	sum := sha256.Sum256([]byte(key))
	if !p.cfg.Limiter.Allow(hex.EncodeToString(sum[:8])) {
		p.count("rate_limited")
		w.Header().Set("Retry-After", "1")
		writeError(w, http.StatusTooManyRequests, "rate_limited", "rate limit exceeded", nil)
		return
	}
	raw, err := io.ReadAll(io.LimitReader(r.Body, p.cfg.MaxBody+1))
	if err != nil || int64(len(raw)) > p.cfg.MaxBody {
		writeError(w, http.StatusRequestEntityTooLarge, "payload_too_large", "request body too large", nil)
		return
	}
	var body map[string]any
	if err := json.Unmarshal(raw, &body); err != nil {
		writeError(w, http.StatusBadRequest, "invalid_json", "request body is not a JSON object", nil)
		return
	}
	if stream, _ := body["stream"].(bool); stream {
		writeError(w, http.StatusBadRequest, "unsupported", "streaming is not supported: responses are screened whole", nil)
		return
	}
	var messages []message
	if b, err := json.Marshal(body["messages"]); err != nil || json.Unmarshal(b, &messages) != nil || len(messages) == 0 {
		writeError(w, http.StatusBadRequest, "invalid_request", "'messages' must be a non-empty list", nil)
		return
	}

	var userText strings.Builder
	redactions := 0
	for i, m := range messages {
		text, ok := m.Content.(string)
		if !ok {
			writeError(w, http.StatusBadRequest, "invalid_request", "message content must be a string", nil)
			return
		}
		if m.Role == "user" {
			userText.WriteString(text)
			userText.WriteString("\n")
		}
		red := Redact(text)
		for _, n := range red.Counts {
			redactions += n
		}
		messages[i].Content = red.Text
	}
	if inj := AssessInjection(userText.String(), p.cfg.Threshold); inj.Blocked {
		p.count("blocked_injection")
		writeError(w, http.StatusUnprocessableEntity, "blocked_injection", "refused by gateway",
			map[string]any{"score": inj.Score, "triggers": inj.Triggers})
		return
	}
	if redactions > 0 {
		p.count("requests_redacted")
	}
	body["messages"] = messages
	p.forward(w, r, body)
}

func (p *Proxy) forward(w http.ResponseWriter, r *http.Request, body map[string]any) {
	payload, _ := json.Marshal(body)
	req, err := http.NewRequestWithContext(r.Context(), http.MethodPost, p.cfg.Upstream+"/chat/completions", bytes.NewReader(payload))
	if err != nil {
		writeError(w, http.StatusInternalServerError, "internal", err.Error(), nil)
		return
	}
	req.Header.Set("Content-Type", "application/json")
	if p.cfg.UpstreamKey != "" {
		req.Header.Set("Authorization", "Bearer "+p.cfg.UpstreamKey)
	}
	resp, err := p.cfg.Client.Do(req)
	if err != nil {
		p.count("upstream_errors")
		writeError(w, http.StatusBadGateway, "upstream_unavailable", err.Error(), nil)
		return
	}
	defer resp.Body.Close()
	data, err := io.ReadAll(io.LimitReader(resp.Body, 16<<20))
	if err != nil {
		p.count("upstream_errors")
		writeError(w, http.StatusBadGateway, "upstream_unavailable", err.Error(), nil)
		return
	}
	if resp.StatusCode == http.StatusOK {
		data = redactResponse(data, p)
	}
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(resp.StatusCode)
	_, _ = w.Write(data)
}

// redactResponse redacts PII in choices[].message.content, leaving other fields intact.
func redactResponse(data []byte, p *Proxy) []byte {
	var out map[string]any
	if json.Unmarshal(data, &out) != nil {
		return data
	}
	choices, _ := out["choices"].([]any)
	changed := false
	for _, c := range choices {
		choice, _ := c.(map[string]any)
		msg, _ := choice["message"].(map[string]any)
		if text, ok := msg["content"].(string); ok {
			if red := Redact(text); red.Text != text {
				msg["content"] = red.Text
				changed = true
			}
		}
	}
	if !changed {
		return data
	}
	p.count("responses_redacted")
	redacted, err := json.Marshal(out)
	if err != nil {
		return data
	}
	return redacted
}

func (p *Proxy) writeMetrics(w http.ResponseWriter) {
	p.mu.Lock()
	defer p.mu.Unlock()
	w.Header().Set("Content-Type", "text/plain; version=0.0.4")
	_, _ = io.WriteString(w, "# TYPE gateway_proxy_events_total counter\n")
	for _, name := range []string{"requests", "unauthorized", "rate_limited", "blocked_injection", "requests_redacted", "responses_redacted", "upstream_errors"} {
		_, _ = fmt.Fprintf(w, "gateway_proxy_events_total{event=%q} %d\n", name, p.metrics[name])
	}
}
