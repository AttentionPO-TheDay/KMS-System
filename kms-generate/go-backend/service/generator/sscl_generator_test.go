package generator

import (
	"strings"
	"testing"
)

func TestSSCLGenPartialKeyIncludesChainScalar(t *testing.T) {
	gen := newSSCLGenerator()
	res, err := gen.GenPartialKey("alice", gen.gStr, "test-domain")
	if err != nil {
		t.Fatalf("GenPartialKey returned error: %v", err)
	}

	if !strings.Contains(res.KeyValue, `"SSCLKey":"04`) {
		t.Fatalf("missing SSCLKey in response: %s", res.KeyValue)
	}
	if !strings.Contains(res.KeyValue, `"SSCLEA":"`) {
		t.Fatalf("missing SSCLEA in response: %s", res.KeyValue)
	}
	if !strings.Contains(res.KeyValue, `"SSCLDomian":"test-domain"`) {
		t.Fatalf("missing SSCLDomian in response: %s", res.KeyValue)
	}
	if len(res.KeyValue) != len(`{"SSCLKey":"04`)+128+len(`","SSCLEA":"`)+64+len(`","SSCLDomian":"test-domain"}`) {
		t.Fatalf("unexpected response length: got %d, value=%s", len(res.KeyValue), res.KeyValue)
	}
}

func TestSSCLGenPartialKeyRejectsPointOffCurve(t *testing.T) {
	gen := newSSCLGenerator()
	invalidUA := "04" + strings.Repeat("0", 128)

	_, err := gen.GenPartialKey("alice", invalidUA, "test-domain")
	if err == nil {
		t.Fatal("expected point validation error")
	}
	if !strings.Contains(err.Error(), "curve") {
		t.Fatalf("unexpected error: %v", err)
	}
}

func BenchmarkSSCLGenPartialKey(b *testing.B) {
	gen := newSSCLGenerator()
	b.ReportAllocs()
	b.SetParallelism(4)
	b.ResetTimer()

	b.RunParallel(func(pb *testing.PB) {
		for pb.Next() {
			if _, err := gen.GenPartialKey("alice", gen.gStr, "bench-domain"); err != nil {
				b.Fatalf("GenPartialKey returned error: %v", err)
			}
		}
	})
}
