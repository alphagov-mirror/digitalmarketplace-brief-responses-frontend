# coding=utf-8
import mock
from lxml import html
from wtforms import ValidationError
from werkzeug.exceptions import BadRequest

from .helpers import BaseApplicationTest
from dmtestutils.api_model_stubs import BriefStub
from dmapiclient.errors import HTTPError


class TestApplication(BaseApplicationTest):
    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client')
        self.data_api_client = self.data_api_client_patch.start()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()
        self.login()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_response_headers(self):
        response = self.client.get('/suppliers/opportunities/1/ask-a-question')

        assert response.status_code == 200
        assert (
            response.headers['cache-control'] ==
            "no-cache"
        )

    def test_url_with_non_canonical_trailing_slash(self):
        response = self.client.get('/suppliers/opportunities/')
        assert response.status_code == 301
        assert "http://localhost.localdomain/suppliers/opportunities" == response.location

    @mock.patch('app.main.briefs.get_brief')
    def test_400(self, get_brief):
        get_brief.side_effect = BadRequest()

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')

        assert res.status_code == 400
        assert "Sorry, there was a problem with your request" in res.get_data(as_text=True)
        assert "Please do not attempt the same request again." in res.get_data(as_text=True)

    def test_404(self):
        res = self.client.get("/service/1234")
        assert res.status_code == 404
        html = res.get_data(as_text=True)
        assert (
            "Check you’ve entered the correct web address"
            " or start again on the Digital Marketplace homepage." in html
        )
        assert (
            "If you can’t find what you’re looking for, contact us at "
            '<a class="govuk-link" href="mailto:cloud_digital@crowncommercial.gov.uk?'
            'subject=Digital%20Marketplace%20feedback" title="Please '
            'send feedback to cloud_digital@crowncommercial.gov.uk">'
            "cloud_digital@crowncommercial.gov.uk</a>" in html
        )

    def test_503(self):
        self.data_api_client.get_brief.side_effect = HTTPError('API is down')
        self.app.config['DEBUG'] = False

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 503
        assert u"Sorry, we’re experiencing technical difficulties" in res.get_data(as_text=True)
        assert "Try again later." in res.get_data(as_text=True)

    def test_header_xframeoptions_set_to_deny(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 200
        assert 'DENY', res.headers['X-Frame-Options']

    def test_should_use_local_cookie_page_on_cookie_message(self):
        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 200

        document = html.fromstring(res.get_data(as_text=True))
        cookie_banner = document.xpath('//div[@id="dm-cookie-banner"]')
        assert cookie_banner[0].xpath('//h2//text()')[0].strip() == "Can we store analytics cookies on your device?"

    @mock.patch('flask_wtf.csrf.validate_csrf', autospec=True)
    def test_csrf_handler_redirects_to_login(self, validate_csrf):
        self.login()

        with self.app.app_context():
            self.app.config['WTF_CSRF_ENABLED'] = True
            self.client.set_cookie(
                "localhost",
                self.app.config['DM_COOKIE_PROBE_COOKIE_NAME'],
                self.app.config['DM_COOKIE_PROBE_COOKIE_VALUE'],
            )

            # This will raise a CSRFError for us when the form is validated
            validate_csrf.side_effect = ValidationError('The CSRF session token is missing.')

            res = self.client.post(
                '/suppliers/opportunities/1/ask-a-question', data={'clarification_question': 'blah'},
            )

            self.assert_flashes("Your session has expired. Please log in again.", expected_category="error")
            assert res.status_code == 302

            # POST requests will not preserve the request path on redirect
            assert res.location == 'http://localhost.localdomain/user/login'
            assert validate_csrf.call_args_list == [mock.call(None)]
