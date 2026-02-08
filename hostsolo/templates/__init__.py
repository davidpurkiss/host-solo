"""Template rendering for docker-compose files."""

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from hostsolo.config import AppConfig, HostSoloConfig

# Get template directory
TEMPLATE_DIR = Path(__file__).parent


def get_jinja_env() -> Environment:
    """Get configured Jinja2 environment."""
    return Environment(
        loader=FileSystemLoader(TEMPLATE_DIR),
        autoescape=select_autoescape(),
        trim_blocks=True,
        lstrip_blocks=True,
    )


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

    return template.render(
        config=config,
        app_name=app_name,
        app_config=app_config,
        env_name=env_name,
        domain=domain,
        local=local,
        volumes=processed_volumes,
        project_root=project_root,
    )
