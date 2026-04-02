<#
.SYNOPSIS
    Adds OAuth2 permission scopes to an Entra app registration via Microsoft Graph API PATCH.

.DESCRIPTION
    Reads new scope definitions from scopes.json, merges them with any existing
    oauth2PermissionScopes on the target application, then issues a single PATCH
    to avoid clobbering existing scopes.

.PARAMETER TenantId
    Entra tenant ID. Defaults to the value in this script.

.PARAMETER AppId
    Application (client) ID of the app registration to update.

.EXAMPLE
    # Interactive login (prompts for credentials)
    .\Add-AppScopes.ps1

    # Non-interactive using a service principal
    $env:AZURE_CLIENT_ID     = "..."
    $env:AZURE_CLIENT_SECRET = "..."
    .\Add-AppScopes.ps1
#>
param(
    [string] $TenantId = "4db4e22f-83ed-4093-8d8a-c73b1e559459",
    [string] $AppId    = "5ffe8f56-2bc8-4430-83a3-c01c1de14524"
)

Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

# ---------------------------------------------------------------------------
# 1. Acquire an access token for Microsoft Graph
# ---------------------------------------------------------------------------
function Get-GraphToken {
    param([string] $TenantId)

    if ($env:AZURE_CLIENT_ID -and $env:AZURE_CLIENT_SECRET) {
        Write-Host "Authenticating with service principal..."
        $body = @{
            grant_type    = "client_credentials"
            client_id     = $env:AZURE_CLIENT_ID
            client_secret = $env:AZURE_CLIENT_SECRET
            scope         = "https://graph.microsoft.com/.default"
        }
        $response = Invoke-RestMethod `
            -Uri    "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token" `
            -Method Post `
            -Body   $body
        return $response.access_token
    }

    Write-Host "Acquiring token via 'az account get-access-token'..."
    $azToken = az account get-access-token `
        --tenant $TenantId `
        --resource https://graph.microsoft.com `
        --query accessToken -o tsv 2>&1

    if ($LASTEXITCODE -ne 0) {
        throw "Failed to get token via az CLI. Run 'az login' first, or set AZURE_CLIENT_ID / AZURE_CLIENT_SECRET."
    }
    return $azToken.Trim()
}

# ---------------------------------------------------------------------------
# 2. Get existing oauth2PermissionScopes from the app registration
# ---------------------------------------------------------------------------
function Get-ExistingScopes {
    param([string] $Token, [string] $AppId)

    $uri = "https://graph.microsoft.com/v1.0/applications(appId='$AppId')?`$select=id,api"
    $headers = @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" }

    $app = Invoke-RestMethod -Uri $uri -Headers $headers -Method Get
    Write-Host "Fetched app object ID: $($app.id)"

    $scopes = $app.api.oauth2PermissionScopes
    if ($null -eq $scopes) { return @() }
    return $scopes
}

# ---------------------------------------------------------------------------
# 3. Merge new scopes (skip any whose 'value' already exists)
# ---------------------------------------------------------------------------
function Merge-Scopes {
    param($Existing, $New)

    $merged = New-Object System.Collections.Generic.List[object]
    foreach ($s in $Existing) { $merged.Add($s) }

    foreach ($scope in $New) {
        $duplicate = $merged | Where-Object { $_.value -eq $scope.value }
        if ($duplicate) {
            Write-Warning "Scope '$($scope.value)' already exists - skipping."
        } else {
            $merged.Add($scope)
            Write-Host "  + Adding scope: $($scope.value)"
        }
    }
    return $merged
}

# ---------------------------------------------------------------------------
# 4. PATCH the application with the merged scope list
# ---------------------------------------------------------------------------
function Set-AppScopes {
    param([string] $Token, [string] $AppId, $Scopes)

    $uri     = "https://graph.microsoft.com/v1.0/applications(appId='$AppId')"
    $headers = @{ Authorization = "Bearer $Token"; "Content-Type" = "application/json" }
    $body    = @{ api = @{ oauth2PermissionScopes = @($Scopes) } } | ConvertTo-Json -Depth 6

    Invoke-RestMethod -Uri $uri -Headers $headers -Method Patch -Body $body
    Write-Host "PATCH succeeded - scopes updated on app $AppId"
}

# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
$scopesFile = Join-Path $PSScriptRoot "scopes.json"

if (-not (Test-Path $scopesFile)) {
    throw "scopes.json not found at: $scopesFile"
}

$newScopes = Get-Content $scopesFile -Raw | ConvertFrom-Json

Write-Host ""
Write-Host "Target tenant : $TenantId"
Write-Host "Target app ID : $AppId"
Write-Host "New scopes    : $($newScopes.value -join ', ')"
Write-Host ""

$token          = Get-GraphToken -TenantId $TenantId
$existingScopes = Get-ExistingScopes -Token $token -AppId $AppId
$mergedScopes   = Merge-Scopes -Existing $existingScopes -New $newScopes

Set-AppScopes -Token $token -AppId $AppId -Scopes $mergedScopes
