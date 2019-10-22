# -*- coding: utf-8 -*-
import mock
import pytest
import re

from datetime import datetime, timedelta
from lxml import html
from werkzeug.http import parse_cookie

from dmtestutils.login import login_for_tests
from dmutils.formats import DATETIME_FORMAT

from app import create_app, data_api_client


class BaseApplicationTest(object):
    def setup_method(self, method):
        self.app_env_var_mock = mock.patch.dict('gds_metrics.os.environ', {'PROMETHEUS_METRICS_PATH': '_metrics'})
        self.app_env_var_mock.start()

        self.app = create_app('test')
        self.app.register_blueprint(login_for_tests)
        self.client = self.app.test_client()
        self.get_user_patch = None

    def teardown_method(self, method):
        self.teardown_login()
        self.app_env_var_mock.stop()

    @staticmethod
    def get_cookie_by_name(response, name):
        cookies = response.headers.getlist('Set-Cookie')
        for cookie in cookies:
            if name in parse_cookie(cookie):
                return parse_cookie(cookie)
        return None

    @staticmethod
    def supplier():
        return {
            "suppliers": {
                "id": 12345,
                "name": "Supplier Name",
                'description': 'Supplier Description',
                'dunsNumber': '999999999',
                'companiesHouseId': 'SC009988',
                'contactInformation': [{
                    'id': 1234,
                    'contactName': 'contact name',
                    'phoneNumber': '099887',
                    'email': 'email@email.com',
                    'website': 'http://myweb.com',
                }],
                'clients': ['one client', 'two clients']
            }
        }

    @staticmethod
    def user(id, email_address, supplier_id, supplier_name, name,
             is_token_valid=True, locked=False, active=True, role='buyer'):

        hours_offset = -1 if is_token_valid else 1
        date = datetime.utcnow() + timedelta(hours=hours_offset)
        password_changed_at = date.strftime(DATETIME_FORMAT)

        user = {
            "id": id,
            "emailAddress": email_address,
            "name": name,
            "role": role,
            "locked": locked,
            'active': active,
            'passwordChangedAt': password_changed_at
        }

        if supplier_id:
            supplier = {
                "supplierId": supplier_id,
                "name": supplier_name,
            }
            user['role'] = 'supplier'
            user['supplier'] = supplier
        return {
            "users": user
        }

    @staticmethod
    def strip_all_whitespace(content):
        pattern = re.compile(r'\s+')
        return re.sub(pattern, '', content)

    @staticmethod
    def services():
        return {
            'services': [
                {
                    'id': 'id',
                    'serviceName': 'serviceName',
                    'frameworkName': 'frameworkName',
                    'lot': 'lot',
                    'serviceSummary': 'serviceSummary'
                }
            ]
        }

    @staticmethod
    def framework(
            status='open',
            name='G-Cloud 7',
            slug='g-cloud-7',
            clarification_questions_open=True,
            framework_agreement_version=None
    ):
        if 'g-cloud-' in slug:
            if slug == 'g-cloud-9':
                lots = [
                    {'id': 1, 'slug': 'cloud-hosting', 'name': 'Cloud hosting', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 2, 'slug': 'cloud-software', 'name': 'Cloud software', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 3, 'slug': 'cloud-support', 'name': 'Cloud support', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                ]
            else:
                lots = [
                    {'id': 1, 'slug': 'iaas', 'name': 'Infrastructure as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 2, 'slug': 'scs', 'name': 'Specialist Cloud Services', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 3, 'slug': 'paas', 'name': 'Platform as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                    {'id': 4, 'slug': 'saas', 'name': 'Software as a Service', 'oneServiceLimit': False,
                     'unitSingular': 'service', 'unitPlural': 'service'},
                ]
            metaframework = "g-cloud"
        elif 'digital-outcomes-and-specialists' in slug:
            lots = [
                {'id': 1, 'slug': 'digital-specialists', 'name': 'Digital specialists', 'oneServiceLimit': True,
                 'unitSingular': 'service', 'unitPlural': 'service'},
            ]
            metaframework = "digital-outcomes-and-specialists"

        return {
            'frameworks': {
                'status': status,
                'clarificationQuestionsOpen': clarification_questions_open,
                'name': name,
                'slug': slug,
                'lots': lots,
                'frameworkAgreementVersion': framework_agreement_version,
                'framework': metaframework,
            }
        }

    @staticmethod
    def framework_agreement(
            id=234,
            supplier_id=1234,
            framework_slug="g-cloud-8",
            signed_agreement_details=None,
            signed_agreement_path=None
    ):
        return {
            "agreement": {
                "id": id,
                "supplierId": supplier_id,
                "frameworkSlug": framework_slug,
                "signedAgreementDetails": signed_agreement_details,
                "signedAgreementPath": signed_agreement_path
            }
        }

    @staticmethod
    def brief_response(
            id=5,
            brief_id=1234,
            supplier_id=1234,
            data=None
    ):
        result = {
            "briefResponses": {
                "id": id,
                "briefId": brief_id,
                "supplierId": supplier_id,
                'brief': {
                    'framework': {
                        'slug': 'digital-outcomes-and-specialists-2',
                        'family': 'digital-outcomes-and-specialists',
                        'name': 'Digital Outcomes and Specialists 2',
                        'status': 'live'
                    }
                }
            }
        }

        if data:
            result['briefResponses'].update(data)

        return result

    def teardown_login(self):
        if self.get_user_patch is not None:
            self.get_user_patch.stop()

    def login(self):
        with mock.patch('app.data_api_client') as login_api_client:
            login_api_client.authenticate_user.return_value = self.user(
                123, "email@email.com", 1234, u'Supplier NĀme', u'Năme')

            self.get_user_patch = mock.patch.object(
                data_api_client,
                'get_user',
                return_value=self.user(123, "email@email.com", 1234, u'Supplier NĀme', u'Năme')
            )
            self.get_user_patch.start()

            response = self.client.get("/auto-supplier-login")
            assert response.status_code == 200

    def login_as_buyer(self):
        with mock.patch('app.data_api_client') as login_api_client:
            login_api_client.authenticate_user.return_value = self.user(
                234, "buyer@email.com", None, None, 'Ā Buyer', role='buyer')

            self.get_user_patch = mock.patch.object(
                data_api_client,
                'get_user',
                return_value=self.user(234, "buyer@email.com", None, None, 'Buyer', role='buyer')
            )
            self.get_user_patch.start()

            response = self.client.get("/auto-buyer-login")
            assert response.status_code == 200

    def assert_in_strip_whitespace(self, needle, haystack):
        assert self.strip_all_whitespace(needle) in self.strip_all_whitespace(haystack)

    def assert_not_in_strip_whitespace(self, needle, haystack):
        assert self.strip_all_whitespace(needle) not in self.strip_all_whitespace(haystack)

    # Method to test flashes taken from http://blog.paulopoiati.com/2013/02/22/testing-flash-messages-in-flask/
    def assert_flashes(self, expected_message, expected_category='message'):
        with self.client.session_transaction() as session:
            try:
                category, message = session['_flashes'][0]
            except KeyError:
                raise AssertionError('nothing flashed')
            try:
                assert expected_message == message or expected_message in message
            except TypeError:
                # presumably this was raised from the "in" test being reached and fed types which don't support "in".
                # either way, a failure.
                pytest.fail("Flash message contents not found in _flashes")
            assert expected_category == category

    def assert_no_flashes(self):
        with self.client.session_transaction() as session:
            assert not session.get("_flashes")

    def assert_breadcrumbs(self, response, expected_breadcrumbs):
        """
        Example expected breadcrumbs:
        expected_breadcrumbs = [
            ('Digital Marketplace', '/'),
            ('Supplier opportunities', '/digital-outcomes-and-specialists/opportunities'),
            ('Brief title', '/digital-outcomes-and-specialists/opportunities/127'),
            ('Question title', 'without href')
        ]
        """
        breadcrumbs = html.fromstring(response.get_data(as_text=True)).xpath(
            '//*[@class="govuk-breadcrumbs"]/ol/li'
        )

        assert len(breadcrumbs) == len(expected_breadcrumbs)

        for index, link in enumerate(expected_breadcrumbs):
            if index + 1 < len(expected_breadcrumbs):  # last item must not have a href
                assert breadcrumbs[index].find('a').text_content().strip() == link[0]
                assert breadcrumbs[index].find('a').get('href').strip() == link[1]
            else:
                assert breadcrumbs[index].text_content().strip() == link[0]
