# Security Test Plan

## Scope

1. Generate system algorithm and payload attacks
2. Update and revoke system attacks
3. Login and traffic protection verification
4. Browser embedding and clickjacking verification

## Current Baseline

1. Generate and updatedel Java backends already enable `SmartSecurityFilter`
2. Login retry lock in updatedel is configured in `kms-updatedel/java-backend/ruoyi-admin/src/main/resources/application.yml` as `maxRetryCount=5` and `lockTime=10`
3. `X-Frame-Options` is currently `SAMEORIGIN`, not full deny
4. Updatedel and generate now both support internal token forwarding to Go backends
5. Acceptance runtime consumes the copied script at `kms-ops/runtime/acceptance-go/security/security_test.sh`, sourced from the repository root `security/security_test.sh`

## Automated Security Range (Acceptance UI)

All attacks below are fully integrated into the `kms-acceptance` UI and driven by `security/security_test.sh`.

### Crypto Algorithm Core (Generate 3 Attacks)

1. **Algorithm Tampering:** Tamper attack on public key, length, and prefix (Invalid Curve/Formats)
2. **Weak Parameter:** Downgrade to weak algorithms (MD5, RSA-512) or empty encryption types
3. **Malformed Payload:** Corrupted structures causing parser errors (non-hex, over-length boundaries)

### Update and Revoke (Lifecycle 5 Attacks)

1. **SQL Injection:** Payloads against key query and record query inputs
2. **XSS:** Payload submission on editable key metadata
3. **Scanner Detection:** Malicious User-Agent detection (sqlmap, nikto) and IP blacklisting
4. **Brute Force:** Login retry lockout mechanism verification
5. **Clickjacking:** `X-Frame-Options` and CSP `frame-ancestors` verification across endpoints

*Note: The platform protection attacks (Scanner and Brute Force) execute in **Safe Mode**. They hit the `kms-updatedel` Java backend to trigger the defense, then immediately call `/internal/lifecycle/security/reset-blacklist` and `/internal/lifecycle/security/reset-login-lock` to clear the state, ensuring the system remains usable for subsequent demonstrations.*

## Expected Results

1. **Algorithm Tampering:** Tampered public key, invalid lengths, and unregistered prefixes must be directly rejected by the cryptographic library.
2. **Weak Parameter:** Lower-than-standard bit sizes or deprecated algorithms should fail to generate.
3. **Malformed Validation:** Bad inputs should be cleanly intercepted via Type/Parse errors without affecting system stability.
4. **Platform Defenses:** Scanners should be immediately blocked with 403. Brute force attempts should be locked after 5 failures.
5. **SmartSecurityFilter Window:** Scanner-style traffic should enter a 30-minute blacklist, while abnormal access pattern detection is based on a 5-minute statistics window with 404/403 thresholds.

## Follow-Up Enhancements

1. Add structured security regression script outputs for CI

---

## Archived Scenarios

The following attacks are fully implemented in `security_test.sh` but are currently archived and not exposed in the UI, as they target deeper business logic boundaries outside the primary algorithm and lifecycle scopes:

- **Generate Replay:** Replaying ENROLL_KEY requests
- **Generate Privilege:** Accessing foreign generation keys
- **Lifecycle Replay:** Replaying UPDATE_KEY requests
- **Lifecycle Tamper:** Modifying foreign key metadata
- **Lifecycle Privilege:** Accessing foreign lifecycle keys
