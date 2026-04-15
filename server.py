import uvicorn
from starlette.applications import Starlette
from starlette.routing import Route, Mount
from starlette.responses import JSONResponse
from fastmcp import FastMCP
import subprocess
import os
import sys
import json
import shutil
from typing import Optional, List

mcp = FastMCP("FerretDB")


def _run_process(cmd: list, timeout: int = 60, cwd: str = None) -> dict:
    """Helper to run a subprocess and capture output."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=cwd,
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd),
        }
    except subprocess.TimeoutExpired as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": e.stdout or "",
            "stderr": f"Process timed out after {timeout} seconds",
            "command": " ".join(cmd),
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Binary not found: {e}",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Unexpected error: {e}",
            "command": " ".join(cmd),
        }


@mcp.tool()
async def run_ferretdb(
    listen_addr: Optional[str] = "127.0.0.1:27017",
    postgresql_url: Optional[str] = None,
    log_level: Optional[str] = "info",
    log_format: Optional[str] = "console",
    extra_flags: Optional[List[str]] = None,
) -> dict:
    """
    Start the FerretDB server process with specified configuration.
    Use this when you need to launch FerretDB to accept MongoDB protocol connections
    and proxy them to a PostgreSQL/DocumentDB backend.
    Supports setting listen address, PostgreSQL URI, logging level, and other server options.
    """
    ferretdb_bin = shutil.which("ferretdb")
    if not ferretdb_bin:
        # Try common locations
        candidates = ["/usr/local/bin/ferretdb", "./ferretdb", "./bin/ferretdb"]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                ferretdb_bin = c
                break

    if not ferretdb_bin:
        return {
            "success": False,
            "error": "ferretdb binary not found in PATH or common locations. Please install FerretDB first.",
            "searched_locations": ["PATH"] + ["/usr/local/bin/ferretdb", "./ferretdb", "./bin/ferretdb"],
        }

    cmd = [ferretdb_bin]

    if listen_addr:
        cmd += [f"--listen-addr={listen_addr}"]

    if postgresql_url:
        cmd += [f"--postgresql-url={postgresql_url}"]

    if log_level:
        cmd += [f"--log-level={log_level}"]

    if log_format:
        cmd += [f"--log-format={log_format}"]

    if extra_flags:
        cmd += extra_flags

    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        # Give it a moment to start up or fail immediately
        try:
            stdout, stderr = proc.communicate(timeout=3)
            return {
                "success": proc.returncode == 0,
                "returncode": proc.returncode,
                "stdout": stdout,
                "stderr": stderr,
                "command": " ".join(cmd),
                "note": "Process exited quickly. Check stderr for errors.",
            }
        except subprocess.TimeoutExpired:
            # Process is still running - that's expected for a server
            return {
                "success": True,
                "pid": proc.pid,
                "command": " ".join(cmd),
                "status": "running",
                "listen_addr": listen_addr,
                "postgresql_url": postgresql_url or "not set",
                "log_level": log_level,
                "log_format": log_format,
                "message": f"FerretDB started successfully with PID {proc.pid}. Listening on {listen_addr}.",
            }
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"ferretdb binary not found at: {ferretdb_bin}",
            "command": " ".join(cmd),
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(cmd),
        }


@mcp.tool()
async def setup_environment(
    target: Optional[str] = None,
    log_level: Optional[str] = "info",
    timeout_seconds: Optional[int] = 120,
) -> dict:
    """
    Set up the development or test environment for FerretDB using the envtool setup command.
    Use this to initialize required services (e.g., PostgreSQL with DocumentDB extension via Docker Compose),
    verify dependencies, and prepare the environment before running tests or the server.
    """
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        candidates = ["./bin/envtool", "./envtool"]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                envtool_bin = c
                break

    if not envtool_bin:
        # Try building it first with go run
        go_bin = shutil.which("go")
        if go_bin:
            build_result = _run_process(
                [go_bin, "build", "-o", "./bin/envtool", "./cmd/envtool"],
                timeout=120,
            )
            if build_result["success"]:
                envtool_bin = "./bin/envtool"
            else:
                return {
                    "success": False,
                    "error": "envtool binary not found and could not be built.",
                    "build_output": build_result,
                }
        else:
            return {
                "success": False,
                "error": "envtool binary not found in PATH and Go is not available to build it.",
            }

    cmd = [envtool_bin, f"--log-level={log_level}", "setup"]

    if target:
        cmd.append(target)

    result = _run_process(cmd, timeout=timeout_seconds)
    result["tool"] = "envtool setup"
    result["target"] = target or "default"
    return result


@mcp.tool()
async def run_tests(
    packages: Optional[List[str]] = None,
    run_pattern: Optional[str] = None,
    verbose: Optional[bool] = False,
    parallel: Optional[int] = None,
    timeout_seconds: Optional[int] = 600,
    tags: Optional[List[str]] = None,
    short: Optional[bool] = False,
) -> dict:
    """
    Run Go tests for FerretDB using the envtool tests runner, which provides enhanced test output formatting,
    panic recovery, and subtest support. Use this to execute unit tests, integration tests, or specific
    test packages with filtering capabilities.
    """
    if packages is None:
        packages = ["./..."]

    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        candidates = ["./bin/envtool", "./envtool"]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                envtool_bin = c
                break

    if not envtool_bin:
        # Fall back to plain `go test`
        go_bin = shutil.which("go")
        if not go_bin:
            return {
                "success": False,
                "error": "Neither envtool nor go binary found in PATH.",
            }

        cmd = [go_bin, "test"]

        if verbose:
            cmd.append("-v")

        if short:
            cmd.append("-short")

        if run_pattern:
            cmd += ["-run", run_pattern]

        if parallel is not None:
            cmd += ["-parallel", str(parallel)]

        cmd += ["-timeout", f"{timeout_seconds}s"]

        if tags:
            cmd += ["-tags", ",".join(tags)]

        cmd += packages

        result = _run_process(cmd, timeout=timeout_seconds + 30)
        result["runner"] = "go test (fallback)"
        return result

    # Use envtool tests runner
    cmd = [envtool_bin, "tests", "run"]

    if run_pattern:
        cmd += ["-run", run_pattern]

    if verbose:
        cmd.append("-v")

    if short:
        cmd.append("-short")

    if parallel is not None:
        cmd += ["-parallel", str(parallel)]

    cmd += ["-timeout", f"{timeout_seconds}s"]

    if tags:
        cmd += ["-tags", ",".join(tags)]

    cmd += packages

    result = _run_process(cmd, timeout=timeout_seconds + 30)
    result["runner"] = "envtool tests run"
    result["packages"] = packages
    return result


@mcp.tool()
async def run_fuzz(
    fuzz_target: str,
    package: str,
    duration_seconds: Optional[int] = 60,
    corpus_dir: Optional[str] = None,
    parallel: Optional[int] = None,
) -> dict:
    """
    Run Go fuzz tests for FerretDB using the envtool fuzz subcommand.
    Use this to perform fuzz testing on specific targets to discover unexpected inputs that cause
    failures or panics. Useful for testing BSON parsing, query handling, and protocol decoding.
    """
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        candidates = ["./bin/envtool", "./envtool"]
        for c in candidates:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                envtool_bin = c
                break

    if not envtool_bin:
        # Fall back to go test -fuzz
        go_bin = shutil.which("go")
        if not go_bin:
            return {
                "success": False,
                "error": "Neither envtool nor go binary found in PATH.",
            }

        cmd = [go_bin, "test", "-fuzz", fuzz_target, f"-fuzztime={duration_seconds}s"]

        if parallel is not None:
            cmd += ["-parallel", str(parallel)]

        if corpus_dir:
            cmd += ["-test.fuzzcachedir", corpus_dir]

        cmd.append(package)

        result = _run_process(cmd, timeout=duration_seconds + 30)
        result["runner"] = "go test -fuzz (fallback)"
        result["fuzz_target"] = fuzz_target
        result["package"] = package
        return result

    cmd = [envtool_bin, "fuzz", "-fuzz", fuzz_target, f"-fuzztime={duration_seconds}s"]

    if parallel is not None:
        cmd += ["-parallel", str(parallel)]

    if corpus_dir:
        cmd += ["-corpus", corpus_dir]

    cmd.append(package)

    result = _run_process(cmd, timeout=duration_seconds + 30)
    result["runner"] = "envtool fuzz"
    result["fuzz_target"] = fuzz_target
    result["package"] = package
    result["duration_seconds"] = duration_seconds
    return result


@mcp.tool()
async def print_diagnostic_data(
    setup_error_message: Optional[str] = None,
    log_level: Optional[str] = "info",
) -> dict:
    """
    Collect and print diagnostic information about the FerretDB environment, including
    Docker Compose service logs and system state. Use this when debugging setup failures,
    test failures, or environment issues to get a comprehensive snapshot of what went wrong.
    """
    diagnostics = {}

    # Docker compose logs
    docker_bin = shutil.which("docker")
    if docker_bin:
        logs_result = _run_process([docker_bin, "compose", "logs"], timeout=30)
        diagnostics["docker_compose_logs"] = logs_result

        ps_result = _run_process([docker_bin, "compose", "ps", "--all"], timeout=30)
        diagnostics["docker_compose_ps"] = ps_result

        stats_result = _run_process([docker_bin, "stats", "--all", "--no-stream"], timeout=30)
        diagnostics["docker_stats"] = stats_result

        docker_version_result = _run_process([docker_bin, "version"], timeout=15)
        diagnostics["docker_version"] = docker_version_result

        compose_version_result = _run_process([docker_bin, "compose", "version"], timeout=15)
        diagnostics["docker_compose_version"] = compose_version_result
    else:
        diagnostics["docker_compose_logs"] = {"error": "docker not found in PATH"}

    # Git version
    git_bin = shutil.which("git")
    if git_bin:
        git_version_result = _run_process([git_bin, "version"], timeout=10)
        diagnostics["git_version"] = git_version_result
    else:
        diagnostics["git_version"] = {"error": "git not found in PATH"}

    # Go version
    go_bin = shutil.which("go")
    if go_bin:
        go_version_result = _run_process([go_bin, "version"], timeout=10)
        diagnostics["go_version"] = go_version_result
    else:
        diagnostics["go_version"] = {"error": "go not found in PATH"}

    # Try envtool diagnostics
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for c in ["./bin/envtool", "./envtool"]:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                envtool_bin = c
                break

    if envtool_bin:
        diag_cmd = [envtool_bin, f"--log-level={log_level}", "shell", "read"]
        # Just capture the envtool version as a diagnostic
        version_check = _run_process([envtool_bin, "--version"], timeout=10)
        diagnostics["envtool_version"] = version_check

    # FerretDB version file
    version_file = "build/version/version.txt"
    if os.path.isfile(version_file):
        try:
            with open(version_file, "r") as f:
                diagnostics["ferretdb_version_file"] = f.read().strip()
        except Exception as e:
            diagnostics["ferretdb_version_file"] = f"Error reading: {e}"
    else:
        diagnostics["ferretdb_version_file"] = "File not found"

    diagnostics["setup_error_message"] = setup_error_message
    diagnostics["log_level"] = log_level
    diagnostics["python_version"] = sys.version
    diagnostics["cwd"] = os.getcwd()

    return diagnostics


@mcp.tool()
async def get_version_info(
    version_file_path: Optional[str] = "build/version/version.txt",
    output_format: Optional[str] = "text",
) -> dict:
    """
    Retrieve version information for FerretDB, including the build version, git commit hash,
    and build timestamp. Use this to verify which version is installed, check build metadata,
    or confirm the package version matches expectations before running tests or deployments.
    """
    result = {
        "version_file_path": version_file_path,
        "output_format": output_format,
    }

    # Read the version file
    if os.path.isfile(version_file_path):
        try:
            with open(version_file_path, "r") as f:
                raw_version = f.read().strip()
            result["raw_version"] = raw_version
            # Strip leading 'v' for package version (as packageVersion does in Go)
            result["package_version"] = raw_version.lstrip("v")
        except Exception as e:
            result["error"] = f"Error reading version file: {e}"
            result["raw_version"] = None
            result["package_version"] = None
    else:
        result["error"] = f"Version file not found: {version_file_path}"
        result["raw_version"] = None
        result["package_version"] = None

    # Try to get additional info from git
    git_bin = shutil.which("git")
    if git_bin:
        commit_result = _run_process([git_bin, "rev-parse", "HEAD"], timeout=10)
        if commit_result["success"]:
            result["git_commit"] = commit_result["stdout"].strip()
        else:
            result["git_commit"] = None

        branch_result = _run_process([git_bin, "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
        if branch_result["success"]:
            result["git_branch"] = branch_result["stdout"].strip()
        else:
            result["git_branch"] = None

        dirty_result = _run_process([git_bin, "status", "--porcelain"], timeout=10)
        if dirty_result["success"]:
            result["git_dirty"] = len(dirty_result["stdout"].strip()) > 0
        else:
            result["git_dirty"] = None
    else:
        result["git_commit"] = None
        result["git_branch"] = None
        result["git_dirty"] = None

    # Try envtool version command
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for c in ["./bin/envtool", "./envtool"]:
            if os.path.isfile(c) and os.access(c, os.X_OK):
                envtool_bin = c
                break

    if envtool_bin:
        version_cmd_result = _run_process([envtool_bin, "--version"], timeout=10)
        result["envtool_version_output"] = version_cmd_result.get("stdout", "").strip()

    if output_format == "json":
        return result
    else:
        # Text format summary
        lines = []
        if result.get("raw_version"):
            lines.append(f"Version: {result['raw_version']}")
        if result.get("git_commit"):
            lines.append(f"Commit: {result['git_commit']}")
        if result.get("git_branch"):
            lines.append(f"Branch: {result['git_branch']}")
        if result.get("git_dirty") is not None:
            lines.append(f"Dirty: {result['git_dirty']}")
        result["text_summary"] = "\n".join(lines) if lines else "No version information available"
        return result


@mcp.tool()
async def manage_shell_paths(
    operation: str,
    paths: List[str],
) -> dict:
    """
    Create or remove directories and read file contents using envtool shell utilities.
    Use this for managing test fixtures, build artifacts, temporary directories, or reading
    configuration files during development and CI workflows.

    operation: 'mkdir' to create directories, 'rmdir' to remove directories, or 'read' to read a file's contents.
    paths: One or more file or directory paths to operate on.
    """
    if operation not in ("mkdir", "rmdir", "read"):
        return {
            "success": False,
            "error": f"Invalid operation '{operation}'. Must be 'mkdir', 'rmdir', or 'read'.",
        }

    if not paths:
        return {
            "success": False,
            "error": "No paths provided.",
        }

    results = []

    if operation == "mkdir":
        for path in paths:
            try:
                os.makedirs(path, exist_ok=True)
                results.append({"path": path, "success": True, "action": "created"})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})

    elif operation == "rmdir":
        for path in paths:
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                    results.append({"path": path, "success": True, "action": "removed"})
                else:
                    # Match Go behavior: removing absent dir is not an error
                    results.append({"path": path, "success": True, "action": "already absent"})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})

    elif operation == "read":
        for path in paths:
            try:
                with open(path, "r") as f:
                    content = f.read()
                results.append({"path": path, "success": True, "content": content})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})

    all_success = all(r["success"] for r in results)
    return {
        "success": all_success,
        "operation": operation,
        "results": results,
    }

async def health(request):
    return JSONResponse({"status": "ok", "server": mcp.name})

async def tools(request):
    registered = await mcp.list_tools()
    tool_list = [{"name": t.name, "description": t.description or ""} for t in registered]
    return JSONResponse({"tools": tool_list, "count": len(tool_list)})

mcp_app = mcp.http_app(transport="streamable-http")

class _FixAcceptHeader:
    """Ensure Accept header includes both types FastMCP requires."""
    def __init__(self, app):
        self.app = app
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            accept = headers.get(b"accept", b"").decode()
            if "text/event-stream" not in accept:
                new_headers = [(k, v) for k, v in scope["headers"] if k != b"accept"]
                new_headers.append((b"accept", b"application/json, text/event-stream"))
                scope = dict(scope, headers=new_headers)
        await self.app(scope, receive, send)

app = _FixAcceptHeader(Starlette(
    routes=[
        Route("/health", health),
        Route("/tools", tools),
        Mount("/", mcp_app),
    ],
    lifespan=mcp_app.lifespan,
))

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
