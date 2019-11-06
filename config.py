# coding=utf-8

import os
import jinja2
from dmutils.status import get_version_label
from dmutils.asset_fingerprint import AssetFingerprinter


class Config(object):

    VERSION = get_version_label(
        os.path.abspath(os.path.dirname(__file__))
    )
    SESSION_COOKIE_NAME = 'dm_session'
    SESSION_COOKIE_PATH = '/'
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SECURE = True

    PERMANENT_SESSION_LIFETIME = 3600  # 1 hour

    DM_COOKIE_PROBE_EXPECT_PRESENT = True

    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None

    DM_DATA_API_URL = None
    DM_DATA_API_AUTH_TOKEN = None
    DM_NOTIFY_API_KEY = None

    DEBUG = False

    NOTIFY_TEMPLATES = {
        "clarification_question": "520e0623-119e-41ac-990b-b9cdb0e9c30d",
        "clarification_question_confirmation": "d74a8a05-eae6-49cb-bc08-63d95b92b4d3",
    }

    SECRET_KEY = None

    STATIC_URL_PATH = '/suppliers/opportunities/static'
    ASSET_PATH = STATIC_URL_PATH + '/'
    BASE_TEMPLATE_DATA = {
        'header_class': 'with-proposition',
        'asset_path': ASSET_PATH,
        'asset_fingerprinter': AssetFingerprinter(asset_root=ASSET_PATH)
    }

    # Logging
    DM_LOG_LEVEL = 'DEBUG'
    DM_PLAIN_TEXT_LOGS = False
    DM_LOG_PATH = None
    DM_APP_NAME = 'brief-responses-frontend'

    @staticmethod
    def init_app(app):
        repo_root = os.path.abspath(os.path.dirname(__file__))
        digitalmarketplace_govuk_frontend = os.path.join(repo_root, "node_modules", "digitalmarketplace-govuk-frontend")
        template_folders = [
            os.path.join(repo_root, "app", "templates"),
            os.path.join(digitalmarketplace_govuk_frontend, "digitalmarketplace", "templates"),
            os.path.join(digitalmarketplace_govuk_frontend, "govuk-frontend"),
        ]
        jinja_loader = jinja2.FileSystemLoader(template_folders)
        app.jinja_loader = jinja_loader


class Test(Config):
    DEBUG = True
    DM_PLAIN_TEXT_LOGS = True
    DM_LOG_LEVEL = 'CRITICAL'
    WTF_CSRF_ENABLED = False
    SERVER_NAME = 'localhost.localdomain'
    DM_NOTIFY_API_KEY = 'not_a_real_key'
    SECRET_KEY = 'verySecretKey'

    DM_DATA_API_AUTH_TOKEN = 'myToken'


class Development(Config):
    DEBUG = True
    DM_PLAIN_TEXT_LOGS = True
    SESSION_COOKIE_SECURE = False

    DM_DATA_API_URL = f"http://localhost:{os.getenv('DM_API_PORT', 5000)}"
    DM_DATA_API_AUTH_TOKEN = "myToken"
    DM_API_AUTH_TOKEN = "myToken"

    DM_NOTIFY_API_KEY = "not_a_real_key"
    SECRET_KEY = 'verySecretKey'


class Live(Config):
    """Base config for deployed environments"""
    DEBUG = False
    DM_LOG_PATH = '/var/log/digitalmarketplace/application.log'
    DM_HTTP_PROTO = 'https'

    # use of invalid email addresses with live api keys annoys Notify
    DM_NOTIFY_REDIRECT_DOMAINS_TO_ADDRESS = {
        "example.com": "success@simulator.amazonses.com",
        "example.gov.uk": "success@simulator.amazonses.com",
        "user.marketplace.team": "success@simulator.amazonses.com",
    }


class Preview(Live):
    pass


class Production(Live):
    pass


class Staging(Production):
    pass


configs = {
    'development': Development,
    'preview': Preview,
    'staging': Staging,
    'production': Production,
    'test': Test,
}
