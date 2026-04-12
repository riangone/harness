"""
Harness 2.0 - Core Gateway Package
网关集成：邮件、WebUI等外部系统对接
"""

from .mail import MailGateway

__all__ = ['MailGateway']
