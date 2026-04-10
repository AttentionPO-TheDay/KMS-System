param(
    [string]$CaseId = "",
    [string]$GenerateGoBaseUrl = "http://127.0.0.1:8081",
    [string]$LifecycleGoBaseUrl = "http://127.0.0.1:8082",
    [string]$GenerateJavaBaseUrl = "http://127.0.0.1:9081",
    [string]$LifecycleJavaBaseUrl = "http://127.0.0.1:9082",
    [string]$GenerateKeyPoolUrl = "http://127.0.0.1:9081/internal/generate/keys/recent",
    [string]$LifecycleVerifyUrl = "http://127.0.0.1:9082/internal/lifecycle/key-status",
    [string]$InternalToken = "kms-generate-internal-secret-2026",
    [string]$AcceptanceUser = "acceptance_user",
    [string]$AttackUserName = "acceptance_user",
    [string]$AttackUserPassword = "",
    [string]$AttackAdminName = "admin",
    [string]$AttackAdminPassword = "",
    [string]$AttackForeignUser = "admin",
    [switch]$Json
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$ValidUa = "04e5df58dcdd1d8bba99bc62b825fd1abbb8b4c2d32aa4ed79f48bb5b1dd2e14e09f5d47296df715dd748951b6e22805b0e71bfd4097e7db93cd6528cb68870f2a"
$GenerateType = "CERTLESS"

function New-RunResult {
    param([string]$CurrentCaseId)

    return [ordered]@{
        caseId = $CurrentCaseId
        status = "completed"
        verdict = "blocked"
        passed = $true
        summary = ""
        error = ""
        notes = New-Object System.Collections.Generic.List[string]
        requests = New-Object System.Collections.Generic.List[object]
    }
}

function Add-Trace {
    param(
        [hashtable]$Result,
        [string]$Name,
        [string]$Method,
        [string]$Url,
        [int]$StatusCode,
        [string]$Outcome,
        [string]$Message,
        [string]$ResponseBody
    )

    $snippet = ""
    if ($null -ne $ResponseBody) {
        $snippet = [string]$ResponseBody
        if ($snippet.Length -gt 400) {
            $snippet = $snippet.Substring(0, 400)
        }
    }

    $Result.requests.Add([ordered]@{
        name = $Name
        method = $Method
        url = $Url
        statusCode = $StatusCode
        outcome = $Outcome
        message = $Message
        responseBody = $snippet
    }) | Out-Null
}

function Invoke-HttpRequest {
    param(
        [string]$Method,
        [string]$Url,
        [hashtable]$Headers,
        [object]$Body
    )

    $requestHeaders = @{}
    if ($Headers) {
        foreach ($key in $Headers.Keys) {
            $requestHeaders[$key] = $Headers[$key]
        }
    }

    $invokeParams = @{
        Method = $Method
        Uri = $Url
        Headers = $requestHeaders
        UseBasicParsing = $true
    }

    if ($null -ne $Body) {
        $bodyText = if ($Body -is [string]) { $Body } else { $Body | ConvertTo-Json -Depth 10 -Compress }
        $invokeParams["ContentType"] = "application/json"
        $invokeParams["Body"] = $bodyText
    }

    try {
        $response = Invoke-WebRequest @invokeParams
        return [ordered]@{
            StatusCode = [int]$response.StatusCode
            Body = [string]$response.Content
            Headers = $response.Headers
        }
    } catch {
        $webResponse = $_.Exception.Response
        if ($null -eq $webResponse) {
            throw
        }

        $body = ""
        $stream = $webResponse.GetResponseStream()
        if ($stream) {
            $reader = New-Object System.IO.StreamReader($stream)
            $body = $reader.ReadToEnd()
            $reader.Dispose()
        }

        return [ordered]@{
            StatusCode = [int]$webResponse.StatusCode
            Body = [string]$body
            Headers = $webResponse.Headers
        }
    }
}

function Get-JsonBody {
    param([string]$Body)

    if ([string]::IsNullOrWhiteSpace($Body)) {
        return $null
    }

    try {
        return $Body | ConvertFrom-Json
    } catch {
        return $null
    }
}

function Get-ListRows {
    param([object]$Payload)

    if ($null -eq $Payload) {
        return @()
    }
    if ($Payload.rows) {
        return @($Payload.rows)
    }
    if ($Payload.data) {
        return @($Payload.data)
    }
    return @()
}

function Test-AjaxDenied {
    param([object]$Payload)

    if ($null -eq $Payload) {
        return $false
    }

    $message = ""
    if ($Payload.msg) {
        $message = [string]$Payload.msg
    }
    return ($Payload.code -ne 200) -or $message.Contains("deny") -or $message.Contains("forbid") -or $message.Contains("no permission") -or $message.Contains("wu quan")
}

function Require-Credentials {
    param(
        [string]$UserName,
        [string]$Password,
        [string]$Label
    )

    if ([string]::IsNullOrWhiteSpace($UserName) -or [string]::IsNullOrWhiteSpace($Password)) {
        throw "missing credentials for $Label"
    }
}

function Get-AuthToken {
    param(
        [string]$BaseUrl,
        [string]$UserName,
        [string]$Password,
        [hashtable]$Result,
        [string]$TraceName
    )

    Require-Credentials -UserName $UserName -Password $Password -Label $TraceName

    $captchaUrl = "$BaseUrl/captchaImage"
    $captchaResponse = Invoke-HttpRequest -Method "GET" -Url $captchaUrl -Headers @{} -Body $null
    Add-Trace -Result $Result -Name "$TraceName captcha" -Method "GET" -Url $captchaUrl -StatusCode $captchaResponse.StatusCode -Outcome "captcha" -Message "load captcha config" -ResponseBody $captchaResponse.Body
    $captchaPayload = Get-JsonBody $captchaResponse.Body
    if ($null -eq $captchaPayload) {
        throw "$TraceName captcha response is not json"
    }
    if ($captchaPayload.captchaEnabled -eq $true) {
        throw "$TraceName requires captcha disabled"
    }

    $loginUrl = "$BaseUrl/login"
    $loginResponse = Invoke-HttpRequest -Method "POST" -Url $loginUrl -Headers @{} -Body @{
        username = $UserName
        password = $Password
        code = ""
        uuid = ""
    }
    Add-Trace -Result $Result -Name "$TraceName login" -Method "POST" -Url $loginUrl -StatusCode $loginResponse.StatusCode -Outcome "login" -Message $UserName -ResponseBody $loginResponse.Body
    $loginPayload = Get-JsonBody $loginResponse.Body
    if ($loginResponse.StatusCode -ge 400 -or $null -eq $loginPayload -or [string]::IsNullOrWhiteSpace([string]$loginPayload.token)) {
        throw "$TraceName login failed"
    }
    return [string]$loginPayload.token
}

function Get-InternalRecentKeys {
    param(
        [string]$UserName,
        [int]$Limit,
        [string]$CreatedAfter
    )

    $uri = "$GenerateKeyPoolUrl?userName=$([uri]::EscapeDataString($UserName))&limit=$Limit"
    if (-not [string]::IsNullOrWhiteSpace($CreatedAfter)) {
        $uri += "&createdAfter=$([uri]::EscapeDataString($CreatedAfter))"
    }

    $response = Invoke-HttpRequest -Method "GET" -Url $uri -Headers @{ "X-Internal-Token" = $InternalToken } -Body $null
    $payload = Get-JsonBody $response.Body
    if ($response.StatusCode -ge 400 -or $null -eq $payload) {
        throw "recent key query failed"
    }
    return @($payload.data)
}

function Get-OwnedLifecycleKeyId {
    param(
        [string]$Token,
        [hashtable]$Result
    )

    $url = "$LifecycleJavaBaseUrl/lifecycle/keymanage/list?pageNum=1&pageSize=1"
    $response = Invoke-HttpRequest -Method "GET" -Url $url -Headers @{ "Authorization" = "Bearer $Token" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle own list" -Method "GET" -Url $url -StatusCode $response.StatusCode -Outcome "query" -Message "load own key" -ResponseBody $response.Body
    $payload = Get-JsonBody $response.Body
    $rows = Get-ListRows $payload
    if ($rows.Count -lt 1) {
        throw "no lifecycle key for attack user"
    }
    return [long]$rows[0].keyId
}

function Run-GenerateReplay {
    param([hashtable]$Result)

    $started = (Get-Date).ToUniversalTime().ToString("o")
    $url = "$GenerateGoBaseUrl/generate/request/ENROLL_KEY"
    $headers = @{ "X-Internal-Token" = $InternalToken }
    $body = @{
        user = $AcceptanceUser
        encryt_type = $GenerateType
        encryt_name = "SSCL"
        ua = $ValidUa
        key_domain = "acceptance"
        key_name = "attack-replay"
        key_use = "security"
        auto_update = "false"
    }

    $first = Invoke-HttpRequest -Method "POST" -Url $url -Headers $headers -Body $body
    Add-Trace -Result $Result -Name "generate replay first" -Method "POST" -Url $url -StatusCode $first.StatusCode -Outcome "mutation" -Message "first request" -ResponseBody $first.Body

    Start-Sleep -Seconds 1

    $second = Invoke-HttpRequest -Method "POST" -Url $url -Headers $headers -Body $body
    Add-Trace -Result $Result -Name "generate replay second" -Method "POST" -Url $url -StatusCode $second.StatusCode -Outcome "mutation" -Message "replayed request" -ResponseBody $second.Body

    Start-Sleep -Seconds 4
    $recent = Get-InternalRecentKeys -UserName $AcceptanceUser -Limit 10 -CreatedAfter $started
    $createdCount = @($recent).Count
    $acceptedCount = 0
    if ($first.StatusCode -lt 400) { $acceptedCount++ }
    if ($second.StatusCode -lt 400) { $acceptedCount++ }

    if ($acceptedCount -ge 2 -and $createdCount -ge 2) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Generate replay was accepted twice and produced multiple fresh keys."
    } else {
        $Result.summary = "Generate replay did not produce two effective results."
    }
    $Result.notes.Add("recentGenerated=$createdCount") | Out-Null
}

function Run-GenerateTamper {
    param([hashtable]$Result)

    $url = "$GenerateGoBaseUrl/generate/request/ENROLL_KEY"
    $headers = @{ "X-Internal-Token" = $InternalToken }
    $cases = @(
        @{ name = "empty-ua"; body = @{ user = $AcceptanceUser; encryt_type = $GenerateType; encryt_name = "SSCL"; ua = ""; key_domain = "acceptance"; key_name = "tamper-empty"; key_use = "attack"; auto_update = "false" } },
        @{ name = "short-ua"; body = @{ user = $AcceptanceUser; encryt_type = $GenerateType; encryt_name = "SSCL"; ua = "abcd"; key_domain = "acceptance"; key_name = "tamper-short"; key_use = "attack"; auto_update = "false" } },
        @{ name = "bad-prefix"; body = @{ user = $AcceptanceUser; encryt_type = $GenerateType; encryt_name = "SSCL"; ua = ("05" + $ValidUa.Substring(2)); key_domain = "acceptance"; key_name = "tamper-prefix"; key_use = "attack"; auto_update = "false" } }
    )

    $accepted = 0
    foreach ($item in $cases) {
        $response = Invoke-HttpRequest -Method "POST" -Url $url -Headers $headers -Body $item.body
        Add-Trace -Result $Result -Name "generate tamper $($item.name)" -Method "POST" -Url $url -StatusCode $response.StatusCode -Outcome "tamper" -Message $item.name -ResponseBody $response.Body
        $payload = Get-JsonBody $response.Body
        if ($response.StatusCode -lt 400 -and ($null -eq $payload -or $payload.code -eq 200)) {
            $accepted++
        }
    }

    if ($accepted -gt 0) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Tampered generate input was still accepted by the system."
    } else {
        $Result.summary = "Tampered generate input was rejected."
    }
    $Result.notes.Add("acceptedTamperRequests=$accepted") | Out-Null
}

