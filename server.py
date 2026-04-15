from starlette.responses import JSONResponse
import uvicorn
from fastmcp import FastMCP
import os
import subprocess
import asyncio
import json
from typing import Optional, List
from pathlib import Path

mcp = FastMCP("FerretDB")


@mcp.tool()
async def run_ferretdb_server(
    listen_addr: str = "127.0.0.1:27017",
    postgresql_url: Optional[str] = None,
    log_level: str = "info",
    tls: bool = False,
    extra_flags: Optional[List[str]] = None,
) -> dict:
    """
    Start the FerretDB server process with specified configuration.
    Use this when you need to launch FerretDB as a MongoDB-compatible proxy
    backed by PostgreSQL with DocumentDB extension. Supports configuring
    listen address, backend, logging, and TLS options.
    """
    cmd = ["ferretdb"]

    cmd.append(f"--listen-addr={listen_addr}")
    cmd.append(f"--log-level={log_level}")

    if postgresql_url:
        cmd.append(f"--postgresql-url={postgresql_url}")

    if tls:
        cmd.append("--tls")

    if extra_flags:
        cmd.extend(extra_flags)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=5.0)
            return {
                "status": "exited",
                "pid": process.pid,
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "command": " ".join(cmd),
            }
        except asyncio.TimeoutError:
            return {
                "status": "running",
                "pid": process.pid,
                "message": "FerretDB process started and is running (did not exit within 5s timeout)",
                "command": " ".join(cmd),
                "listen_addr": listen_addr,
                "log_level": log_level,
                "tls_enabled": tls,
                "postgresql_url": postgresql_url or "(not set)",
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "ferretdb binary not found. Please ensure FerretDB is installed and available in PATH.",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "command": " ".join(cmd),
        }


@mcp.tool()
async def setup_test_environment(
    compose_file: Optional[str] = None,
    timeout_seconds: int = 300,
    log_level: str = "info",
) -> dict:
    """
    Run the envtool setup subcommand to prepare the development/test environment.
    This configures Docker Compose services, waits for dependencies to be healthy,
    and sets up required infrastructure before running tests.
    """
    cmd = ["go", "run", "./cmd/envtool", "setup"]

    cmd.append(f"--log-level={log_level}")

    if compose_file:
        cmd.append(f"--compose-file={compose_file}")

    env = os.environ.copy()

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=float(timeout_seconds)
            )
            success = process.returncode == 0
            return {
                "status": "success" if success else "failed",
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "command": " ".join(cmd),
            }
        except asyncio.TimeoutError:
            process.kill()
            return {
                "status": "timeout",
                "error": f"Setup timed out after {timeout_seconds} seconds",
                "command": " ".join(cmd),
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "'go' binary not found. Please ensure Go is installed and available in PATH.",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "command": " ".join(cmd),
        }


@mcp.tool()
async def run_tests(
    packages: List[str],
    run_pattern: Optional[str] = None,
    parallel: Optional[int] = None,
    timeout_seconds: int = 600,
    verbose: bool = False,
    tags: Optional[List[str]] = None,
) -> dict:
    """
    Execute Go tests via envtool's test runner, which provides enhanced output
    formatting, parallel test control, and proper exit code handling.
    """
    cmd = ["go", "run", "./cmd/envtool", "tests", "run"]

    if run_pattern:
        cmd.append(f"--run={run_pattern}")

    if parallel is not None:
        cmd.append(f"--parallel={parallel}")

    if verbose:
        cmd.append("--verbose")

    if tags:
        cmd.append(f"--tags={','.join(tags)}")

    cmd.append(f"--timeout={timeout_seconds}s")

    cmd.extend(packages)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=float(timeout_seconds + 60)
            )
            success = process.returncode == 0
            return {
                "status": "success" if success else "failed",
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "command": " ".join(cmd),
                "packages": packages,
            }
        except asyncio.TimeoutError:
            process.kill()
            return {
                "status": "timeout",
                "error": f"Tests timed out after {timeout_seconds} seconds",
                "command": " ".join(cmd),
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "'go' binary not found. Please ensure Go is installed and available in PATH.",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "command": " ".join(cmd),
        }


