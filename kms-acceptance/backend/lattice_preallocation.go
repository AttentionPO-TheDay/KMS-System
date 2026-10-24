package main

import (
	"bytes"
	"context"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"io"
	"net/http"
	"net/url"
	"strings"
	"time"

	"github.com/gofiber/fiber/v2"
)

type latticeRequest struct {
	CaseID        string `json:"caseId"`
	RootID        string `json:"rootId,omitempty"`
	NodeID        string `json:"nodeId,omitempty"`
	PreparationID string `json:"preparationId,omitempty"`
	Count         int    `json:"count,omitempty"`
	Workers       int    `json:"workers,omitempty"`
}

func validLatticeRequest(body []byte) bool {
	var request latticeRequest
	if decodeStrictJSON(body, &request) != nil {
		return false
	}
	var fields map[string]json.RawMessage
	if json.Unmarshal(body, &fields) != nil {
		return false
	}
	switch request.CaseID {
	case "offline-trapdoor":
		return len(fields) == 1
	case "basis-delegation":
		return len(fields) == 3 && len(request.RootID) == 36 && len(request.NodeID) > 0 && len(request.NodeID) <= 64
	case "parallel-sampling":
		return len(fields) == 4 && len(request.PreparationID) == 36 &&
			(request.Count == 16 || request.Count == 32 || request.Count == 64) &&
			(request.Workers == 1 || request.Workers == 2 || request.Workers == 4 || request.Workers == 8)
	}
	return false
}

// All requests retain the existing Demo ADMIN/revision/CSRF/lease boundary.
// The browser cannot select an internal destination or send a success result.
func (g *demoGuard) latticeRPC(c *fiber.Ctx, session string) error {
	endpoint, err := url.Parse(g.server.cfg.PreallocationEvidenceURL)
	if err != nil || endpoint.Host == "" || !strings.HasSuffix(endpoint.Path, "/preallocation-evidence/") || g.server.cfg.GenerateInternalToken == "" {
		return c.Status(503).JSON(fiber.Map{"message": "格预分配内部服务未配置"})
	}
	endpoint.Path = strings.TrimSuffix(endpoint.Path, "preallocation-evidence/") + "lattice/"
	endpoint.RawQuery, endpoint.Fragment = "", ""
	owner := sha256.Sum256([]byte(session))
	ctx, cancel := context.WithTimeout(context.Background(), 90*time.Second)
	defer cancel()
	req, err := http.NewRequestWithContext(ctx, c.Method(), endpoint.String(), bytes.NewReader(c.Body()))
	if err != nil {
		return c.SendStatus(503)
	}
	req.Header.Set("Content-Type", "application/json")
	req.Header.Set("X-Internal-Token", g.server.cfg.GenerateInternalToken)
	req.Header.Set("X-Acceptance-Owner", hex.EncodeToString(owner[:]))
	client := *g.server.client
	client.Timeout = 90 * time.Second
	response, err := client.Do(req)
	if err != nil {
		return c.Status(503).JSON(fiber.Map{"message": "格预分配服务暂时不可用"})
	}
	defer response.Body.Close()
	var payload struct {
		Code int             `json:"code"`
		Msg  string          `json:"msg"`
		Data json.RawMessage `json:"data"`
	}
	if json.NewDecoder(io.LimitReader(response.Body, 8<<20)).Decode(&payload) != nil {
		return c.Status(503).JSON(fiber.Map{"message": "格预分配服务返回无效"})
	}
	if response.StatusCode != 200 || payload.Code != 200 {
		status := 503
		if response.StatusCode == 400 {
			status = 400
		}
		return c.Status(status).JSON(fiber.Map{"message": payload.Msg})
	}
	c.Set("Cache-Control", "no-store")
	return c.JSON(fiber.Map{"data": payload.Data})
}