function Run-GeneratePrivilege {
    param([hashtable]$Result)

    $token = Get-AuthToken -BaseUrl $GenerateJavaBaseUrl -UserName $AttackUserName -Password $AttackUserPassword -Result $Result -TraceName "generate normal user"
    $foreignKeys = Get-InternalRecentKeys -UserName $AttackForeignUser -Limit 1 -CreatedAfter ""
    if (@($foreignKeys).Count -lt 1) {
        throw "no foreign generate key found"
    }

    $foreignKeyId = [long]$foreignKeys[0].keyId
    $url = "$GenerateJavaBaseUrl/generate/key/$foreignKeyId"
    $response = Invoke-HttpRequest -Method "GET" -Url $url -Headers @{ "Authorization" = "Bearer $token" } -Body $null
    Add-Trace -Result $Result -Name "generate foreign detail" -Method "GET" -Url $url -StatusCode $response.StatusCode -Outcome "privilege" -Message "normal user reads foreign key" -ResponseBody $response.Body
    $payload = Get-JsonBody $response.Body

    if ($response.StatusCode -lt 400 -and -not (Test-AjaxDenied $payload) -and $payload.data) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Normal user read a foreign generate key detail."
    } else {
        $Result.summary = "Normal user could not read a foreign generate key detail."
    }
}

