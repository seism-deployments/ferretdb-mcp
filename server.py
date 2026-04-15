from fastmcp import FastMCP
import subprocess
import os
import shutil
from typing import Optional, List

mcp = FastMCP("FerretDB")


def _run_command(cmd: List[str], capture_output: bool = True) -> dict:
    """Helper to run a subprocess command and return result."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=capture_output,
            text=True,
            timeout=300
        )
        return {
            "success": result.returncode == 0,
            "returncode": result.returncode,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "command": " ".join(cmd)
        }
    except subprocess.TimeoutExpired as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Command timed out: {str(e)}",
            "command": " ".join(cmd)
        }
    except FileNotFoundError as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Executable not found: {str(e)}",
            "command": " ".join(cmd)
        }
    except Exception as e:
        return {
            "success": False,
            "returncode": -1,
            "stdout": "",
            "stderr": f"Unexpected error: {str(e)}",
            "command": " ".join(cmd)
        }


@mcp.tool()
async def run_ferretdb(
    listen_addr: Optional[str] = "127.0.0.1:27017",
    postgresql_url: Optional[str] = None,
    log_level: Optional[str] = "info",
    log_format: Optional[str] = "console",
    tls: Optional[bool] = False,
    tls_cert_file: Optional[str] = None,
    tls_key_file: Optional[str] = None
) -> dict:
    """
    Start the FerretDB server with specified configuration.
    Use this when you need to launch the FerretDB proxy that converts MongoDB wire protocol
    to SQL for PostgreSQL with DocumentDB extension.
    Supports configuring listen address, backend, logging, and TLS options.
    """
    cmd = ["ferretdb"]

    if listen_addr:
        cmd.extend(["--listen-addr", listen_addr])

    if postgresql_url:
        cmd.extend(["--postgresql-url", postgresql_url])

    if log_level:
        cmd.extend(["--log-level", log_level])

    if log_format:
        cmd.extend(["--log-format", log_format])

    if tls:
        cmd.append("--tls")

    if tls_cert_file:
        cmd.extend(["--tls-cert-file", tls_cert_file])

    if tls_key_file:
        cmd.extend(["--tls-key-file", tls_key_file])

    # Check if ferretdb binary exists
    if not shutil.which("ferretdb"):
        return {
            "success": False,
            "error": "ferretdb binary not found in PATH",
            "command": " ".join(cmd),
            "suggestion": "Please ensure FerretDB is installed and available in your PATH"
        }

    result = _run_command(cmd)
    result["config"] = {
        "listen_addr": listen_addr,
        "postgresql_url": postgresql_url,
        "log_level": log_level,
        "log_format": log_format,
        "tls": tls,
        "tls_cert_file": tls_cert_file,
        "tls_key_file": tls_key_file
    }
    return result


@mcp.tool()
async def setup_environment(
    compose_file: Optional[str] = None,
    log_level: Optional[str] = "info",
    services: Optional[List[str]] = None
) -> dict:
    """
    Set up the development or test environment for FerretDB using envtool.
    Use this to initialize required services, create directories, pull Docker images,
    and prepare the environment before running tests or development work.
    This runs the envtool setup subcommand.
    """
    # Check if envtool binary exists
    envtool_bin = shutil.which("envtool")
    if not envtool_bin:
        # Try go run as fallback
        envtool_bin = None

    cmd = []
    if envtool_bin:
        cmd = ["envtool", "setup"]
    else:
        cmd = ["go", "run", "./cmd/envtool", "setup"]

    if compose_file:
        cmd.extend(["--compose-file", compose_file])

    if log_level:
        cmd.extend(["--log-level", log_level])

    if services:
        for service in services:
            cmd.append(service)

    result = _run_command(cmd)
    result["setup_config"] = {
        "compose_file": compose_file,
        "log_level": log_level,
        "services": services
    }
    return result


@mcp.tool()
async def run_tests(
    packages: Optional[List[str]] = None,
    run_filter: Optional[str] = None,
    timeout: Optional[str] = "10m",
    count: Optional[int] = 1,
    short: Optional[bool] = False,
    verbose: Optional[bool] = False,
    tags: Optional[List[str]] = None
) -> dict:
    """
    Run FerretDB Go tests using envtool's test runner, which provides enhanced output formatting,
    test filtering, and result reporting. Use this to execute unit tests, integration tests,
    or specific test packages with detailed pass/fail/skip reporting.
    """
    if packages is None:
        packages = ["./..."]

    # Check if envtool binary exists
    envtool_bin = shutil.which("envtool")

    cmd = []
    if envtool_bin:
        cmd = ["envtool", "test"]
    else:
        cmd = ["go", "run", "./cmd/envtool", "test"]

    if timeout:
        cmd.extend(["--timeout", timeout])

    if count is not None and count != 1:
        cmd.extend(["--count", str(count)])

    if short:
        cmd.append("--short")

    if verbose:
        cmd.append("--verbose")

    if tags:
        cmd.extend(["--tags", ",".join(tags)])

    if run_filter:
        cmd.extend(["--run", run_filter])

    cmd.extend(packages)

    result = _run_command(cmd)
    result["test_config"] = {
        "packages": packages,
        "run_filter": run_filter,
        "timeout": timeout,
        "count": count,
        "short": short,
        "verbose": verbose,
        "tags": tags
    }
    return result


@mcp.tool()
async def run_fuzz(
    fuzz_target: str,
    package: str,
    fuzz_time: Optional[str] = "30s",
    corpus_dir: Optional[str] = None,
    parallel: Optional[int] = None
) -> dict:
    """
    Run fuzz tests for FerretDB using envtool's fuzz subcommand.
    Use this to execute Go fuzz testing against specific fuzz targets to discover
    edge cases and potential bugs in FerretDB's protocol handling or data processing.
    """
    # Check if envtool binary exists
    envtool_bin = shutil.which("envtool")

    cmd = []
    if envtool_bin:
        cmd = ["envtool", "fuzz"]
    else:
        cmd = ["go", "run", "./cmd/envtool", "fuzz"]

    if fuzz_time:
        cmd.extend(["--fuzz-time", fuzz_time])

    if corpus_dir:
        cmd.extend(["--corpus-dir", corpus_dir])

    if parallel is not None:
        cmd.extend(["--parallel", str(parallel)])

    cmd.extend(["--fuzz", fuzz_target, package])

    result = _run_command(cmd)
    result["fuzz_config"] = {
        "fuzz_target": fuzz_target,
        "package": package,
        "fuzz_time": fuzz_time,
        "corpus_dir": corpus_dir,
        "parallel": parallel
    }
    return result


@mcp.tool()
async def print_version(
    format: Optional[str] = "text"
) -> dict:
    """
    Print FerretDB version information including build metadata, Git commit hash, and Go runtime version.
    Use this to check the current version of FerretDB being used or to retrieve version info
    for debugging and reporting purposes.
    """
    results = {}

    # Try ferretdb binary first
    ferretdb_bin = shutil.which("ferretdb")
    if ferretdb_bin:
        if format == "json":
            cmd = ["ferretdb", "--version", "--log-format", "json"]
        else:
            cmd = ["ferretdb", "--version"]
        ferretdb_result = _run_command(cmd)
        results["ferretdb"] = ferretdb_result
    else:
        results["ferretdb"] = {
            "success": False,
            "error": "ferretdb binary not found in PATH"
        }

    # Try envtool version as well
    envtool_bin = shutil.which("envtool")
    if envtool_bin:
        if format == "json":
            envtool_cmd = ["envtool", "version", "--json"]
        else:
            envtool_cmd = ["envtool", "version"]
        envtool_result = _run_command(envtool_cmd)
        results["envtool"] = envtool_result
    else:
        # Try via go run
        go_bin = shutil.which("go")
        if go_bin:
            go_cmd = ["go", "run", "./cmd/envtool", "version"]
            go_result = _run_command(go_cmd)
            results["envtool_via_go"] = go_result
        else:
            results["envtool"] = {
                "success": False,
                "error": "envtool binary and go not found in PATH"
            }

    results["format"] = format
    return results


@mcp.tool()
async def shell_run(
    operation: str,
    paths: Optional[List[str]] = None,
    command: Optional[str] = None,
    args: Optional[List[str]] = None
) -> dict:
    """
    Execute shell utility operations via envtool's shell subcommand, including creating directories,
    removing directories, reading files, or running arbitrary shell commands needed for build
    and development workflows. Use this for file system operations during CI/CD or development setup.
    """
    valid_operations = ["mkdir", "rmdir", "read", "exec"]
    if operation not in valid_operations:
        return {
            "success": False,
            "error": f"Invalid operation '{operation}'. Must be one of: {', '.join(valid_operations)}"
        }

    envtool_bin = shutil.which("envtool")

    if operation == "mkdir":
        if not paths:
            return {"success": False, "error": "paths is required for mkdir operation"}
        results = []
        for path in paths:
            try:
                os.makedirs(path, exist_ok=True)
                results.append({"path": path, "success": True})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
        return {
            "success": all(r["success"] for r in results),
            "operation": "mkdir",
            "results": results
        }

    elif operation == "rmdir":
        if not paths:
            return {"success": False, "error": "paths is required for rmdir operation"}
        results = []
        for path in paths:
            try:
                if os.path.exists(path):
                    shutil.rmtree(path)
                    results.append({"path": path, "success": True, "removed": True})
                else:
                    results.append({"path": path, "success": True, "removed": False, "note": "path did not exist"})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
        return {
            "success": all(r["success"] for r in results),
            "operation": "rmdir",
            "results": results
        }

    elif operation == "read":
        if not paths:
            return {"success": False, "error": "paths is required for read operation"}
        results = []
        for path in paths:
            try:
                with open(path, "r") as f:
                    content = f.read()
                results.append({"path": path, "success": True, "content": content})
            except Exception as e:
                results.append({"path": path, "success": False, "error": str(e)})
        return {
            "success": all(r["success"] for r in results),
            "operation": "read",
            "results": results
        }

    elif operation == "exec":
        if not command:
            return {"success": False, "error": "command is required for exec operation"}

        exec_cmd = [command]
        if args:
            exec_cmd.extend(args)

        result = _run_command(exec_cmd)
        result["operation"] = "exec"
        return result

    return {"success": False, "error": f"Unhandled operation: {operation}"}


@mcp.tool()
async def get_diagnostic_data(
    include_docker_logs: Optional[bool] = True,
    services: Optional[List[str]] = None,
    tail_lines: Optional[int] = 100,
    output_file: Optional[str] = None
) -> dict:
    """
    Collect and print diagnostic data about the FerretDB environment, including Docker Compose
    service logs and system information. Use this when troubleshooting failures, investigating
    test errors, or gathering information about the running environment state.
    """
    diagnostic_results = {}

    if include_docker_logs:
        # docker compose logs
        logs_cmd = ["docker", "compose", "logs", f"--tail={tail_lines}"]
        if services:
            logs_cmd.extend(services)
        docker_logs_result = _run_command(logs_cmd)
        diagnostic_results["docker_compose_logs"] = docker_logs_result

        # docker compose ps
        ps_result = _run_command(["docker", "compose", "ps", "--all"])
        diagnostic_results["docker_compose_ps"] = ps_result

        # docker stats
        stats_result = _run_command(["docker", "stats", "--all", "--no-stream"])
        diagnostic_results["docker_stats"] = stats_result

    # System info
    git_result = _run_command(["git", "version"])
    diagnostic_results["git_version"] = git_result

    docker_version_result = _run_command(["docker", "version"])
    diagnostic_results["docker_version"] = docker_version_result

    compose_version_result = _run_command(["docker", "compose", "version"])
    diagnostic_results["docker_compose_version"] = compose_version_result

    go_version_result = _run_command(["go", "version"])
    diagnostic_results["go_version"] = go_version_result

    # FerretDB version if available
    ferretdb_bin = shutil.which("ferretdb")
    if ferretdb_bin:
        ferretdb_version = _run_command(["ferretdb", "--version"])
        diagnostic_results["ferretdb_version"] = ferretdb_version

    # Compile full output
    output_lines = ["=== FerretDB Diagnostic Data ==="]
    for key, val in diagnostic_results.items():
        output_lines.append(f"
--- {key} ---")
        if isinstance(val, dict):
            if val.get("stdout"):
                output_lines.append(val["stdout"])
            if val.get("stderr"):
                output_lines.append(f"STDERR: {val['stderr']}")
            if val.get("error"):
                output_lines.append(f"ERROR: {val['error']}")
        else:
            output_lines.append(str(val))

    full_output = "
".join(output_lines)

    if output_file:
        try:
            with open(output_file, "w") as f:
                f.write(full_output)
            diagnostic_results["output_file"] = {
                "success": True,
                "path": output_file,
                "bytes_written": len(full_output)
            }
        except Exception as e:
            diagnostic_results["output_file"] = {
                "success": False,
                "error": str(e)
            }

    diagnostic_results["full_output"] = full_output
    diagnostic_results["config"] = {
        "include_docker_logs": include_docker_logs,
        "services": services,
        "tail_lines": tail_lines,
        "output_file": output_file
    }

    return diagnostic_results


if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
