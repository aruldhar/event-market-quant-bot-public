<#
Creates the private, versioned S3 destination used by the terminal-only
Candidate-E evidence archiver and grants the EC2 role write-only archive access.

Run this locally with an administrator account for the AWS account, for example:
  .\deploy\provision-kxbtcd-offsite-archive.ps1 -BucketName my-private-kxbtcd-evidence -Profile grafana-tunnel
#>
[CmdletBinding()]
param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$')]
    [string]$BucketName,

    [string]$Profile = 'grafana-tunnel',
    [string]$Region = 'us-east-1',
    [string]$RoleName = 'EventMarketQuantBotEC2Role',
    [string]$Prefix = 'candidate-e'
)

$ErrorActionPreference = 'Stop'
$aws = (Get-Command aws -ErrorAction Stop).Source
$Prefix = $Prefix.Trim('/')
if ([string]::IsNullOrWhiteSpace($Prefix) -or $Prefix.Contains('..')) {
    throw 'Prefix must be a non-empty, simple S3 key prefix.'
}

function Invoke-Aws {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Arguments)
    & $aws @Arguments --profile $Profile --region $Region
    if ($LASTEXITCODE -ne 0) { throw "AWS CLI failed: $($Arguments -join ' ')" }
}

$tmp = Join-Path ([System.IO.Path]::GetTempPath()) ("kxbtcd-offsite-archive-" + [guid]::NewGuid())
New-Item -ItemType Directory -Path $tmp | Out-Null
try {
    # Do not use head-bucket here: a missing bucket produces an expected
    # nonzero response which some PowerShell configurations promote to a
    # terminating NativeCommandError.  The provisioning identity lists its
    # buckets, so a successful list is a deterministic existence probe.
    $knownBuckets = & $aws s3api list-buckets --query 'Buckets[].Name' --output text --profile $Profile --region $Region
    if ($LASTEXITCODE -ne 0) { throw 'Unable to list buckets for the provisioning profile.' }
    $bucketExists = @($knownBuckets -split '\s+') -contains $BucketName
    if (-not $bucketExists) {
        if ($Region -eq 'us-east-1') {
            Invoke-Aws s3api create-bucket --bucket $BucketName
        } else {
            Invoke-Aws s3api create-bucket --bucket $BucketName --create-bucket-configuration "LocationConstraint=$Region"
        }
    }

    Invoke-Aws s3api put-bucket-versioning --bucket $BucketName --versioning-configuration Status=Enabled
    $publicAccess = @{
        BlockPublicAcls = $true
        IgnorePublicAcls = $true
        BlockPublicPolicy = $true
        RestrictPublicBuckets = $true
    } | ConvertTo-Json -Depth 4
    $publicAccessPath = Join-Path $tmp 'public-access-block.json'
    [System.IO.File]::WriteAllText($publicAccessPath, $publicAccess, [System.Text.UTF8Encoding]::new($false))
    Invoke-Aws s3api put-public-access-block --bucket $BucketName --public-access-block-configuration ("file://" + ($publicAccessPath -replace '\\', '/'))

    $encryption = @{ Rules = @(@{ ApplyServerSideEncryptionByDefault = @{ SSEAlgorithm = 'AES256' } }) } | ConvertTo-Json -Depth 6
    $encryptionPath = Join-Path $tmp 'encryption.json'
    [System.IO.File]::WriteAllText($encryptionPath, $encryption, [System.Text.UTF8Encoding]::new($false))
    Invoke-Aws s3api put-bucket-encryption --bucket $BucketName --server-side-encryption-configuration ("file://" + ($encryptionPath -replace '\\', '/'))

    $bucketArn = "arn:aws:s3:::$BucketName"
    $objectArn = "$bucketArn/$Prefix/*"
    $bucketPolicy = @{
        Version = '2012-10-17'
        Statement = @(@{
            Sid = 'DenyInsecureTransport'
            Effect = 'Deny'
            Principal = '*'
            Action = 's3:*'
            Resource = @($bucketArn, "$bucketArn/*")
            Condition = @{ Bool = @{ 'aws:SecureTransport' = 'false' } }
        })
    } | ConvertTo-Json -Depth 8
    $bucketPolicyPath = Join-Path $tmp 'bucket-policy.json'
    [System.IO.File]::WriteAllText($bucketPolicyPath, $bucketPolicy, [System.Text.UTF8Encoding]::new($false))
    Invoke-Aws s3api put-bucket-policy --bucket $BucketName --policy ("file://" + ($bucketPolicyPath -replace '\\', '/'))

    $rolePolicy = @{
        Version = '2012-10-17'
        Statement = @(
            @{
                Sid = 'VerifyArchiveBucketHardening'
                Effect = 'Allow'
                Action = @('s3:GetBucketLocation', 's3:GetBucketVersioning', 's3:GetBucketPublicAccessBlock', 's3:GetEncryptionConfiguration')
                Resource = $bucketArn
            },
            @{
                Sid = 'WriteAndVerifyCandidateEEvidenceOnly'
                Effect = 'Allow'
                Action = @('s3:PutObject', 's3:GetObject', 's3:AbortMultipartUpload', 's3:ListMultipartUploadParts')
                Resource = $objectArn
            }
        )
    } | ConvertTo-Json -Depth 8
    $rolePolicyPath = Join-Path $tmp 'role-policy.json'
    [System.IO.File]::WriteAllText($rolePolicyPath, $rolePolicy, [System.Text.UTF8Encoding]::new($false))
    Invoke-Aws iam put-role-policy --role-name $RoleName --policy-name CandidateEOffsiteArchiveWrite --policy-document ("file://" + ($rolePolicyPath -replace '\\', '/'))

    Write-Host "Archive bucket ready: s3://$BucketName/$Prefix/runs/"
    Write-Host "Granted $RoleName upload and verification access only; no delete permission was granted."
} finally {
    Remove-Item -LiteralPath $tmp -Recurse -Force -ErrorAction SilentlyContinue
}
