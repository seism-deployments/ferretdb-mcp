from fastmcp import FastMCP
import subprocess
import os
import shutil
import asyncio
from typing import Optional, List

mcp = FastMCP("FerretDB")


def _run_command(args: list[str], timeout: int = 300) -> dict:
    """Run a subprocess command and return result."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "success": result.returncode == 0,
            "command": " ".join(args)
        }
    except subprocess.TimeoutExpired:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "success": False,
            "command": " ".join(args)
        }
    except FileNotFoundError as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command not found: {str(e)}",
            "success": False,
            "command": " ".join(args)
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"Unexpected error: {str(e)}",
            "success": False,
            "command": " ".join(args)
        }


@mcp.tool()
async def run_ferretdb_server(
    listen_addr: Optional[str] = "127.0.0.1:27017",
    postgresql_url: Optional[str] = None,
    log_level: Optional[str] = "info",
    mode: Optional[str] = None
) -> dict:
    """
    Start the FerretDB server process with specified configuration options.
    Use this when you need to launch the MongoDB-compatible proxy server that
    converts wire protocol queries to SQL for PostgreSQL with DocumentDB extension.
    """
    args = ["go", "run", "./cmd/ferretdb"]

    if listen_addr:
        args.extend(["--listen-addr", listen_addr])

    if postgresql_url:
        args.extend(["--postgresql-url", postgresql_url])

    if log_level:
        args.extend(["--log-level", log_level])

    if mode:
        args.extend(["--mode", mode])

    result = _run_command(args, timeout=30)

    return {
        "command": result["command"],
        "success": result["success"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "config": {
            "listen_addr": listen_addr,
            "postgresql_url": postgresql_url,
            "log_level": log_level,
            "mode": mode
        },
        "note": "FerretDB process started. Check stdout/stderr for runtime output. The server runs as a long-lived process."
    }


@mcp.tool()
async def setup_environment(
    compose_file: Optional[str] = None,
    services: Optional[List[str]] = None,
    timeout_seconds: Optional[int] = 120,
    verbose: Optional[bool] = False
) -> dict:
    """
    Initialize and set up the development/test environment for FerretDB,
    including Docker Compose services, database backends, and required infrastructure.
    Use this before running tests or starting development work.
    """
    base_args = ["docker", "compose"]

    if compose_file:
        base_args.extend(["-f", compose_file])

    up_args = base_args + ["up", "-d", "--wait"]

    if services:
        up_args.extend(services)

    result = _run_command(up_args, timeout=timeout_seconds or 120)

    output = {
        "command": result["command"],
        "success": result["success"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "services_requested": services or "all",
        "compose_file": compose_file or "default"
    }

    if verbose and result["success"]:
        log_args = base_args + ["logs"]
        if services:
            log_args.extend(services)
        log_result = _run_command(log_args, timeout=30)
        output["compose_logs"] = log_result["stdout"]

    if not result["success"]:
        ps_args = base_args + ["ps", "--all"]
        ps_result = _run_command(ps_args, timeout=30)
        output["service_status"] = ps_result["stdout"]

    return output


@mcp.tool()
async def run_tests(
    packages: Optional[List[str]] = None,
    run_filter: Optional[str] = None,
    timeout: Optional[str] = "10m",
    count: Optional[int] = 1,
    verbose: Optional[bool] = False,
    tags: Optional[List[str]] = None,
    short: Optional[bool] = False
) -> dict:
    """
    Execute Go tests for FerretDB packages with enhanced output formatting.
    Use this to run unit tests, integration tests, or specific test suites.
    Handles test output parsing, panic recovery, and structured result reporting.
    """
    if packages is None:
        packages = ["./..."]

    args = ["go", "test"]

    if verbose:
        args.append("-v")

    if timeout:
        args.extend(["-timeout", timeout])

    if count is not None:
        args.extend(["-count", str(count)])

    if run_filter:
        args.extend(["-run", run_filter])

    if short:
        args.append("-short")

    if tags:
        args.extend(["-tags", ",".join(tags)])

    args.extend(packages)

    # Parse timeout into seconds for subprocess
    timeout_secs = 600  # default 10m
    if timeout:
        t = timeout.strip()
        if t.endswith("h"):
            timeout_secs = int(t[:-1]) * 3600
        elif t.endswith("m"):
            timeout_secs = int(t[:-1]) * 60
        elif t.endswith("s"):
            timeout_secs = int(t[:-1])

    result = _run_command(args, timeout=timeout_secs + 60)

    # Parse test results from output
    passed = 0
    failed = 0
    skipped = 0
    lines = result["stdout"].splitlines()
    for line in lines:
        if line.startswith("--- PASS"):
            passed += 1
        elif line.startswith("--- FAIL"):
            failed += 1
        elif line.startswith("--- SKIP"):
            skipped += 1

    return {
        "command": result["command"],
        "success": result["success"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "summary": {
            "passed": passed,
            "failed": failed,
            "skipped": skipped
        },
        "config": {
            "packages": packages,
            "run_filter": run_filter,
            "timeout": timeout,
            "count": count,
            "verbose": verbose,
            "tags": tags,
            "short": short
        }
    }


@mcp.tool()
async def run_fuzz(
    fuzz_target: str,
    package: str,
    duration: Optional[str] = "30s",
    corpus_dir: Optional[str] = None,
    workers: Optional[int] = None
) -> dict:
    """
    Execute Go fuzz tests against FerretDB to find edge cases and bugs through
    randomized input generation. Use this for security testing, finding panics,
    or validating input handling robustness.
    """
    args = ["go", "test", "-fuzz", fuzz_target]

    if duration:
        args.extend(["-fuzztime", duration])

    if workers is not None:
        args.extend(["-parallel", str(workers)])

    if corpus_dir:
        args.extend(["-test.fuzzcachedir", corpus_dir])

    args.append(package)

    # Parse duration into seconds
    timeout_secs = 60  # default 30s + buffer
    if duration:
        d = duration.strip()
        if d.endswith("h"):
            timeout_secs = int(d[:-1]) * 3600 + 60
        elif d.endswith("m"):
            timeout_secs = int(d[:-1]) * 60 + 60
        elif d.endswith("s"):
            timeout_secs = int(d[:-1]) + 30

    result = _run_command(args, timeout=timeout_secs)

    return {
        "command": result["command"],
        "success": result["success"],
        "returncode": result["returncode"],
        "stdout": result["stdout"],
        "stderr": result["stderr"],
        "config": {
            "fuzz_target": fuzz_target,
            "package": package,
            "duration": duration,
            "corpus_dir": corpus_dir,
            "workers": workers
        },
        "note": "Fuzz testing completed. Check stdout/stderr for any discovered crashes or failures."
    }


@mcp.tool()
async def get_version_info(
    version_file: Optional[str] = "build/version/version.txt",
    format: Optional[str] = "text"
) -> dict:
    """
    Retrieve FerretDB build version information, including version number,
    commit hash, and build metadata. Use this to check what version is installed,
    verify build artifacts, or display version details.
    """
    version_data = {}

    # Read version file
    if version_file and os.path.exists(version_file):
        try:
            with open(version_file, "r") as f:
                raw_version = f.read().strip()
                # Strip leading 'v' as the Go code does
                version_str = raw_version.lstrip("v")
                version_data["version"] = version_str
                version_data["raw_version"] = raw_version
                version_data["version_file"] = version_file
        except Exception as e:
            version_data["version_file_error"] = str(e)
    else:
        version_data["version_file_error"] = f"Version file not found: {version_file}"

    # Try to get git info
    git_commit = _run_command(["git", "rev-parse", "HEAD"], timeout=10)
    if git_commit["success"]:
        version_data["commit"] = git_commit["stdout"].strip()

    git_branch = _run_command(["git", "rev-parse", "--abbrev-ref", "HEAD"], timeout=10)
    if git_branch["success"]:
        version_data["branch"] = git_branch["stdout"].strip()

    git_dirty = _run_command(["git", "status", "--porcelain"], timeout=10)
    if git_dirty["success"]:
        version_data["dirty"] = len(git_dirty["stdout"].strip()) > 0

    # Try go version
    go_version = _run_command(["go", "version"], timeout=10)
    if go_version["success"]:
        version_data["go_version"] = go_version["stdout"].strip()

    if format == "json":
        import json
        return {
            "format": "json",
            "data": version_data,
            "json": json.dumps(version_data, indent=2)
        }
    else:
        lines = []
        for k, v in version_data.items():
            lines.append(f"{k}: {v}")
        return {
            "format": "text",
            "data": version_data,
            "text": "\n".join(lines)
        }


@mcp.tool()
async def manage_directories(
    action: str,
    paths: List[str],
    recursive: Optional[bool] = True
) -> dict:
    """
    Create or remove directories needed for FerretDB development, testing, or
    build processes. Use this to set up workspace directories, clean build
    artifacts, or prepare test data directories.
    """
    if action not in ("create", "remove"):
        return {
            "success": False,
            "error": f"Invalid action '{action}'. Must be 'create' or 'remove'.",
            "results": []
        }

    results = []
    overall_success = True

    for path in paths:
        entry = {"path": path, "action": action}
        try:
            if action == "create":
                if recursive:
                    os.makedirs(path, exist_ok=True)
                else:
                    os.mkdir(path)
                entry["success"] = True
                entry["message"] = f"Directory created: {path}"
            elif action == "remove":
                if os.path.exists(path):
                    if recursive:
                        shutil.rmtree(path)
                    else:
                        os.rmdir(path)
                    entry["success"] = True
                    entry["message"] = f"Directory removed: {path}"
                else:
                    entry["success"] = True
                    entry["message"] = f"Directory does not exist (nothing to remove): {path}"
        except Exception as e:
            entry["success"] = False
            entry["error"] = str(e)
            overall_success = False

        results.append(entry)

    return {
        "success": overall_success,
        "action": action,
        "recursive": recursive,
        "results": results,
        "total": len(paths),
        "succeeded": sum(1 for r in results if r.get("success", False)),
        "failed": sum(1 for r in results if not r.get("success", False))
    }


@mcp.tool()
async def print_diagnostic_data(
    include_compose_logs: Optional[bool] = True,
    services: Optional[List[str]] = None,
    tail_lines: Optional[int] = 100,
    error_context: Optional[str] = None
) -> dict:
    """
    Collect and print diagnostic information about the FerretDB environment,
    including Docker Compose service logs and system state. Use this when
    debugging setup failures, test failures, or environment issues.
    """
    diagnostics = {
        "error_context": error_context,
        "sections": {}
    }

    # Docker Compose logs
    if include_compose_logs:
        log_args = ["docker", "compose", "logs", "--no-color"]
        if tail_lines:
            log_args.extend(["--tail", str(tail_lines)])
        if services:
            log_args.extend(services)
        log_result = _run_command(log_args, timeout=30)
        diagnostics["sections"]["compose_logs"] = {
            "command": log_result["command"],
            "success": log_result["success"],
            "output": log_result["stdout"],
            "stderr": log_result["stderr"]
        }

    # Docker Compose PS
    ps_result = _run_command(["docker", "compose", "ps", "--all"], timeout=15)
    diagnostics["sections"]["compose_ps"] = {
        "command": ps_result["command"],
        "success": ps_result["success"],
        "output": ps_result["stdout"]
    }

    # Docker stats
    stats_result = _run_command(["docker", "stats", "--all", "--no-stream"], timeout=15)
    diagnostics["sections"]["docker_stats"] = {
        "command": stats_result["command"],
        "success": stats_result["success"],
        "output": stats_result["stdout"]
    }

    # Git version
    git_result = _run_command(["git", "version"], timeout=10)
    diagnostics["sections"]["git_version"] = {
        "output": git_result["stdout"] if git_result["success"] else git_result["stderr"]
    }

    # Docker version
    docker_version_result = _run_command(["docker", "version"], timeout=10)
    diagnostics["sections"]["docker_version"] = {
        "output": docker_version_result["stdout"] if docker_version_result["success"] else docker_version_result["stderr"]
    }

    # Docker Compose version
    compose_version_result = _run_command(["docker", "compose", "version"], timeout=10)
    diagnostics["sections"]["compose_version"] = {
        "output": compose_version_result["stdout"] if compose_version_result["success"] else compose_version_result["stderr"]
    }

    # Go version
    go_version_result = _run_command(["go", "version"], timeout=10)
    diagnostics["sections"]["go_version"] = {
        "output": go_version_result["stdout"] if go_version_result["success"] else go_version_result["stderr"]
    }

    # FerretDB version file
    version_file = "build/version/version.txt"
    if os.path.exists(version_file):
        try:
            with open(version_file, "r") as f:
                diagnostics["sections"]["ferretdb_version"] = {"output": f.read().strip()}
        except Exception as e:
            diagnostics["sections"]["ferretdb_version"] = {"output": f"Error reading version file: {e}"}
    else:
        diagnostics["sections"]["ferretdb_version"] = {"output": "Version file not found"}

    # Build formatted report
    report_lines = []
    if error_context:
        report_lines.append(f"=== ERROR CONTEXT ===")
        report_lines.append(error_context)
        report_lines.append("")

    for section_name, section_data in diagnostics["sections"].items():
        report_lines.append(f"=== {section_name.upper().replace('_', ' ')} ===")
        report_lines.append(section_data.get("output", ""))
        report_lines.append("")

    diagnostics["report"] = "\n".join(report_lines)

    return diagnostics


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))))