@mcp.tool()
async def run_fuzz(
    fuzz_target: str,
    package: str,
    duration_seconds: int = 60,
    corpus_dir: Optional[str] = None,
) -> dict:
    """
    Execute fuzz testing via envtool's fuzz subcommand against FerretDB components.
    Runs Go fuzz targets for a specified duration to discover edge cases and crashes
    in protocol parsing or query handling.
    """
    cmd = [
        "go",
        "test",
        f"-fuzz={fuzz_target}",
        f"-fuzztime={duration_seconds}s",
    ]

    if corpus_dir:
        cmd.append(f"-test.fuzzcachedir={corpus_dir}")

    cmd.append(package)

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=float(duration_seconds + 60)
            )
            success = process.returncode == 0
            return {
                "status": "success" if success else "failed",
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
                "command": " ".join(cmd),
                "fuzz_target": fuzz_target,
                "package": package,
                "duration_seconds": duration_seconds,
            }
        except asyncio.TimeoutError:
            process.kill()
            return {
                "status": "timeout",
                "error": f"Fuzz run timed out after {duration_seconds + 60} seconds",
                "command": " ".join(cmd),
            }
    except FileNotFoundError:
        return {
            "status": "error",
            "error": "'go' binary not found. Please ensure Go is installed and available in PATH.",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "command": " ".join(cmd),
        }


@mcp.tool()
async def get_version_info(
    version_file: str = "build/version/version.txt",
    format: str = "text",
) -> dict:
    """
    Retrieve the current FerretDB version information from the build version file or binary.
    Use this to check what version is built, verify release tags, or confirm build metadata.
    """
    result = {}

    version_path = Path(version_file)
    if version_path.exists():
        try:
            raw_version = version_path.read_text(encoding="utf-8").strip()
            clean_version = raw_version.lstrip("v")
            result["version_file"] = version_file
            result["raw_version"] = raw_version
            result["version"] = clean_version
        except Exception as e:
            result["version_file_error"] = str(e)
    else:
        result["version_file_error"] = f"Version file not found: {version_file}"

    if format == "json":
        cmd = ["go", "run", "./cmd/envtool", "package-version", version_file]
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=30.0)
            if process.returncode == 0:
                version_str = stdout.decode(errors="replace").strip()
                result["envtool_version"] = version_str
                result["format"] = "json"

                git_cmd = ["git", "log", "-1", "--format=%H %ai"]
                git_process = await asyncio.create_subprocess_exec(
                    *git_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                git_stdout, _ = await asyncio.wait_for(git_process.communicate(), timeout=10.0)
                if git_process.returncode == 0:
                    parts = git_stdout.decode(errors="replace").strip().split(" ", 1)
                    result["commit"] = parts[0] if parts else "unknown"
                    result["build_date"] = parts[1] if len(parts) > 1 else "unknown"
            else:
                result["envtool_error"] = stderr.decode(errors="replace")
        except asyncio.TimeoutError:
            result["envtool_error"] = "Command timed out"
        except FileNotFoundError:
            result["envtool_error"] = "'go' binary not found"
        except Exception as e:
            result["envtool_error"] = str(e)
    else:
        result["format"] = "text"

    try:
        ferretdb_process = await asyncio.create_subprocess_exec(
            "ferretdb", "--version",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        fb_stdout, fb_stderr = await asyncio.wait_for(ferretdb_process.communicate(), timeout=10.0)
        result["binary_version_output"] = (
            fb_stdout.decode(errors="replace") or fb_stderr.decode(errors="replace")
        ).strip()
    except FileNotFoundError:
        result["binary_note"] = "ferretdb binary not found in PATH"
    except asyncio.TimeoutError:
        result["binary_note"] = "ferretdb --version timed out"
    except Exception as e:
        result["binary_note"] = str(e)

    return result


@mcp.tool()
async def get_diagnostic_data(
    include_compose_logs: bool = True,
    setup_error: Optional[str] = None,
    output_file: Optional[str] = None,
) -> dict:
    """
    Collect and print diagnostic data about the FerretDB environment, including
    Docker Compose service logs and system information. Use this when debugging
    test failures, setup errors, or unexpected crashes.
    """
    diagnostics = {}

    async def run_cmd(cmd: List[str]) -> dict:
        try:
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=60.0)
            return {
                "returncode": process.returncode,
                "stdout": stdout.decode(errors="replace"),
                "stderr": stderr.decode(errors="replace"),
            }
        except FileNotFoundError:
            return {"error": f"Command not found: {cmd[0]}"}
        except asyncio.TimeoutError:
            return {"error": f"Command timed out: {' '.join(cmd)}"}
        except Exception as e:
            return {"error": str(e)}

    if include_compose_logs:
        diagnostics["compose_logs"] = await run_cmd(["docker", "compose", "logs"])
        diagnostics["compose_ps"] = await run_cmd(["docker", "compose", "ps", "--all"])
        diagnostics["docker_stats"] = await run_cmd(
            ["docker", "stats", "--all", "--no-stream"]
        )

    diagnostics["git_version"] = await run_cmd(["git", "version"])
    diagnostics["docker_version"] = await run_cmd(["docker", "version"])
    diagnostics["compose_version"] = await run_cmd(["docker", "compose", "version"])
    diagnostics["go_version"] = await run_cmd(["go", "version"])

    diagnostics["goos"] = os.sys.platform
    diagnostics["python_version"] = os.sys.version

    if setup_error:
        diagnostics["setup_error"] = setup_error

    version_path = Path("build/version/version.txt")
    if version_path.exists():
        try:
            diagnostics["ferretdb_version"] = version_path.read_text(encoding="utf-8").strip()
        except Exception as e:
            diagnostics["ferretdb_version_error"] = str(e)

    if output_file:
        try:
            output_path = Path(output_file)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(diagnostics, indent=2, default=str), encoding="utf-8"
            )
            diagnostics["output_written_to"] = output_file
        except Exception as e:
            diagnostics["output_file_error"] = str(e)

    return diagnostics


