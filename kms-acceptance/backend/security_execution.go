package main

import (
	"context"
	"time"
)

// These are observations made by the executor, not claims about uninstrumented
// internal middleware branches. Never include session credentials or key bytes.
type SecurityProbeStep struct {
	Kind       string `json:"kind"`
	Name       string `json:"name"`
	Detail     string `json:"detail"`
	State      string `json:"state"`
	RecordedAt string `json:"recordedAt"`
}

func (p *securityProbe) recordStep(ctx context.Context, kind, name, detail, state string) {
	p.result.ProbeSteps = append(p.result.ProbeSteps, SecurityProbeStep{
		Kind: kind, Name: name, Detail: detail, State: state,
		RecordedAt: time.Now().Format(time.RFC3339Nano),
	})
	p.progress(ctx, name)
}
