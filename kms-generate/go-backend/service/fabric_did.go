package service

// The SDK and management keys stay in the private bridge; only public identifiers cross this boundary.
import (
	"bytes"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/url"
	"os"
	"regexp"
	"strings"
	"time"

	"github.com/google/uuid"
	"key-service-generate/models"
)

var didSysPidPattern = regexp.MustCompile(`^[0-9a-f]{182}$`)
var didTransactionPattern = regexp.MustCompile(`^[0-9a-f]{64}$`)

type fabricDidClient struct {
	base, token string
	http        *http.Client
}

func keygenDIDClient() (*fabricDidClient, error) {
	if !strings.EqualFold(os.Getenv("FABRIC_DID_KEYGEN_ENABLED"), "true") {
		return nil, nil
	}
	base := strings.TrimRight(os.Getenv("FABRIC_DID_BRIDGE_URL"), "/")
	if base == "" {
		base = "http://fabric-did-bridge:9094/internal/fabric-did"
	}
	u, err := url.Parse(base)
	token := os.Getenv("INTERNAL_TOKEN")
	if err != nil || u.Hostname() == "" || u.User != nil || (u.Scheme != "http" && u.Scheme != "https") || token == "" {
		return nil, errors.New("DID_KEYGEN_NOT_CONFIGURED")
	}
	return &fabricDidClient{base, token, &http.Client{
		Timeout: 25 * time.Second, Transport: &http.Transport{Proxy: nil},
		CheckRedirect: func(*http.Request, []*http.Request) error { return http.ErrUseLastResponse },
	}}, nil
}

func (c *fabricDidClient) request(action string, body map[string]string) (map[string]interface{}, error) {
	raw, _ := json.Marshal(body)
	req, err := http.NewRequest(http.MethodPost, c.base+"/sys-pids/"+action, bytes.NewReader(raw))
	if err != nil {
		return nil, errors.New("DID_REQUEST_INVALID")
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", c.token)
	response, err := c.http.Do(req)
	if err != nil {
		return nil, errors.New("DID_BRIDGE_UNAVAILABLE_OR_TIMEOUT")
	}
	defer response.Body.Close()
	var envelope struct {
		Code int                    `json:"code"`
		Data map[string]interface{} `json:"data"`
	}
	if json.NewDecoder(io.LimitReader(response.Body, 128*1024)).Decode(&envelope) != nil ||
		response.StatusCode != http.StatusOK || envelope.Code != 200 || envelope.Data == nil {
		return nil, errors.New("DID_BRIDGE_REJECTED")
	}
	return envelope.Data, nil
}

func (c *fabricDidClient) prepare(km *models.Keymanage) error {
	km.DidRequestID = uuid.NewString()
	result, err := c.request("prepare", map[string]string{"requestId": km.DidRequestID})
	if err != nil {
		return err
	}
	sysPid, _ := result["sysPid"].(string)
	txID, _ := result["txId"].(string)
	if !didSysPidPattern.MatchString(sysPid) || !didTransactionPattern.MatchString(txID) ||
		result["requestId"] != km.DidRequestID || result["provider"] != "FABRIC_DID" ||
		result["status"] != "PREPARED" || result["submitted"] != false {
		return errors.New("DID_PREPARE_RESPONSE_MISMATCH")
	}
	km.SysPid, km.DidOnchain = sysPid, result
	return nil
}

func (c *fabricDidClient) submit(km *models.Keymanage) {
	// The bridge has already saved txId/nonce. Query an uncertain outcome instead of creating another identifier.
	km.DidOnchain["submissionAttempted"] = true
	km.DidOnchain["submitted"] = nil
	result, err := c.request("onchain", map[string]string{"sysPid": km.SysPid})
	if err != nil {
		km.DidOnchain["status"], km.DidOnchain["errorCode"] = "PENDING_VERIFICATION", err.Error()
		return
	}
	if result["provider"] != "FABRIC_DID" || result["sysPid"] != km.SysPid || result["did"] != km.DidOnchain["did"] ||
		result["txId"] != km.DidOnchain["txId"] || result["chainId"] != km.DidOnchain["chainId"] {
		km.DidOnchain["status"], km.DidOnchain["errorCode"] = "PENDING_VERIFICATION", "DID_SUBMISSION_RESPONSE_MISMATCH"
		return
	}
	if result["status"] == "CONFIRMED" && (result["transactionValid"] != true || result["metadataMatches"] != true) {
		result["status"], result["errorCode"] = "PENDING_VERIFICATION", "DID_CONFIRMATION_INCOMPLETE"
	}
	km.DidOnchain = result
}
