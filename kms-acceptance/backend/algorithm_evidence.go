package main

// Only fixed native checks are accepted, never a browser-supplied success claim.
type AlgorithmCheck struct {
	ID         string  `json:"id"`
	Name       string  `json:"name"`
	Expected   string  `json:"expected"`
	Actual     string  `json:"actual"`
	Passed     bool    `json:"passed"`
	Status     string  `json:"status"`
	DurationMs float64 `json:"durationMs"`
	RecordedAt string  `json:"recordedAt"`
}

type AlgorithmEvidence struct {
	Version  int              `json:"version"`
	CaseID   string           `json:"caseId"`
	Category string           `json:"category"`
	Source   string           `json:"source"`
	Scope    string           `json:"scope"`
	Checks   []AlgorithmCheck `json:"checks"`
	Passed   bool             `json:"passed"`
}

func algorithmCheckIDs(caseID string) []string {
	switch caseID {
	case "pq-parameter-downgrade":
		return []string{"512-roundtrip", "512-interop", "512-tamper", "768-roundtrip", "768-interop", "768-tamper", "1024-roundtrip", "1024-interop", "1024-tamper"}
	case "pq-secret-upload":
		return []string{"512-roundtrip", "512-other-control", "512-wrong-key", "768-roundtrip", "768-other-control", "768-wrong-key", "1024-roundtrip", "1024-other-control", "1024-wrong-key"}
	case "pq-sign-encrypt-confusion":
		return []string{"falcon-roundtrip", "falcon-interop", "falcon-message-tamper"}
	case "pq-issuance-source-forgery":
		return []string{"falcon-roundtrip", "falcon-interop", "falcon-signature-tamper", "falcon-other-control", "falcon-wrong-key"}
	}
	return nil
}

func passedAlgorithmChecks(checks []AlgorithmCheck) int {
	n := 0
	for _, check := range checks {
		if check.Passed {
			n++
		}
	}
	return n
}

func validAlgorithmEvidence(caseID string, evidence *AlgorithmEvidence) bool {
	ids := algorithmCheckIDs(caseID)
	if evidence == nil || len(ids) == 0 || evidence.Version != 1 || evidence.CaseID != caseID ||
		evidence.Source == "" || evidence.Scope == "" || evidence.Category == "" || len(evidence.Checks) != len(ids) {
		return false
	}
	for i, check := range evidence.Checks {
		if check.ID != ids[i] || check.Name == "" || check.Expected == "" || check.Actual == "" || check.RecordedAt == "" || check.DurationMs < 0 ||
			(check.Status != "passed" && check.Status != "failed" && check.Status != "error") || check.Passed != (check.Status == "passed") {
			return false
		}
	}
	return evidence.Passed == (passedAlgorithmChecks(evidence.Checks) == len(ids))
}
