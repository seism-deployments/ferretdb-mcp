from fastmcp import FastMCP
import asyncio
import os
import subprocess
import shutil
from typing import Optional

mcp = FastMCP("ferretdb")


def _run_subprocess(args: list[str], timeout: int = 60) -> dict:
    """Run a subprocess and return structured output."""
    try:
        result = subprocess.run(
            args,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(args)
        }
    except subprocess.TimeoutExpired:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out after {timeout} seconds",
            "command": " ".join(args)
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Binary not found: {e}",
            "command": " ".join(args)
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": str(e),
            "command": " ".join(args)
        }


@mcp.tool()
async def run_ferretdb_server(
    listen_addr: str = "127.0.0.1:27017",
    postgresql_url: Optional[str] = None,
    log_level: str = "info",
    tls: bool = False,
    extra_flags: Optional[list] = None
) -> dict:
    """
    Start the FerretDB server process with specified configuration.
    Use this when you need to launch FerretDB as a MongoDB-compatible proxy
    connected to a PostgreSQL/DocumentDB backend. Supports configuring listen
    addresses, backend connection strings, TLS, logging, and other server options.
    """
    args = ["ferretdb"]

    if listen_addr:
        args.extend([f"--listen-addr={listen_addr}"])

    if postgresql_url:
        args.extend([f"--postgresql-url={postgresql_url}"])

    if log_level:
        args.extend([f"--log-level={log_level}"])

    if tls:
        args.append("--tls")

    if extra_flags:
        args.extend(extra_flags)

    # Check if ferretdb binary exists
    ferretdb_bin = shutil.which("ferretdb")
    if not ferretdb_bin:
        # Try common build output paths
        for candidate in ["./ferretdb", "./bin/ferretdb", "./build/ferretdb"]:
            if os.path.isfile(candidate):
                args[0] = candidate
                ferretdb_bin = candidate
                break

    if not ferretdb_bin and args[0] == "ferretdb":
        return {
            "success": False,
            "error": "ferretdb binary not found in PATH or common build directories",
            "attempted_command": " ".join(args),
            "suggestion": "Build FerretDB first with 'go build ./cmd/ferretdb/...' or ensure the binary is in PATH"
        }

    # Start the process in background (non-blocking)
    try:
        process = subprocess.Popen(
            args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Give it a moment to start or fail immediately
        await asyncio.sleep(1)
        poll_result = process.poll()
        if poll_result is not None:
            stdout, stderr = process.communicate(timeout=5)
            return {
                "success": False,
                "pid": None,
                "returncode": poll_result,
                "stdout": stdout,
                "stderr": stderr,
                "command": " ".join(args),
                "message": "FerretDB process exited immediately"
            }
        return {
            "success": True,
            "pid": process.pid,
            "command": " ".join(args),
            "listen_addr": listen_addr,
            "postgresql_url": postgresql_url,
            "log_level": log_level,
            "tls_enabled": tls,
            "message": f"FerretDB server started with PID {process.pid}. Use kill {process.pid} to stop it."
        }
    except FileNotFoundError:
        return {
            "success": False,
            "error": f"Binary not found: {args[0]}",
            "command": " ".join(args)
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "command": " ".join(args)
        }


@mcp.tool()
async def setup_environment(
    compose_file: Optional[str] = None,
    verbose: bool = False,
    skip_pull: bool = False
) -> dict:
    """
    Run the envtool setup subcommand to initialize and configure the development
    or test environment. Use this to prepare Docker services, check dependencies,
    and ensure all required infrastructure (PostgreSQL, DocumentDB extension, etc.)
    is ready before running tests or the server.
    """
    # Find envtool binary
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for candidate in ["./envtool", "./bin/envtool", "./cmd/envtool/envtool"]:
            if os.path.isfile(candidate):
                envtool_bin = candidate
                break

    if not envtool_bin:
        # Fall back to go run
        envtool_bin = None

    if envtool_bin:
        args = [envtool_bin, "setup"]
    else:
        args = ["go", "run", "./cmd/envtool", "setup"]

    if verbose:
        args.append("--verbose")

    if skip_pull:
        args.append("--skip-pull")

    if compose_file:
        args.extend(["--compose-file", compose_file])

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _run_subprocess(args, timeout=300))
    result["tool"] = "setup_environment"
    result["config"] = {
        "compose_file": compose_file,
        "verbose": verbose,
        "skip_pull": skip_pull
    }
    return result