@mcp.tool()
async def manage_shell_paths(
    action: str,
    paths: List[str],
    recursive: bool = True,
) -> dict:
    """
    Create or remove directories using envtool shell path utilities.
    Use this to set up required directory structures for test data, build artifacts,
    or temporary files, or to clean them up after test runs.
    Actions: 'mkdir' to create directories, 'rmdir' to remove directories,
    or 'read' to read a file's contents.
    """
    results = []
    errors = []

    if action == "mkdir":
        for path in paths:
            try:
                p = Path(path)
                if recursive:
                    p.mkdir(parents=True, exist_ok=True)
                else:
                    p.mkdir(exist_ok=True)
                results.append({"path": path, "status": "created", "exists": p.exists()})
            except Exception as e:
                errors.append({"path": path, "error": str(e)})

    elif action == "rmdir":
        import shutil
        for path in paths:
            try:
                p = Path(path)
                if not p.exists():
                    results.append({"path": path, "status": "not_found_skipped"})
                    continue
                if recursive:
                    shutil.rmtree(str(p))
                else:
                    p.rmdir()
                results.append({"path": path, "status": "removed", "exists": p.exists()})
            except Exception as e:
                errors.append({"path": path, "error": str(e)})

    elif action == "read":
        for path in paths:
            try:
                p = Path(path)
                if not p.exists():
                    errors.append({"path": path, "error": "File not found"})
                    continue
                content = p.read_text(encoding="utf-8")
                results.append({"path": path, "status": "read", "content": content})
            except Exception as e:
                errors.append({"path": path, "error": str(e)})

    else:
        return {
            "status": "error",
            "error": f"Unknown action '{action}'. Valid actions are: mkdir, rmdir, read",
        }

    return {
        "status": "success" if not errors else "partial_failure",
        "action": action,
        "recursive": recursive,
        "results": results,
        "errors": errors,
        "total": len(paths),
        "succeeded": len(results),
        "failed": len(errors),
    }




# ── Browser-friendly entrypoint ──────────────────────────────
async def _health(request):
    return JSONResponse({"status": "ok", "server": mcp.name, "mcp_endpoint": "/mcp"})

async def _browser_mcp(request):
    """Return server info when /mcp is opened in a browser (GET without SSE accept)."""
    tools = []
    try:
        for t in mcp._tool_manager._tools.values():
            tools.append({"name": t.name, "description": t.description or ""})
    except Exception:
        pass
    return JSONResponse({
        "server": mcp.name,
        "protocol": "MCP (Model Context Protocol)",
        "transport": "streamable-http",
        "endpoint": "/mcp",
        "tools": tools,
        "tool_count": len(tools),
        "usage": "Connect with an MCP client (Claude Desktop, Cursor, etc.) using this URL as the server endpoint."
    })

class _BrowserFallbackMiddleware:
    """Intercept browser GETs to /mcp before they hit FastMCP's handler."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if (scope["type"] == "http"
            and scope["path"] == "/mcp"
            and scope["method"] == "GET"):
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                from starlette.requests import Request
                req = Request(scope, receive)
                resp = await _browser_mcp(req)
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)

_mcp_asgi = mcp.http_app()
app = _BrowserFallbackMiddleware(_mcp_asgi)



# Browser-friendly entrypoint
class _BrowserFallback:
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if (scope["type"] == "http"
            and scope["path"] == "/mcp"
            and scope["method"] == "GET"):
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                tools = []
                try:
                    for t in mcp._tool_manager._tools.values():
                        tools.append({"name": t.name, "description": t.description or ""})
                except Exception:
                    pass
                resp = JSONResponse({
                    "server": mcp.name,
                    "protocol": "MCP (Model Context Protocol)",
                    "transport": "streamable-http",
                    "endpoint": "/mcp",
                    "tools": tools,
                    "tool_count": len(tools),
                    "usage": "Connect with an MCP client (Claude Desktop, Cursor, etc.) using this URL."
                })
                await resp(scope, receive, send)
                return
        await self.app(scope, receive, send)

app = _BrowserFallback(mcp.http_app())

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
