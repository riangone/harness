import os

# Lightweight config loader for models routing
# Falls back gracefully if PyYAML is missing or file can't be read.

_config_cache = None

def _get_harness_root():
    return os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))


def load_models_config():
    global _config_cache
    if _config_cache is not None:
        return _config_cache

    config = {}
    path = os.path.join(_get_harness_root(), "config", "models.yaml")
    try:
        import yaml
        with open(path, 'r', encoding='utf-8') as f:
            cfg = yaml.safe_load(f)
            if isinstance(cfg, dict):
                config = cfg
    except Exception:
        # If yaml not available or file missing, return empty config
        config = {}

    _config_cache = config
    return _config_cache


def preferred_cli_order_for_role(role: str) -> list:
    """Return a preferred ordered list of cli_command ids for the given role.
    Priority sources (in order): routing.fallback_chain -> providers.cli.models order filtered by role
    """
    cfg = load_models_config()
    order = []

    routing = cfg.get('routing', {}) if isinstance(cfg, dict) else {}
    chain = routing.get('fallback_chain', []) if isinstance(routing, dict) else []
    if isinstance(chain, list):
        for entry in chain:
            if isinstance(entry, dict):
                tries = entry.get('try', [])
                if isinstance(tries, list):
                    for cli in tries:
                        if cli not in order:
                            order.append(cli)

    if order:
        return order

    # Fallback: use providers.cli.models order
    providers = cfg.get('providers', {}) if isinstance(cfg, dict) else {}
    cli_section = providers.get('cli', {}) if isinstance(providers, dict) else {}
    models = cli_section.get('models', []) if isinstance(cli_section, dict) else []
    if isinstance(models, list):
        for m in models:
            try:
                roles = m.get('roles', [])
                if role in roles:
                    cli_id = m.get('id')
                    if cli_id and cli_id not in order:
                        order.append(cli_id)
            except Exception:
                continue

    return order
