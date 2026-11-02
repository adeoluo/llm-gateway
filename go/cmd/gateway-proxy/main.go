// Command gateway-proxy is an OpenAI-compatible reverse proxy that applies the llm-gateway
// safety rules: per-key rate limiting, prompt-injection blocking, and PII redaction of
// prompts and responses.
package main

import (
	"context"
	"errors"
	"flag"
	"fmt"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strings"
	"syscall"
	"time"

	"github.com/adeoluo/llm-gateway/go/gateway"
)

var version = "dev"

func main() {
	listen := flag.String("listen", "127.0.0.1:8090", "address to listen on")
	upstream := flag.String("upstream", "https://api.openai.com/v1", "OpenAI-compatible base URL")
	threshold := flag.Float64("threshold", gateway.DefaultThreshold, "injection score at which requests are blocked")
	capacity := flag.Float64("rate-capacity", 60, "burst size per client key")
	refill := flag.Float64("rate-refill", 1, "requests per second refilled per client key")
	showVersion := flag.Bool("version", false, "print the version and exit")
	flag.Parse()
	if *showVersion {
		fmt.Println("gateway-proxy", version)
		return
	}

	keys := map[string]bool{}
	for _, k := range strings.Split(os.Getenv("GATEWAY_CLIENT_KEYS"), ",") {
		if k = strings.TrimSpace(k); k != "" {
			keys[k] = true
		}
	}
	proxy, err := gateway.NewProxy(gateway.Config{
		Upstream:    *upstream,
		UpstreamKey: os.Getenv("UPSTREAM_API_KEY"),
		ClientKeys:  keys,
		Threshold:   *threshold,
		Limiter:     gateway.NewRateLimiter(*capacity, *refill, nil),
	})
	if err != nil {
		log.Fatal(err)
	}
	server := &http.Server{Addr: *listen, Handler: proxy, ReadHeaderTimeout: 10 * time.Second}
	ctx, stop := signal.NotifyContext(context.Background(), syscall.SIGINT, syscall.SIGTERM)
	defer stop()
	go func() {
		<-ctx.Done()
		shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		_ = server.Shutdown(shutdown)
	}()
	log.Printf("gateway-proxy %s listening on %s, forwarding to %s (%d client keys)", version, *listen, *upstream, len(keys))
	if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
		log.Fatal(err)
	}
}
