package main

import (
	"math"
	"testing"
)

func TestParseWrkOutputSeparatesSocketAndHTTPErrors(t *testing.T) {
	output := `
Latency   1.20ms   2.00ms   3.10ms
Requests/sec: 100000.00
Transfer/sec: 10.00MB
100 requests in 1.00s, 1.00MB read
Socket errors: connect 2, read 3, write 4, timeout 1
Non-2xx or 3xx responses: 10
99%   3.10ms
`
	summary := parseWrkOutput(output)
	if summary.TotalRequests != 100 {
		t.Fatalf("total requests = %d, want 100", summary.TotalRequests)
	}
	if summary.SocketErrors != 10 || summary.Non2xxResponses != 10 || summary.ErrorCount != 20 {
		t.Fatalf("error split = socket %d non2xx %d total %d, want 10/10/20", summary.SocketErrors, summary.Non2xxResponses, summary.ErrorCount)
	}
	if math.Abs(summary.SuccessRate-81.81818181818181) > 1e-9 {
		t.Fatalf("success rate = %v, want 81.81818181818181", summary.SuccessRate)
	}
}

func TestSuccessfulRateUsesCompletedHTTPRequestsOnly(t *testing.T) {
	summary := parseWrkOutput("100 requests in 2.00s, 1.00MB read\nSocket errors: connect 5, read 0, write 0, timeout 0\nNon-2xx or 3xx responses: 10\n")
	successful := summary.TotalRequests - summary.Non2xxResponses
	if successful != 90 {
		t.Fatalf("successful requests = %d, want 90", successful)
	}
}
