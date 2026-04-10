[CmdletBinding()]
param(
    [string]$VaultName = "aigov-kv",
    [string]$ComposeFile = "docker-compose.yml",
    [string[]]$Services,
    [switch]$Build,
    [switch]$ForceRecreate,
    [switch]$NoDetach
)

$ErrorActionPreference = "Stop"

function Get-SecretValue {
    param([Parameter(Mandatory = $true)][string]$Name)

    $value = az keyvault secret show --vault-name $VaultName --name $Name --query value -o tsv 2>$null
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Failed to resolve secret '$Name' from Key Vault '$VaultName'."
    }

    return $value.Trim()
}

function Set-EnvFromSecret {
    param(
        [Parameter(Mandatory = $true)][string]$EnvVar,
        [Parameter(Mandatory = $true)][string]$SecretName,
        [hashtable]$OriginalEnv
    )

    $OriginalEnv[$EnvVar] = [Environment]::GetEnvironmentVariable($EnvVar, "Process")
    $secretValue = Get-SecretValue -Name $SecretName
    [Environment]::SetEnvironmentVariable($EnvVar, $secretValue, "Process")
}

$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path
$composePath = Join-Path $repoRoot $ComposeFile

if (-not (Test-Path $composePath)) {
    throw "Compose file not found: $composePath"
}

Write-Host "[secure-start] Verifying Azure CLI login..."
$null = az account show --only-show-errors

$original = @{}
try {
    Write-Host "[secure-start] Pulling secrets from Key Vault '$VaultName'..."
    Set-EnvFromSecret -EnvVar "AZURE_TENANT_ID" -SecretName "aigov-tenant-id" -OriginalEnv $original
    Set-EnvFromSecret -EnvVar "AZURE_CLIENT_ID" -SecretName "aigov-client-id" -OriginalEnv $original
    Set-EnvFromSecret -EnvVar "AZURE_CLIENT_SECRET" -SecretName "aigov-client-secret" -OriginalEnv $original
    Set-EnvFromSecret -EnvVar "AZURE_OPENAI_API_KEY" -SecretName "aigov-openai-key" -OriginalEnv $original
    Set-EnvFromSecret -EnvVar "AZURE_SEARCH_KEY" -SecretName "aigov-search-key" -OriginalEnv $original
    Set-EnvFromSecret -EnvVar "SERVICE_BUS_CONNECTION_STRING" -SecretName "aigov-servicebus-connection-string" -OriginalEnv $original

    $composeArgs = @("compose", "-f", $composePath, "up")
    if (-not $NoDetach) { $composeArgs += "-d" }
    if ($Build) { $composeArgs += "--build" }
    if ($ForceRecreate) { $composeArgs += "--force-recreate" }

    if ($Services -and $Services.Count -gt 0) {
        $normalizedServices = @($Services | ForEach-Object { ($_ -split ",") } | ForEach-Object { $_.Trim() } | Where-Object { $_ })
        if ($normalizedServices.Count -eq 0) {
            throw "-Services was provided but no valid service names were found."
        }
        $composeArgs += $normalizedServices
        Write-Host "[secure-start] Target services: $($normalizedServices -join ', ')"
    }

    Write-Host "[secure-start] Starting Docker services from $composePath ..."
    & docker @composeArgs
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }

    Write-Host "[secure-start] Done. Secrets were injected for this process only."
}
finally {
    foreach ($entry in $original.GetEnumerator()) {
        [Environment]::SetEnvironmentVariable($entry.Key, $entry.Value, "Process")
    }
}

