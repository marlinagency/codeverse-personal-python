# CodeVerse Docker Sandbox

CodeVerse executes generated programs in Docker containers, not in the API
process. The sandbox runner uses the Docker SDK for Python and applies resource
limits on every run.

## Runtime Images

| Language | Image tag | Dockerfile |
| --- | --- | --- |
| Python | `codeverse-python-runtime:3.12` | `docker/runtimes/python/Dockerfile` |
| SQL | `codeverse-sql-runtime:16` | `docker/runtimes/sql/Dockerfile` |

Build both images on Windows PowerShell:

```powershell
.\scripts\build-sandbox-runtimes.ps1
```

Force a clean rebuild:

```powershell
.\scripts\build-sandbox-runtimes.ps1 -NoCache
```

## Security Defaults

`DockerSandboxRunner` starts containers with:

- `network_disabled=True`
- read-only `/workspace` mount
- non-root user `1000:1000`
- memory limit, CPU quota, PID limit
- external timeout with forced container removal

The generated source is written to a temporary host directory and mounted into
the container as read-only. Containers are removed in a `finally` block.

## Windows Prerequisites

Docker Desktop on Windows requires WSL2 or another supported backend. If Docker
Desktop is installed but `docker info` says the daemon cannot start, enable
these Windows features from an elevated PowerShell and reboot:

```powershell
dism.exe /online /enable-feature /featurename:Microsoft-Windows-Subsystem-Linux /all /norestart
dism.exe /online /enable-feature /featurename:VirtualMachinePlatform /all /norestart
```

After reboot:

```powershell
wsl --set-default-version 2
docker info
```

## Verification

Offline tests:

```powershell
cd backend
..\.venv\Scripts\pytest.exe
```

Docker-backed tests:

```powershell
cd backend
..\.venv\Scripts\pytest.exe tests\sandbox -m docker
```

Those tests build missing runtime images and run real Python and PostgreSQL
containers.
