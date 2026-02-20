"""Template rendering for docker-compose files."""

import re
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hostsolo.config import AppConfig, HostSoloConfig

# Get template directory
TEMPLATE_DIR = Path(__file__).parent


def _yaml_value(value: str) -> str:
    """Format a value for YAML output, using literal block style for multiline strings."""
    value = str(value)
    if "\n" in value:
        if value.endswith("\n"):
            indicator = "|"
            value = value[:-1]
        else:
            indicator = "|-"
        lines = value.split("\n")
        indented = "\n".join("        " + line if line.strip() else "" for line in lines)
        return indicator + "\n" + indented
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _load_env_file(path: Path) -> dict[str, str]:
    """Load a .env file into a dict, ignoring comments and blank lines."""
    env_vars: dict[str, str] = {}
    if not path.exists():
        return env_vars
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                env_vars[key.strip()] = value.strip()
    return env_vars


def _interpolate_env_vars(value: str, env_vars: dict[str, str]) -> str:
    """Replace ${VAR} references in value with values from env_vars dict."""

    def replace_match(match: re.Match) -> str:
        var_name = match.group(1)
        return env_vars.get(var_name, match.group(0))

    return re.sub(r"\$\{(\w+)\}", replace_match, value)


def get_jinja_env() -> Environment:
    """Get configured Jinja2 environment."""
    env = Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["yaml_value"] = _yaml_value
    return env


def render_traefik_compose(config: HostSoloConfig, local: bool = False) -> str:
    """Render the Traefik docker-compose.yml.

    Args:
        config: Host Solo configuration
        local: Whether to run in local development mode

    Returns:
        Rendered docker-compose.yml content
    """
    env = get_jinja_env()
    template = env.get_template("traefik/docker-compose.yml.j2")

    return template.render(
        config=config,
        local=local,
    )


def render_app_compose(
    config: HostSoloConfig,
    app_name: str,
    app_config: AppConfig,
    env_name: str,
    domain: str,
    local: bool = False,
) -> str:
    """Render an app's docker-compose.yml.

    Args:
        config: Host Solo configuration
        app_name: Name of the application
        app_config: Application configuration
        env_name: Environment name
        domain: Full domain for the app
        local: Whether to run in local development mode

    Returns:
        Rendered docker-compose.yml content
    """
    from hostsolo.config import get_project_root

    env = get_jinja_env()
    template = env.get_template("app/docker-compose.yml.j2")

    project_root = get_project_root()

    # Process volumes: replace ${ENV} placeholder and convert relative paths to absolute
    processed_volumes = []
    for v in app_config.volumes:
        v = v.replace("${ENV}", env_name)
        # Convert relative paths to absolute (compose file is in apps/{env}/{app}/)
        if v.startswith("./"):
            source, target = v.split(":", 1)
            source = str(project_root / source[2:])  # Remove ./ and make absolute
            v = f"{source}:{target}"
        processed_volumes.append(v)

    # Load env files for variable interpolation in environment values
    env_file_vars: dict[str, str] = {}
    shared_env = project_root / "config" / app_name / "shared.env"
    env_specific = project_root / "config" / app_name / f"{env_name}.env"
    env_file_vars.update(_load_env_file(shared_env))
    env_file_vars.update(_load_env_file(env_specific))

    # Interpolate ${VAR} references in environment values
    interpolated_env = {
        k: _interpolate_env_vars(v, env_file_vars)
        for k, v in app_config.environment.items()
    }

    return template.render(
        config=config,
        app_name=app_name,
        app_config=app_config,
        env_name=env_name,
        domain=domain,
        local=local,
        volumes=processed_volumes,
        project_root=project_root,
        environment=interpolated_env,
    )