function Run-LifecycleSql {
    param([hashtable]$Result)

    $token = Get-AuthToken -BaseUrl $LifecycleJavaBaseUrl -UserName $AttackUserName -Password $AttackUserPassword -Result $Result -TraceName "lifecycle normal user"
    $keyPayload = [uri]::EscapeDataString("' OR 1=1 -- kms_sql_test")
    $recordPayload = [uri]::EscapeDataString("' OR '1'='1 kms_sql_test")

    $keyUrl = "$LifecycleJavaBaseUrl/lifecycle/keymanage/list?pageNum=1&pageSize=10&keyName=$keyPayload"
    $keyResponse = Invoke-HttpRequest -Method "GET" -Url $keyUrl -Headers @{ "Authorization" = "Bearer $token" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle sql key-list" -Method "GET" -Url $keyUrl -StatusCode $keyResponse.StatusCode -Outcome "sql-injection" -Message "inject keyName" -ResponseBody $keyResponse.Body
    $keyRows = Get-ListRows (Get-JsonBody $keyResponse.Body)

    $recordUrl = "$LifecycleJavaBaseUrl/lifecycle/operation-record/list?pageNum=1&pageSize=10&actionType=$recordPayload"
    $recordResponse = Invoke-HttpRequest -Method "GET" -Url $recordUrl -Headers @{ "Authorization" = "Bearer $token" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle sql record-list" -Method "GET" -Url $recordUrl -StatusCode $recordResponse.StatusCode -Outcome "sql-injection" -Message "inject actionType" -ResponseBody $recordResponse.Body
    $recordRows = Get-ListRows (Get-JsonBody $recordResponse.Body)

    $sqlError = ($keyResponse.StatusCode -ge 500) -or ($recordResponse.StatusCode -ge 500) -or $keyResponse.Body.Contains("SQL") -or $recordResponse.Body.Contains("SQL")
    if ($sqlError -or $keyRows.Count -gt 0 -or $recordRows.Count -gt 0) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "SQL injection probe returned data or triggered server-side SQL errors."
    } else {
        $Result.summary = "SQL injection probe returned no data and no SQL error."
    }
}

function Run-LifecycleXss {
    param([hashtable]$Result)

    $token = Get-AuthToken -BaseUrl $LifecycleJavaBaseUrl -UserName $AttackUserName -Password $AttackUserPassword -Result $Result -TraceName "lifecycle normal user"
    $keyId = Get-OwnedLifecycleKeyId -Token $token -Result $Result
    $payloadText = '\"><script>alert("kms-xss")</script>'
    $updateUrl = "$LifecycleJavaBaseUrl/lifecycle/keymanage"

    $updateResponse = Invoke-HttpRequest -Method "PUT" -Url $updateUrl -Headers @{ "Authorization" = "Bearer $token" } -Body @{
        keyId = $keyId
        keyName = $payloadText
        keyUse = $payloadText
        keyDomain = $payloadText
    }
    Add-Trace -Result $Result -Name "lifecycle xss update" -Method "PUT" -Url $updateUrl -StatusCode $updateResponse.StatusCode -Outcome "xss" -Message "submit payload" -ResponseBody $updateResponse.Body

    Start-Sleep -Seconds 4

    $detailUrl = "$LifecycleJavaBaseUrl/lifecycle/keymanage/$keyId"
    $detailResponse = Invoke-HttpRequest -Method "GET" -Url $detailUrl -Headers @{ "Authorization" = "Bearer $token" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle xss detail" -Method "GET" -Url $detailUrl -StatusCode $detailResponse.StatusCode -Outcome "xss" -Message "read back value" -ResponseBody $detailResponse.Body

    if ($updateResponse.StatusCode -lt 400 -and $detailResponse.Body.Contains("<script>")) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "XSS payload was accepted and returned in lifecycle detail output."
    } else {
        $Result.summary = "XSS payload was not visible in lifecycle detail output."
    }
}

function Run-LifecycleReplay {
    param([hashtable]$Result)

    $recentKeys = Get-InternalRecentKeys -UserName $AcceptanceUser -Limit 1 -CreatedAfter ""
    if (@($recentKeys).Count -lt 1) {
        throw "no lifecycle replay key found"
    }

    $keyId = [long]$recentKeys[0].keyId
    $url = "$LifecycleGoBaseUrl/lifecycle/request/UPDATE_KEY"
    $headers = @{ "X-Internal-Token" = $InternalToken }
    $body = @{ keyId = $keyId; user = $AcceptanceUser; keyName = "attack-replay-update"; keyUse = "security"; keyDomain = "acceptance"; autoUpdate = "false" }

    $first = Invoke-HttpRequest -Method "POST" -Url $url -Headers $headers -Body $body
    Add-Trace -Result $Result -Name "lifecycle replay first" -Method "POST" -Url $url -StatusCode $first.StatusCode -Outcome "mutation" -Message "first update" -ResponseBody $first.Body
    $second = Invoke-HttpRequest -Method "POST" -Url $url -Headers $headers -Body $body
    Add-Trace -Result $Result -Name "lifecycle replay second" -Method "POST" -Url $url -StatusCode $second.StatusCode -Outcome "mutation" -Message "replayed update" -ResponseBody $second.Body

    $secondPayload = Get-JsonBody $second.Body
    $isBlocked = ($secondPayload -and [string]$secondPayload.status -eq "duplicate") -or $second.Body.Contains("duplicate") -or $second.Body.Contains("do not")
    if (-not $isBlocked -and $second.StatusCode -lt 400) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Lifecycle update replay was not flagged as duplicate."
    } else {
        $Result.summary = "Lifecycle update replay was blocked as duplicate."
    }
}

