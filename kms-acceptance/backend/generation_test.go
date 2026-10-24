package main

import (
	"context"
	"crypto/sha256"
	"encoding/json"
	"fmt"
	"math/big"
	"net/http"
	"net/http/httptest"
	"strconv"
	"sync"
	"testing"
	"time"
)

func TestGenerationInputsAreDistinctValidSM2Points(t *testing.T) {
	inputs, err := generationInputs(generationCount)
	if err != nil {
		t.Fatal(err)
	}
	seen := map[string]bool{}
	// The generation service validates points; independently check the curve equation.
	for _, ua := range inputs {
		if len(ua) != 130 || seen[ua] {
			t.Fatal("duplicate or malformed input")
		}
		seen[ua] = true
		var x, y, p, b big.Int
		x.SetString(ua[2:66], 16)
		y.SetString(ua[66:], 16)
		p.SetString("FFFFFFFEFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF00000000FFFFFFFFFFFFFFFF", 16)
		b.SetString("28E9FA9E9D9F5E344D5A9E4BCF6509A7F39789F515AB8F92DDBCBD414D940E93", 16)
		lhs := new(big.Int).Mul(&y, &y)
		rhs := new(big.Int).Exp(&x, big.NewInt(3), &p)
		rhs.Sub(rhs, new(big.Int).Mul(big.NewInt(3), &x))
		rhs.Add(rhs, &b)
		lhs.Mod(lhs, &p)
		rhs.Mod(rhs, &p)
		if lhs.Cmp(rhs) != 0 {
			t.Fatal("point off curve")
		}
	}
}

func TestGenerationRejectsDuplicateInputsAndMismatchedMaterial(t *testing.T) {
	version := 1
	digest := fmt.Sprintf("%x", sha256.Sum256([]byte("material")))
	e := &generationEvidence{Batch: "batch", Selected: 3}
	rows := []internalKeyRecord{{KeyID: 1, UA: "ua1", UserName: "u", KeyDomain: "acceptance", KeyName: "batch", EncrytName: "SSCL", Status: "0"}, {KeyID: 2, UA: "ua1", UserName: "u", KeyDomain: "acceptance", KeyName: "batch", EncrytName: "SSCL", Status: "0"}, {KeyID: 3, UA: "ua3", UserName: "u", KeyDomain: "acceptance", KeyName: "batch", EncrytName: "SSCL", Status: "0"}}
	states := map[int64]internalVerifyRecord{}
	for _, r := range rows {
		states[r.KeyID] = internalVerifyRecord{KeyID: r.KeyID, Exists: true, Status: "0", UserName: "u", KeyDomain: "acceptance", Version: &version, MaterialDigest: digest}
	}
	verifyGeneration(e, rows, states, map[string]string{"ua1": digest, "ua3": "wrong-digest"}, "u")
	if e.Completed != 1 || e.Duplicates != 1 || e.Invalid != 1 || e.Failed != 2 {
		t.Fatalf("wrong counts: %+v", e)
	}
}

func TestGenerationCountsBusinessFailureAndRegistrationEndToEnd(t *testing.T) {
	var mu sync.Mutex
	rows := []internalKeyRecord{}
	states := map[int64]internalVerifyRecord{}
	var requests int
	api := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if r.URL.Path == "/generate" {
			var body map[string]string
			json.NewDecoder(r.Body).Decode(&body)
			if r.Header.Get("X-Kms-User") != "u" {
				t.Error("missing verified user")
			}
			mu.Lock()
			defer mu.Unlock()
			requests++
			if requests == 1 {
				fmt.Fprint(w, `{"code":500,"data":""}`)
				return
			}
			id := int64(requests)
			material := "material-" + body["ua"]
			digest := fmt.Sprintf("%x", sha256.Sum256([]byte(material)))
			v := 1
			rows = append(rows, internalKeyRecord{KeyID: id, UA: body["ua"], UserName: "u", KeyDomain: "acceptance", KeyName: body["key_name"], EncrytName: "SSCL", Status: "0"})
			states[id] = internalVerifyRecord{KeyID: id, Exists: true, Status: "0", UserName: "u", KeyDomain: "acceptance", Version: &v, MaterialDigest: digest}
			json.NewEncoder(w).Encode(map[string]any{"code": 200, "data": material})
			return
		}
		if r.URL.Path == "/keys" {
			time.Sleep(25 * time.Millisecond)
			mu.Lock()
			defer mu.Unlock()
			json.NewEncoder(w).Encode(map[string]any{"data": rows})
			return
		}
		if r.URL.Path == "/status" {
			mu.Lock()
			defer mu.Unlock()
			out := []internalVerifyRecord{}
			for _, s := range r.URL.Query()["keyIds"] {
				id, _ := strconv.ParseInt(s, 10, 64)
				out = append(out, states[id])
			}
			json.NewEncoder(w).Encode(map[string]any{"data": out})
			return
		}
		http.NotFound(w, r)
	}))
	defer api.Close()
	s := &server{client: api.Client(), cfg: acceptanceConfig{AcceptanceUser: "u", GenerateKeyPoolURL: api.URL + "/keys", LifecycleVerifyURL: api.URL + "/status", VerifyWaitSeconds: 1}}
	result := s.executeGeneration(context.Background(), Scenario{BaseURL: api.URL, Path: "/generate", Connections: 40, Headers: map[string]string{"X-Kms-User": "u"}, TargetTPS: 100000, TargetOperator: ">="})
	e := result.Generation
	if result.Error != "" || !e.Verified || e.Submitted != 6000 || e.HTTPSuccess != 6000 || e.Accepted != 5999 || e.Registered != 5999 || e.Completed != 5999 || e.Failed != 1 || result.Status != "failed_threshold" || result.PassedTPS {
		t.Fatalf("bad result: %+v / %+v", result, e)
	}
	if e.ElapsedMs < e.SubmissionMs+24 || result.Summary.SuccessfulRequestsPerSec != float64(e.Completed)*1000/e.ElapsedMs {
		t.Fatal("registration time excluded or rate uses accepted requests")
	}
	if !compareThreshold(100000, ">=", 100000) {
		t.Fatal("boundary must pass")
	}
}
