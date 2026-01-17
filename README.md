# d:\dhga\server

Personal server workspace (Windows): Tailscale + a lightweight service framework.

## Tailscale

- Windows service name: `Tailscale` (auto-start by default)
- CLI path: `C:\Program Files\Tailscale\tailscale.exe`
- After you log in, enable unattended mode (keeps working after user logout):
  - `& "$env:ProgramFiles\Tailscale\tailscale.exe" set --unattended=true`

## Service Framework (NSSM)

This repo contains a simple framework to wrap arbitrary processes as Windows services using NSSM.

- Script: `ops/svc/svc.ps1`
- Service definition: `services/<name>/service.json`

Examples (run in an elevated "Run as Administrator" PowerShell):

- Install all service definitions: `powershell -ExecutionPolicy Bypass -File .\ops\svc\svc.ps1 install-all`
- Install one service: `powershell -ExecutionPolicy Bypass -File .\ops\svc\svc.ps1 install example-python-http`
- Start/stop: `powershell -File .\ops\svc\svc.ps1 start example-python-http`

## Monitoring (Design)

- Plan: `docs/monitoring/monitoring-plan.md`