function Run-LifecycleTamper {
    param([hashtable]$Result)

    $adminToken = Get-AuthToken -BaseUrl $LifecycleJavaBaseUrl -UserName $AttackAdminName -Password $AttackAdminPassword -Result $Result -TraceName "lifecycle admin"
    $foreignKeys = Get-InternalRecentKeys -UserName $AttackForeignUser -Limit 1 -CreatedAfter ""
    if (@($foreignKeys).Count -lt 1) {
        throw "no foreign lifecycle key found"
    }

    $foreignKeyId = [long]$foreignKeys[0].keyId
    $detailUrl = "$LifecycleJavaBaseUrl/lifecycle/keymanage/$foreignKeyId"
    $before = Invoke-HttpRequest -Method "GET" -Url $detailUrl -Headers @{ "Authorization" = "Bearer $adminToken" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle tamper before" -Method "GET" -Url $detailUrl -StatusCode $before.StatusCode -Outcome "read" -Message "before tamper" -ResponseBody $before.Body

    $tamperUrl = "$LifecycleGoBaseUrl/lifecycle/request/UPDATE_KEY"
    $tamper = Invoke-HttpRequest -Method "POST" -Url $tamperUrl -Headers @{ "X-Internal-Token" = $InternalToken } -Body @{
        keyId = $foreignKeyId
        user = $AttackUserName
        keyName = "tampered-by-attack"
        keyUse = "tampered"
        keyDomain = "tampered"
        autoUpdate = "true"
    }
    Add-Trace -Result $Result -Name "lifecycle tamper submit" -Method "POST" -Url $tamperUrl -StatusCode $tamper.StatusCode -Outcome "tamper" -Message "spoofed owner and metadata" -ResponseBody $tamper.Body

    Start-Sleep -Seconds 4

    $after = Invoke-HttpRequest -Method "GET" -Url $detailUrl -Headers @{ "Authorization" = "Bearer $adminToken" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle tamper after" -Method "GET" -Url $detailUrl -StatusCode $after.StatusCode -Outcome "read" -Message "after tamper" -ResponseBody $after.Body

    if ($after.Body.Contains("tampered-by-attack") -and -not $before.Body.Contains("tampered-by-attack")) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Tampered lifecycle request changed a foreign key detail."
    } else {
        $Result.summary = "Tampered lifecycle request did not change the foreign key detail."
    }
}

function Run-LifecyclePrivilege {
    param([hashtable]$Result)

    $token = Get-AuthToken -BaseUrl $LifecycleJavaBaseUrl -UserName $AttackUserName -Password $AttackUserPassword -Result $Result -TraceName "lifecycle normal user"
    $foreignKeys = Get-InternalRecentKeys -UserName $AttackForeignUser -Limit 1 -CreatedAfter ""
    if (@($foreignKeys).Count -lt 1) {
        throw "no foreign lifecycle key found"
    }

    $foreignKeyId = [long]$foreignKeys[0].keyId
    $url = "$LifecycleJavaBaseUrl/lifecycle/keymanage/$foreignKeyId"
    $response = Invoke-HttpRequest -Method "GET" -Url $url -Headers @{ "Authorization" = "Bearer $token" } -Body $null
    Add-Trace -Result $Result -Name "lifecycle foreign detail" -Method "GET" -Url $url -StatusCode $response.StatusCode -Outcome "privilege" -Message "normal user reads foreign lifecycle key" -ResponseBody $response.Body
    $payload = Get-JsonBody $response.Body

    if ($response.StatusCode -lt 400 -and -not (Test-AjaxDenied $payload) -and $payload.data) {
        $Result.verdict = "vulnerable"
        $Result.passed = $false
        $Result.summary = "Normal user read a foreign lifecycle key detail."
    } else {
        $Result.summary = "Normal user could not read a foreign lifecycle key detail."
    }
}

function Run-Case {
    param([string]$CurrentCaseId)

    $result = New-RunResult -CurrentCaseId $CurrentCaseId
    try {
        switch ($CurrentCaseId) {
            "generate-replay" { Run-GenerateReplay -Result $result }
            "generate-tamper" { Run-GenerateTamper -Result $result }
            "generate-privilege" { Run-GeneratePrivilege -Result $result }
            "lifecycle-sql" { Run-LifecycleSql -Result $result }
            "lifecycle-xss" { Run-LifecycleXss -Result $result }
            "lifecycle-replay" { Run-LifecycleReplay -Result $result }
            "lifecycle-tamper" { Run-LifecycleTamper -Result $result }
            "lifecycle-privilege" { Run-LifecyclePrivilege -Result $result }
            default { throw "unknown case id: $CurrentCaseId" }
        }
    } catch {
        $result.status = "error"
        $result.verdict = "error"
        $result.passed = $false
        $result.error = [string]$_.Exception.Message
        if ([string]::IsNullOrWhiteSpace($result.summary)) {
            $result.summary = "attack execution failed"
        }
    }

    return $result
}

if ([string]::IsNullOrWhiteSpace($CaseId)) {
    throw "CaseId is required"
}

$final = Run-Case -CurrentCaseId $CaseId

if ($Json) {
    $output = "" | Select-Object caseId, status, verdict, passed, summary, error, notes, requests
    $output.caseId = [string]$final.caseId
    $output.status = [string]$final.status
    $output.verdict = [string]$final.verdict
    $output.passed = [bool]$final.passed
    $output.summary = [string]$final.summary
    $output.error = [string]$final.error
    $output.notes = $final.notes.ToArray()
    $output.requests = $final.requests.ToArray()
    $output | ConvertTo-Json -Depth 10 -Compress
} else {
    $final | ConvertTo-Json -Depth 10
}
