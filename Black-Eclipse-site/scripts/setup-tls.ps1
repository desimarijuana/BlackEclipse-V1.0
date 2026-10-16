# Provisions a locally-trusted HTTPS certificate for the BlackEclipse local
# hostname (default `blackeclipse`), so `https://blackeclipse` becomes a SECURE
# CONTEXT. That is what the browser's Web Notification API (the desktop
# notifications in Settings > Alerts/Notifications), service workers and other
# powerful features require — the plain-http hosts-file alias is not one.
#
# What it does (idempotent, NO Administrator needed):
#   1. Creates a self-signed certificate for the hostname in the CURRENT USER's
#      personal store (Cert:\CurrentUser\My).
#   2. Exports it as PKCS#12 (.pfx) plus a passphrase file under
#      `.black-eclipse/certs/` (gitignored) — what the Node reverse proxy reads.
#   3. Marks the certificate trusted by importing it into the CURRENT USER's
#      trusted root store (Cert:\CurrentUser\Root), so Chrome/Edge accept
#      https://blackeclipse without a warning.
#
#   npm run setup:tls                    # create / refresh the certificate
#   powershell -File scripts/setup-tls.ps1 -Name myhost
#   npm run tls:remove                   # remove the certificate + files
#
# Chrome and Edge validate against the Windows trust store, so they trust this
# automatically. Firefox keeps its own store: either set
# `security.enterprise_roots.enabled = true`, or use Chrome/Edge for desktop
# notifications.

param(
    [string]$Name = "blackeclipse",
    [switch]$Uninstall
)

$ErrorActionPreference = "Stop"

$root     = Split-Path $PSScriptRoot -Parent
$certDir  = Join-Path $root ".black-eclipse\certs"
$pfxPath  = Join-Path $certDir "$Name.pfx"
$crtPath  = Join-Path $certDir "$Name.crt"
$passPath = Join-Path $certDir "$Name.pass"
$friendly = "BlackEclipse local HTTPS ($Name)"

function Get-BeCerts {
    Get-ChildItem Cert:\CurrentUser\My -ErrorAction SilentlyContinue |
        Where-Object { $_.FriendlyName -eq $friendly }
}

if ($Uninstall) {
    foreach ($cert in Get-BeCerts) {
        $thumb = $cert.Thumbprint
        Remove-Item "Cert:\CurrentUser\My\$thumb" -Force -ErrorAction SilentlyContinue
        Remove-Item "Cert:\CurrentUser\Root\$thumb" -Force -ErrorAction SilentlyContinue
        Write-Host "Removed certificate $thumb from My + Root."
    }
    if (Test-Path $certDir) {
        Remove-Item (Join-Path $certDir "$Name.*") -Force -ErrorAction SilentlyContinue
    }
    Write-Host "Done. Restart BlackEclipse; it falls back to http until a certificate exists again."
    exit 0
}

# Reuse an existing certificate + files when everything is already in place.
$existing = Get-BeCerts | Select-Object -First 1
$reuse = $false
if ($existing -and (Test-Path $pfxPath) -and (Test-Path $passPath) -and (Test-Path $crtPath)) {
    $reuse = $true
}

if ($reuse) {
    Write-Host "Certificate for '$Name' already configured (thumbprint $($existing.Thumbprint))."
} else {
    if (!(Test-Path $certDir)) { New-Item -ItemType Directory -Path $certDir -Force | Out-Null }

    # Fresh, random passphrase for the PFX (stored beside it; both gitignored).
    $pass = [guid]::NewGuid().ToString("N") + [guid]::NewGuid().ToString("N")

    # A self-signed CA:TRUE certificate that also serves TLS (serverAuth EKU +
    # SAN). A trusted root that is simultaneously the server certificate is the
    # most compatible shape for Chrome/Edge's Windows trust-store validation.
    $cert = New-SelfSignedCertificate `
        -Type Custom `
        -Subject "CN=$Name" `
        -DnsName $Name `
        -CertStoreLocation "Cert:\CurrentUser\My" `
        -KeyAlgorithm RSA `
        -KeyLength 2048 `
        -HashAlgorithm SHA256 `
        -KeyExportPolicy Exportable `
        -KeyUsageProperty All `
        -KeyUsage CertSign, CRLSign, DigitalSignature, KeyEncipherment `
        -NotAfter (Get-Date).AddYears(5) `
        -FriendlyName $friendly `
        -TextExtension @(
            "2.5.29.19={critical}{text}ca=1",
            "2.5.29.37={text}1.3.6.1.5.5.7.3.1"
        )

    $secure = ConvertTo-SecureString -String $pass -Force -AsPlainText
    Export-PfxCertificate -Cert $cert -FilePath $pfxPath -Password $secure | Out-Null
    Set-Content -Path $passPath -Value $pass -NoNewline -Encoding ascii
    Export-Certificate -Cert $cert -FilePath $crtPath | Out-Null

    Write-Host "Created certificate (thumbprint $($cert.Thumbprint))."
    $existing = $cert
}

# Trust the certificate for the current user (no Administrator needed).
#
# Uses the .NET X509Store API rather than `Import-Certificate`: importing into
# the Trusted Root store through the cmdlet raises a blocking Windows trust
# dialog (which hangs an unattended run). The store API adds silently.
$target = Get-BeCerts | Select-Object -First 1
if ($target) {
    $public = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($crtPath)
    $root = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "CurrentUser")
    $root.Open("ReadWrite")
    $already = $root.Certificates | Where-Object { $_.Thumbprint -eq $public.Thumbprint }
    if (-not $already) {
        $root.Add($public)
        Write-Host "Trusted the certificate in Cert:\CurrentUser\Root."
    } else {
        Write-Host "Certificate already trusted in Cert:\CurrentUser\Root."
    }
    $root.Close()
}

Write-Host ""
Write-Host "HTTPS is ready. Restart BlackEclipse (npm run dev) and open https://$Name"
Write-Host "Desktop notifications (Settings > Alerts/Notifications) now work on that origin."
