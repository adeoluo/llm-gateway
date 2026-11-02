package gateway

import (
	"sync"
	"time"
)

// RateLimiter keeps an independent token bucket per key, created on first use.
type RateLimiter struct {
	capacity float64
	refill   float64
	now      func() time.Time
	mu       sync.Mutex
	buckets  map[string]*bucket
}

type bucket struct {
	tokens float64
	last   time.Time
}

// NewRateLimiter allows bursts of capacity and refill requests per second per key.
func NewRateLimiter(capacity, refill float64, now func() time.Time) *RateLimiter {
	if now == nil {
		now = time.Now
	}
	return &RateLimiter{capacity: capacity, refill: refill, now: now, buckets: map[string]*bucket{}}
}

// Allow consumes one token for key if one is available.
func (l *RateLimiter) Allow(key string) bool {
	l.mu.Lock()
	defer l.mu.Unlock()
	t := l.now()
	b, ok := l.buckets[key]
	if !ok {
		b = &bucket{tokens: l.capacity, last: t}
		l.buckets[key] = b
	}
	elapsed := t.Sub(b.last).Seconds()
	if elapsed > 0 {
		b.tokens = min(l.capacity, b.tokens+elapsed*l.refill)
	}
	b.last = t
	if b.tokens >= 1 {
		b.tokens--
		return true
	}
	return false
}
