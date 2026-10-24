package main

import "testing"

func TestLatticeRequestBoundary(t *testing.T) {
	for _, body := range []string{
		`{"caseId":"offline-trapdoor"}`,
		`{"caseId":"basis-delegation","rootId":"00000000-0000-0000-0000-000000000000","nodeId":"node-A"}`,
		`{"caseId":"parallel-sampling","preparationId":"00000000-0000-0000-0000-000000000000","count":32,"workers":4}`,
	} {
		if !validLatticeRequest([]byte(body)) {
			t.Fatal("valid request rejected", body)
		}
	}
	for _, body := range []string{
		`{"caseId":"offline-trapdoor","passed":true}`,
		`{"caseId":"offline-trapdoor","rootId":""}`,
		`{"caseId":"parallel-sampling","preparationId":"00000000-0000-0000-0000-000000000000","count":100000,"workers":4}`,
		`{"caseId":"parallel-sampling","preparationId":"00000000-0000-0000-0000-000000000000","count":32,"workers":99}`,
		`{"caseId":"basis-delegation","rootId":"00000000-0000-0000-0000-000000000000","nodeId":""}`,
		`{"caseId":"offline-trapdoor"} {"caseId":"offline-trapdoor"}`,
		`{"caseId":"unknown"}`,
	} {
		if validLatticeRequest([]byte(body)) {
			t.Fatal("unbounded request accepted", body)
		}
	}
	if !canonicalDemoRoute("GET", "/api/lattice") || !canonicalDemoRoute("POST", "/api/lattice") || canonicalDemoRoute("DELETE", "/api/lattice") {
		t.Fatal("lattice routes must retain the Demo guard")
	}
}
