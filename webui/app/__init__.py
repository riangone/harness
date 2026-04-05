from fastapi.templating import Jinja2Templates

_templates: Jinja2Templates | None = None


def register_templates(t: Jinja2Templates):
    global _templates
    _templates = t


def get_templates() -> Jinja2Templates:
    if _templates is None:
        raise RuntimeError("Templates not initialized")
    return _templates
