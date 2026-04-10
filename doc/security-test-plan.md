# Security Test Plan

## Scope

1. Generate system attacks
2. Update and revoke system attacks
3. Login and traffic protection verification
4. Browser embedding and clickjacking verification

## Current Baseline

1. Generate and updatedel Java backends already enable `SmartSecurityFilter`
2. Login retry lock is configured as `maxRetryCount=5` and `lockTime=10`
3. `X-Frame-Options` is currently `SAMEORIGIN`, not full deny
4. Updatedel and generate now both support internal token forwarding to Go backends

## Automated Checks

Use `security/security_test.ps1` with explicit environment values.

1. Scanner User-Agent probe
2. Login brute-force simulation
3. Clickjacking header check
4. Internal interface smoke check

## Semi-Automated Business Attacks

### Generate

1. SQL injection payloads against query and form parameters
2. XSS payload submission and replay
3. Replay attack using captured generate request
4. Tamper attack on public key, length, and prefix
5. Privilege escalation with normal user token

### Update and Revoke

1. SQL injection payloads against key query and record query inputs
2. XSS payload submission on editable key metadata
3. Replay attack on update and revoke requests
4. Tamper attack on `keyId`, `user`, and body fields
5. Privilege escalation by operating on foreign keys

## Browser-Side Manual Steps

1. Login as `testuser`
2. Open DevTools network tab
3. Capture generate request and copy as cURL
4. Replay the request after delay in Postman
5. Modify body parameters and resend
6. Validate whether the response is rejected and whether the record is created or changed

## Expected Results

1. Scanner UA should be blocked with `403`
2. Sixth login attempt after five failures should still be blocked during lock window
3. Replay requests should not create repeated effective business results
4. Tampered public key and malformed body should be rejected
5. Normal user tokens should not access admin-only or foreign-user resources
6. Clickjacking validation should currently show `SAMEORIGIN`; if the requirement becomes strict anti-framing, backend headers must be tightened later

## Follow-Up Enhancements

1. Add dedicated replay-id or nonce validation for critical generate and lifecycle mutations
2. Tighten `X-Frame-Options` or add CSP `frame-ancestors 'none'` if full anti-clickjacking is required
3. Add structured security regression script outputs for CI