@mcp.tool()
async def run_tests(
    packages: Optional[list] = None,
    run_filter: Optional[str] = None,
    timeout: str = "10m",
    tags: Optional[list] = None,
    short: bool = False,
    count: int = 1,
    verbose: bool = False
) -> dict:
    """
    Execute Go tests using the envtool test runner, which provides enhanced output
    formatting, panic recovery, and structured logging. Use this to run unit tests,
    integration tests, or specific test packages with proper test filtering and
    output handling.
    """
    if packages is None:
        packages = ["./..."]

    # Find envtool binary
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for candidate in ["./envtool", "./bin/envtool"]:
            if os.path.isfile(candidate):
                envtool_bin = candidate
                break

    if envtool_bin:
        args = [envtool_bin, "test"]
    else:
        args = ["go", "run", "./cmd/envtool", "test"]

    if run_filter:
        args.extend(["--run", run_filter])

    if timeout:
        args.extend(["--timeout", timeout])

    if tags:
        args.extend(["--tags", ",".join(tags)])

    if short:
        args.append("--short")

    if count and count != 1:
        args.extend(["--count", str(count)])

    if verbose:
        args.append("-v")

    args.extend(packages)

    # Parse timeout string to seconds for subprocess timeout
    timeout_seconds = 600
    try:
        if timeout.endswith("h"):
            timeout_seconds = int(timeout[:-1]) * 3600
        elif timeout.endswith("m"):
            timeout_seconds = int(timeout[:-1]) * 60
        elif timeout.endswith("s"):
            timeout_seconds = int(timeout[:-1])
    except (ValueError, IndexError):
        timeout_seconds = 600

    # Add buffer for process overhead
    subprocess_timeout = timeout_seconds + 60

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _run_subprocess(args, timeout=subprocess_timeout))
    result["tool"] = "run_tests"
    result["config"] = {
        "packages": packages,
        "run_filter": run_filter,
        "timeout": timeout,
        "tags": tags,
        "short": short,
        "count": count,
        "verbose": verbose
    }
    return result


@mcp.tool()
async def run_fuzz(
    fuzz_target: str,
    package: str,
    fuzz_time: str = "30s",
    corpus_dir: Optional[str] = None
) -> dict:
    """
    Execute Go fuzz tests using the envtool fuzz subcommand. Use this to run
    fuzzing campaigns against FerretDB to discover edge cases and bugs in protocol
    handling or BSON parsing. Supports selecting specific fuzz targets and
    controlling duration.
    """
    # Find envtool binary
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for candidate in ["./envtool", "./bin/envtool"]:
            if os.path.isfile(candidate):
                envtool_bin = candidate
                break

    if envtool_bin:
        args = [envtool_bin, "fuzz"]
    else:
        args = ["go", "run", "./cmd/envtool", "fuzz"]

    args.extend(["--fuzz", fuzz_target])
    args.extend(["--fuzz-time", fuzz_time])

    if corpus_dir:
        args.extend(["--corpus-dir", corpus_dir])

    args.append(package)

    # Parse fuzz_time to determine subprocess timeout
    fuzz_seconds = 30
    try:
        if fuzz_time.endswith("h"):
            fuzz_seconds = int(fuzz_time[:-1]) * 3600
        elif fuzz_time.endswith("m"):
            fuzz_seconds = int(fuzz_time[:-1]) * 60
        elif fuzz_time.endswith("s"):
            fuzz_seconds = int(fuzz_time[:-1])
    except (ValueError, IndexError):
        fuzz_seconds = 30

    subprocess_timeout = fuzz_seconds + 60

    loop = asyncio.get_event_loop()
    result = await loop.run_in_executor(None, lambda: _run_subprocess(args, timeout=subprocess_timeout))
    result["tool"] = "run_fuzz"
    result["config"] = {
        "fuzz_target": fuzz_target,
        "package": package,
        "fuzz_time": fuzz_time,
        "corpus_dir": corpus_dir
    }
    return result


@mcp.tool()
async def get_version_info(
    format: str = "text",
    version_file: str = "build/version/version.txt"
) -> dict:
    """
    Retrieve version information for the FerretDB build, including the version
    string, git commit hash, build date, and Go runtime version. Use this to
    verify which version is installed, inspect build metadata, or confirm a
    build was successful.
    """
    result = {
        "tool": "get_version_info",
        "format": format,
        "version_file": version_file
    }

    # Try reading the version file
    version_content = None
    if os.path.isfile(version_file):
        try:
            with open(version_file, "r") as f:
                version_content = f.read().strip()
            result["version_file_content"] = version_content
        except Exception as e:
            result["version_file_error"] = str(e)
    else:
        result["version_file_error"] = f"Version file not found: {version_file}"

    # Try running ferretdb --version
    ferretdb_bin = shutil.which("ferretdb")
    if not ferretdb_bin:
        for candidate in ["./ferretdb", "./bin/ferretdb", "./build/ferretdb"]:
            if os.path.isfile(candidate):
                ferretdb_bin = candidate
                break

    if ferretdb_bin:
        version_args = [ferretdb_bin, "--version"]
        if format == "json":
            version_args.append("--json")
        loop = asyncio.get_event_loop()
        version_result = await loop.run_in_executor(
            None, lambda: _run_subprocess(version_args, timeout=10)
        )
        result["ferretdb_version_output"] = version_result
    else:
        result["ferretdb_binary"] = "not found"

    # Try running envtool version
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        for candidate in ["./envtool", "./bin/envtool"]:
            if os.path.isfile(candidate):
                envtool_bin = candidate
                break

    if envtool_bin:
        envtool_args = [envtool_bin, "version"]
        if format == "json":
            envtool_args.append("--json")
        loop = asyncio.get_event_loop()
        envtool_result = await loop.run_in_executor(
            None, lambda: _run_subprocess(envtool_args, timeout=10)
        )
        result["envtool_version_output"] = envtool_result
    else:
        result["envtool_binary"] = "not found"

    # Get Go version
    loop = asyncio.get_event_loop()
    go_result = await loop.run_in_executor(
        None, lambda: _run_subprocess(["go", "version"], timeout=10)
    )
    result["go_version"] = go_result

    return result


