package service

import (
	"crypto/elliptic"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/tjfoc/gmsm/sm2"
	"key-service-generate/models"
	"key-service-generate/service/generator"
)

func TestGenerationDIDKeepsDistinctIdentifierAndPublicOnlyRequests(t *testing.T) {
	var submitted []string
	var bodies []map[string]string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		if r.Header.Get("X-Internal-Token") != "offline-token" {
			t.Error("missing internal authentication")
		}
		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)
		bodies = append(bodies, body)
		var data map[string]interface{}
		if strings.HasSuffix(r.URL.Path, "/prepare") {
			id := strings.Repeat("a", 182)
			if len(bodies) > 2 {
				id = strings.Repeat("b", 182)
			}
			data = map[string]interface{}{"provider": "FABRIC_DID", "requestId": body["requestId"], "sysPid": id,
				"did": "did:offline:" + id, "chainId": "offline", "txId": strings.Repeat("a", 64), "status": "PREPARED", "submitted": false}
		} else {
			submitted = append(submitted, body["sysPid"])
			data = map[string]interface{}{"provider": "FABRIC_DID", "sysPid": body["sysPid"], "did": "did:offline:" + body["sysPid"],
				"chainId": "offline", "txId": strings.Repeat("a", 64), "status": "CONFIRMED", "transactionValid": true, "metadataMatches": true}
		}
		json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": data})
	}))
	defer server.Close()
	client := &fabricDidClient{server.URL, "offline-token", server.Client()}
	first, second := &models.Keymanage{KeyValue: "PRIVATE-MATERIAL-MUST-NOT-BE-SENT"}, &models.Keymanage{}
	for _, km := range []*models.Keymanage{first, second} {
		if err := client.prepare(km); err != nil {
			t.Fatal(err)
		}
		client.submit(km)
		if km.DidOnchain["status"] != "CONFIRMED" {
			t.Fatal(km.DidOnchain)
		}
	}
	if first.SysPid == second.SysPid || first.DidRequestID == second.DidRequestID {
		t.Fatal("identifiers reused")
	}
	if len(submitted) != 2 || submitted[0] != first.SysPid || submitted[1] != second.SysPid {
		t.Fatal(submitted)
	}
	for _, body := range bodies {
		if len(body) != 1 {
			t.Fatal("non-whitelisted data was sent", body)
		}
	}
}

func TestDIDUnknownSubmissionPreservesOriginalIdentifier(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) { time.Sleep(35 * time.Millisecond) }))
	defer server.Close()
	client := &fabricDidClient{server.URL, "offline-token", &http.Client{Timeout: 5 * time.Millisecond}}
	km := &models.Keymanage{SysPid: strings.Repeat("a", 182), DidOnchain: map[string]interface{}{"txId": strings.Repeat("b", 64)}}
	client.submit(km)
	if km.DidOnchain["status"] != "PENDING_VERIFICATION" || km.DidOnchain["txId"] != strings.Repeat("b", 64) ||
		km.SysPid != strings.Repeat("a", 182) {
		t.Fatal("original query parameters were lost")
	}
}

func TestDIDDisabledDoesNotCallBridge(t *testing.T) {
	t.Setenv("FABRIC_DID_KEYGEN_ENABLED", "false")
	client, err := keygenDIDClient()
	if client != nil || err != nil {
		t.Fatal("disabled feature must preserve the existing generation path")
	}
}

func TestEnrollPreservesSysPidInKafkaAndGenerationResult(t *testing.T) {
	pid, tx := strings.Repeat("a", 182), strings.Repeat("b", 64)
	var actions []string
	server := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		var body map[string]string
		json.NewDecoder(r.Body).Decode(&body)
		actions = append(actions, r.URL.Path)
		data := map[string]interface{}{"provider": "FABRIC_DID", "chainId": "offline", "sysPid": pid, "txId": tx, "did": "did:offline:" + pid}
		if strings.HasSuffix(r.URL.Path, "/prepare") {
			data["requestId"], data["status"], data["submitted"] = body["requestId"], "PREPARED", false
		} else {
			data["status"], data["transactionValid"], data["metadataMatches"] = "CONFIRMED", true, true
		}
		json.NewEncoder(w).Encode(map[string]interface{}{"code": 200, "data": data})
	}))
	defer server.Close()
	t.Setenv("FABRIC_DID_KEYGEN_ENABLED", "true")
	t.Setenv("FABRIC_DID_BRIDGE_URL", server.URL)
	t.Setenv("INTERNAL_TOKEN", "offline-token")
	s := &KeyManageService{eccGen: generator.GetECCGenerator(), saveChan: make(chan *models.KeyEnrollPayload, 1)}
	curve := sm2.P256Sm2()
	km := &models.Keymanage{UserName: "offline-user", EncrytType: "无证书非对称加密", EncrytName: "SM2",
		UA: hex.EncodeToString(elliptic.Marshal(curve, curve.Params().Gx, curve.Params().Gy)), KeyUse: "加解密"}
	if _, err := s.EnrollKey(km, ""); err != nil {
		t.Fatal(err)
	}
	payload := <-s.saveChan
	if len(actions) != 2 || !strings.HasSuffix(actions[0], "/prepare") || !strings.HasSuffix(actions[1], "/onchain") {
		t.Fatal(actions)
	}
	if payload.GeneratedKey.SysPid != pid || payload.GeneratedKey.DidRequestID != km.DidRequestID || km.DidOnchain["status"] != "CONFIRMED" {
		t.Fatal("identifier was lost between generation, Kafka and caller")
	}
	raw, _ := json.Marshal(payload)
	if !strings.Contains(string(raw), `"sys_pid":"`+pid+`"`) {
		t.Fatal("Kafka omitted SysPid")
	}
}
