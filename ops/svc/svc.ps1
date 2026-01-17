param(
  [Parameter(Position = 0)]
  [ValidateSet('list', 'install', 'install-all', 'uninstall', 'start', 'stop', 'restart', 'status', 'nssm-path')]
  [string]$Command = 'list',

  [Parameter(Position = 1)]
  [string]$Name
)

$ErrorActionPreference = 'Stop'

function Assert-Elevated([string]$action) {
  $identity = [Security.Principal.WindowsIdentity]::GetCurrent()
  $principal = New-Object Security.Principal.WindowsPrincipal($identity)
  $isAdmin = $principal.IsInRole([Security.Principal.WindowsBuiltinRole]::Administrator)
  if ($isAdmin) { return }
  throw "$action requires an elevated (Run as Administrator) PowerShell."
}

function Get-RepoRoot {
  $here = $PSScriptRoot
  return (Resolve-Path (Join-Path $here '..\..')).Path
}

function Get-NssmPath {
  $cmd = Get-Command nssm -ErrorAction SilentlyContinue
  if ($cmd -and (Test-Path $cmd.Source)) {
    return $cmd.Source
  }

  $wingetPackages = Join-Path $env:LOCALAPPDATA 'Microsoft\WinGet\Packages'
  if (Test-Path $wingetPackages) {
    $nssm = Get-ChildItem $wingetPackages -Recurse -Filter nssm.exe -ErrorAction SilentlyContinue |
      Where-Object { $_.FullName -match '\\win64\\nssm\.exe$' } |
      Select-Object -First 1 -ExpandProperty FullName
    if ($nssm -and (Test-Path $nssm)) {
      return $nssm
    }
  }

  throw "nssm.exe not found. Install NSSM (e.g. 'winget install -e --id NSSM.NSSM') or add it to PATH."
}

function Get-ServiceDefinitionDir([string]$serviceName) {
  $root = Get-RepoRoot
  return (Join-Path $root (Join-Path 'services' $serviceName))
}

function Get-ServiceDefinition([string]$serviceName) {
  $dir = Get-ServiceDefinitionDir $serviceName
  $path = Join-Path $dir 'service.json'
  if (!(Test-Path $path)) {
    throw "Service definition not found: $path"
  }
  $json = Get-Content -Raw -Path $path -Encoding UTF8 | ConvertFrom-Json
  return [pscustomobject]@{
    Name        = [string]$json.name
    DisplayName = [string]$json.displayName
    Description = [string]$json.description
    Exe         = [string]$json.exe
    Args        = [string]$json.args
    WorkDir     = [string]$json.workDir
    Stdout      = [string]$json.stdout
    Stderr      = [string]$json.stderr
    Env         = $json.env
    StartMode   = [string]$json.start
  }
}

function Get-ServiceNamesFromDisk {
  $root = Get-RepoRoot
  $servicesDir = Join-Path $root 'services'
  if (!(Test-Path $servicesDir)) {
    return @()
  }
  return Get-ChildItem -Path $servicesDir -Directory -ErrorAction SilentlyContinue |
    Select-Object -ExpandProperty Name |
    Sort-Object
}

function Ensure-Dir([string]$path) {
  if (!$path) { return }
  $dir = Split-Path -Parent $path
  if ($dir -and !(Test-Path $dir)) {
    New-Item -ItemType Directory -Path $dir | Out-Null
  }
}

function Install-One([string]$serviceName) {
  Assert-Elevated "Installing services"

  $nssm = Get-NssmPath
  $def = Get-ServiceDefinition $serviceName

  if (!$def.Name) { throw "Missing required field 'name' in services/$serviceName/service.json" }
  if (!$def.Exe) { throw "Missing required field 'exe' in services/$serviceName/service.json" }

  if (!(Test-Path $def.Exe)) {
    Write-Warning "Exe not found (will still attempt to install): $($def.Exe)"
  }

  Ensure-Dir $def.Stdout
  Ensure-Dir $def.Stderr

  & $nssm install $def.Name $def.Exe $def.Args | Out-Null

  if ($def.DisplayName) { & $nssm set $def.Name DisplayName $def.DisplayName | Out-Null }
  if ($def.Description) { & $nssm set $def.Name Description $def.Description | Out-Null }
  if ($def.WorkDir) { & $nssm set $def.Name AppDirectory $def.WorkDir | Out-Null }
  if ($def.Stdout) { & $nssm set $def.Name AppStdout $def.Stdout | Out-Null }
  if ($def.Stderr) { & $nssm set $def.Name AppStderr $def.Stderr | Out-Null }

  if ($def.Stdout -or $def.Stderr) {
    & $nssm set $def.Name AppRotateFiles 1 | Out-Null
    & $nssm set $def.Name AppRotateOnline 1 | Out-Null
    & $nssm set $def.Name AppRotateSeconds 86400 | Out-Null
    & $nssm set $def.Name AppRotateBytes 10485760 | Out-Null
  }

  if ($def.Env) {
    foreach ($prop in $def.Env.PSObject.Properties) {
      $k = [string]$prop.Name
      $v = [string]$prop.Value
      if ($k) { & $nssm set $def.Name "AppEnvironmentExtra" "$k=$v" | Out-Null }
    }
  }

  if ($def.StartMode -eq 'auto') {
    & $nssm set $def.Name Start SERVICE_AUTO_START | Out-Null
  } elseif ($def.StartMode -eq 'manual') {
    & $nssm set $def.Name Start SERVICE_DEMAND_START | Out-Null
  }

  $svc = Get-Service -Name $def.Name -ErrorAction SilentlyContinue
  if (!$svc) {
    throw "Service '$($def.Name)' was not created. Re-run in an elevated PowerShell."
  }

  Write-Host "Installed service: $($def.Name)"
}

function Uninstall-One([string]$serviceName) {
  Assert-Elevated "Removing services"

  $nssm = Get-NssmPath
  & $nssm remove $serviceName confirm | Out-Null
  Write-Host "Removed service: $serviceName"
}

function Require-Name([string]$serviceName) {
  if (![string]::IsNullOrWhiteSpace($serviceName)) { return }
  throw "Service name required. Example: .\\ops\\svc\\svc.ps1 install example-python-http"
}

switch ($Command) {
  'nssm-path' {
    Get-NssmPath
    break
  }
  'list' {
    $names = Get-ServiceNamesFromDisk
    if ($names.Count -eq 0) {
      Write-Host 'No service definitions found under services/.'
      break
    }
    $names | ForEach-Object { Write-Host $_ }
    break
  }
  'install' {
    Require-Name $Name
    Install-One $Name
    break
  }
  'install-all' {
    $names = Get-ServiceNamesFromDisk
    if ($names.Count -eq 0) { throw 'No service definitions found under services/.' }
    foreach ($svc in $names) {
      Install-One $svc
    }
    break
  }
  'uninstall' {
    Require-Name $Name
    Uninstall-One $Name
    break
  }
  'start' {
    Require-Name $Name
    Start-Service $Name
    break
  }
  'stop' {
    Require-Name $Name
    Stop-Service $Name
    break
  }
  'restart' {
    Require-Name $Name
    Restart-Service $Name
    break
  }
  'status' {
    Require-Name $Name
    Get-Service $Name | Format-Table Name, Status, StartType
    break
  }
}