@mcp.tool()
async def print_diagnostic_data(
    include_compose_logs: bool = True,
    setup_error_message: Optional[str] = None,
    output_file: Optional[str] = None
) -> dict:
    """
    Collect and display diagnostic information about the FerretDB environment,
    including Docker Compose service logs and system state. Use this when debugging
    test failures, setup issues, or unexpected server behavior to gather context
    about what went wrong.
    """
    diagnostics = {
        "tool": "print_diagnostic_data",
        "setup_error_message": setup_error_message,
        "output": {}
    }

    loop = asyncio.get_event_loop()

    if include_compose_logs:
        compose_logs = await loop.run_in_executor(
            None, lambda: _run_subprocess(["docker", "compose", "logs"], timeout=30)
        )
        diagnostics["output"]["compose_logs"] = compose_logs

        compose_ps = await loop.run_in_executor(
            None, lambda: _run_subprocess(["docker", "compose", "ps", "--all"], timeout=30)
        )
        diagnostics["output"]["compose_ps"] = compose_ps

        docker_stats = await loop.run_in_executor(
            None, lambda: _run_subprocess(["docker", "stats", "--all", "--no-stream"], timeout=30)
        )
        diagnostics["output"]["docker_stats"] = docker_stats

    # Git version
    git_version = await loop.run_in_executor(
        None, lambda: _run_subprocess(["git", "version"], timeout=10)
    )
    diagnostics["output"]["git_version"] = git_version

    # Docker version
    docker_version = await loop.run_in_executor(
        None, lambda: _run_subprocess(["docker", "version"], timeout=10)
    )
    diagnostics["output"]["docker_version"] = docker_version

    # Docker compose version
    compose_version = await loop.run_in_executor(
        None, lambda: _run_subprocess(["docker", "compose", "version"], timeout=10)
    )
    diagnostics["output"]["compose_version"] = compose_version

    # Go version
    go_version = await loop.run_in_executor(
        None, lambda: _run_subprocess(["go", "version"], timeout=10)
    )
    diagnostics["output"]["go_version"] = go_version

    # Read version file if it exists
    version_file = "build/version/version.txt"
    if os.path.isfile(version_file):
        try:
            with open(version_file, "r") as f:
                diagnostics["output"]["ferretdb_version_file"] = f.read().strip()
        except Exception as e:
            diagnostics["output"]["ferretdb_version_file_error"] = str(e)

    # Build summary output string
    summary_lines = []
    if setup_error_message:
        summary_lines.append(f"Setup Error: {setup_error_message}")
    for key, val in diagnostics["output"].items():
        summary_lines.append(f"\n=== {key} ===")
        if isinstance(val, dict):
            if val.get("stdout"):
                summary_lines.append(val["stdout"])
            if val.get("stderr"):
                summary_lines.append(f"STDERR: {val['stderr']}")
        else:
            summary_lines.append(str(val))

    summary = "\n".join(summary_lines)
    diagnostics["summary"] = summary

    if output_file:
        try:
            os.makedirs(os.path.dirname(output_file) if os.path.dirname(output_file) else ".", exist_ok=True)
            with open(output_file, "w") as f:
                f.write(summary)
            diagnostics["written_to_file"] = output_file
        except Exception as e:
            diagnostics["file_write_error"] = str(e)

    return diagnostics


@mcp.tool()
async def shell_operations(
    operation: str,
    paths: list
) -> dict:
    """
    Perform shell utility operations used during environment management: create
    directories, remove directories, or read file contents. Use this to manage
    the FerretDB build/test environment file system, such as creating test output
    directories or reading configuration files.
    """
    if not paths:
        return {
            "success": False,
            "error": "No paths provided",
            "operation": operation
        }

    results = []
    overall_success = True

    if operation == "mkdir":
        for path in paths:
            try:
                os.makedirs(path, exist_ok=True)
                results.append({"path": path, "success": True, "message": f"Directory created: {path}"})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
                overall_success = False

    elif operation == "rmdir":
        for path in paths:
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                    results.append({"path": path, "success": True, "message": f"Directory removed: {path}"})
                else:
                    results.append({"path": path, "success": True, "message": f"Directory did not exist: {path}"})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
                overall_success = False

    elif operation == "read":
        for path in paths:
            try:
                if not os.path.isfile(path):
                    results.append({"path": path, "success": False, "error": f"File not found: {path}"})
                    overall_success = False
                    continue
                with open(path, "r", errors="replace") as f:
                    content = f.read()
                results.append({"path": path, "success": True, "content": content})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
                overall_success = False
    else:
        return {
            "success": False,
            "error": f"Unknown operation: '{operation}'. Must be one of: mkdir, rmdir, read",
            "operation": operation
        }

    return {
        "success": overall_success,
        "operation": operation,
        "results": results
    }


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
