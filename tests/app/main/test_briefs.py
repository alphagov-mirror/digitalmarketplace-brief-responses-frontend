# -*- coding: utf-8 -*-
from __future__ import unicode_literals

import mock
import pytest
from lxml import html

from dmapiclient import HTTPError
from dmapiclient.audit import AuditTypes
from dmtestutils.api_model_stubs import BriefStub, FrameworkStub, LotStub
from dmutils.email.exceptions import EmailError

from app.main.views.briefs import _render_not_eligible_for_brief_error_page, PUBLISHED_BRIEF_STATUSES

from ..helpers import BaseApplicationTest


brief_form_submission = {
    "availability": "Next Tuesday",
    "dayRate": "£200",
    "essentialRequirements-0": True,
    "essentialRequirements-1": False,
    "essentialRequirements-2": True,
    "niceToHaveRequirements-0": False,
    "niceToHaveRequirements-1": True,
    "niceToHaveRequirements-2": False,
}

processed_brief_submission = {
    "availability": "Next Tuesday",
    "dayRate": "£200",
    "essentialRequirements": [
        True,
        False,
        True
    ],
    "niceToHaveRequirements": [
        False,
        True,
        False
    ],
}

ERROR_MESSAGE_PAGE_HEADING_CLARIFICATION = 'You can’t ask a question about this opportunity'
ERROR_MESSAGE_NO_SERVICE_ON_LOT_CLARIFICATION = \
    'You can’t ask a question about this opportunity because you didn’t say you'\
    ' could provide services in this category when you applied to the Digital Outcomes and Specialists framework.'
ERROR_MESSAGE_NO_SERVICE_ON_FRAMEWORK_CLARIFICATION = \
    'You can’t ask a question about this opportunity because you’re not a Digital Outcomes and Specialists supplier.'
ERROR_MESSAGE_NO_SERVICE_WITH_ROLE_CLARIFICATION = \
    'You can’t ask a question about this opportunity because you didn’t say you'\
    ' could provide this specialist role when you applied to the Digital Outcomes and Specialists framework.'

NON_LIVE_BRIEF_STATUSES = [i for i in PUBLISHED_BRIEF_STATUSES if i != 'live']


class Table(object):
    def __init__(self, doc, table_name):
        self._data = []
        self._row_index = None
        query = doc.xpath(
            ''.join([
                '//h2[contains(normalize-space(text()), "{}")]',
                '/following-sibling::table[1]/tbody/tr'
            ]).format(table_name)
        )
        if len(query):
            for row_element in query:
                self._data.append(
                    [
                        element.find('span').text if element.find('span') is not None
                        else '' for element in row_element.findall('td')]
                )

    def exists(self):
        return len(self._data) > 0

    def row(self, idx):
        self._row_index = idx
        return self

    def cell(self, idx):
        if self._row_index is None:
            raise KeyError("no row selected")
        else:
            try:
                return self._data[self._row_index][idx]
            except IndexError as e:
                raise IndexError("{}. Contents of table: {}".format(e, self._data))


class TestBriefQuestionAndAnswerSession(BaseApplicationTest):

    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_q_and_a_session_details_requires_login(self):
        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 302
        assert '/login' in res.headers['Location']
        self.assert_no_flashes()

    def test_q_and_a_session_details_shows_flash_error_message_if_user_is_not_a_supplier(self):
        self.login_as_buyer()
        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 302
        assert '/login' in res.headers['Location']

        self.assert_flashes('You must log in with a supplier account to see this page', expected_category='error')

    def test_q_and_a_session_details(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()
        self.data_api_client.get_brief.return_value['briefs']['questionAndAnswerSessionDetails'] = 'SESSION DETAILS'

        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 200
        assert 'SESSION DETAILS' in res.get_data(as_text=True)

    def test_q_and_a_session_details_checks_supplier_is_eligible(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', lot_slug='digital-specialists'
        ).single_result_response()
        self.data_api_client.get_brief.return_value['briefs']['frameworkName'] = 'Digital Outcomes and Specialists'
        self.data_api_client.is_supplier_eligible_for_brief.return_value = False

        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 403

    def test_q_and_a_session_details_requires_existing_brief_id(self):
        self.login()
        self.data_api_client.get_brief.side_effect = HTTPError(mock.Mock(status_code=404))

        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 404

    @pytest.mark.parametrize('status', NON_LIVE_BRIEF_STATUSES)
    def test_q_and_a_session_details_requires_live_brief(self, status):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status=status).single_result_response()

        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 404

    def test_q_and_a_session_details_requires_questions_to_be_open(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', clarification_questions_closed=True
        ).single_result_response()

        res = self.client.get('/suppliers/opportunities/1/question-and-answer-session')
        assert res.status_code == 404


class TestBriefClarificationQuestions(BaseApplicationTest):

    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_clarification_question_form_requires_login(self):
        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 302
        assert '/login' in res.headers['Location']

    def test_clarification_question_form(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 200

    def test_clarification_question_form_escapes_brief_name(self):
        self.login()
        xss_brief = BriefStub(status='live').single_result_response()
        xss_brief['briefs']['title'] = '<script>alert(1)</script>'
        self.data_api_client.get_brief.return_value = xss_brief

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        html_string = res.get_data(as_text=True)
        doc = html.fromstring(html_string)

        assert '<script>alert(1)</script>' not in html_string
        assert '<script>alert(1)</script>' in doc.xpath('//h1/text()')[0].strip()

    def test_clarification_question_form_requires_existing_brief_id(self):
        self.login()
        self.data_api_client.get_brief.side_effect = HTTPError(mock.Mock(status_code=404))

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 404

    def test_clarification_question_checks_supplier_is_eligible(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', lot_slug='digital-specialists'
        ).single_result_response()
        self.data_api_client.get_brief.return_value['briefs']['frameworkName'] = 'Digital Outcomes and Specialists'
        self.data_api_client.is_supplier_eligible_for_brief.return_value = False

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 403

    @pytest.mark.parametrize('status', NON_LIVE_BRIEF_STATUSES)
    def test_clarification_question_form_requires_live_brief(self, status):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status=status).single_result_response()

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 404

    def test_clarification_question_form_requires_questions_to_be_open(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', clarification_questions_closed=True
        ).single_result_response()

        res = self.client.get('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 404

    def test_clarification_question_advice_shows_date_when_answers_will_be_published_by(self):
        self.login()
        brief = BriefStub(status="live").single_result_response()
        brief['briefs']['frameworkName'] = 'Brief Framework Name'
        brief['briefs']['clarificationQuestionsPublishedBy'] = '2016-03-29T10:11:13.000000Z'
        self.data_api_client.get_brief.return_value = brief

        res = self.client.post('/suppliers/opportunities/1/ask-a-question')
        xpath = html.fromstring(res.get_data(as_text=True)).xpath
        advice = xpath("//*[@class='question-advice']/text()")[0]

        assert "Tuesday 29 March 2016" in advice

    def test_clarification_question_advice_includes_link_to_gov_uk_guidance(self):
        self.login()
        brief = BriefStub(status="live").single_result_response()
        brief['briefs']['frameworkName'] = 'Brief Framework Name'
        brief['briefs']['clarificationQuestionsPublishedBy'] = '2016-03-29T10:11:13.000000Z'
        self.data_api_client.get_brief.return_value = brief

        res = self.client.post('/suppliers/opportunities/1/ask-a-question')
        xpath = html.fromstring(res.get_data(as_text=True)).xpath

        guidance_url = xpath("//*[@class='question-advice']//a/@href")[0]

        assert guidance_url.startswith("https://www.gov.uk/guidance")


class TestSubmitClarificationQuestions(BaseApplicationTest):

    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()

        self.notify_client_patch = mock.patch('app.main.helpers.briefs.DMNotifyClient', autospec=True)
        self.notify_client = self.notify_client_patch.start()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        self.notify_client_patch.stop()
        super().teardown_method(method)

    def test_submit_clarification_question_requires_login(self):
        res = self.client.post('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 302
        assert '/login' in res.headers['Location']

    def test_submit_clarification_question(self):
        self.login()
        brief = BriefStub(status="live").single_result_response()
        brief['briefs']['frameworkName'] = 'Brief Framework Name'
        brief['briefs']['clarificationQuestionsPublishedBy'] = '2016-03-29T10:11:13.000000Z'
        self.data_api_client.get_brief.return_value = brief

        with self.app.app_context():
            res = self.client.post('/suppliers/opportunities/1234/ask-a-question', data={
                'clarification_question': "important question",
            })
            assert res.status_code == 200

            # Can't use self.assert_flashes() here as the view does not redirect
            # - rendering the template removes the '_flashes' key from the session.
            doc = html.fromstring(res.get_data(as_text=True))
            assert len(doc.xpath(
                '//*[contains(normalize-space(text()), normalize-space("{}"))]'.format(
                    "Your question has been sent. "
                    "The buyer will post your question and their answer on the ‘I need a thing to do a thing’ page."
                )
            )) == 1
            assert doc.xpath("//div[@data-analytics='trackPageView']/@data-url")[0] == \
                '/suppliers/opportunities/1234/ask-a-question?submitted=true'

            assert self.notify_client.return_value.send_email.call_args_list == [
                mock.call(
                    'buyer@email.com',
                    template_name_or_id=self.app.config['NOTIFY_TEMPLATES']['clarification_question'],
                    personalisation={
                        'brief_title': 'I need a thing to do a thing',
                        'brief_name': 'I need a thing to do a thing',
                        'message': 'important question',
                        'publish_by_date': 'Tuesday 29 March 2016',
                        'questions_url': 'http://localhost/buyers/frameworks/digital-outcomes-and-specialists/requirements/digital-specialists/1234/supplier-questions' # noqa
                    },
                    reference=mock.ANY
                ),
                mock.call(
                    'email@email.com',
                    template_name_or_id=self.app.config['NOTIFY_TEMPLATES']['clarification_question_confirmation'],
                    personalisation={
                        'brief_name': 'I need a thing to do a thing',
                        'message': 'important question',
                        'brief_url': 'http://localhost/digital-outcomes-and-specialists/opportunities/1234'
                    },
                    reference=mock.ANY
                ),
            ]

            self.data_api_client.create_audit_event.assert_called_with(
                audit_type=AuditTypes.send_clarification_question,
                object_type='briefs',
                data={'briefId': 1234, 'question': u'important question', 'supplierId': 1234},
                user='email@email.com',
                object_id=1234
            )

    def test_submit_clarification_question_fails_on_notify_error(self):
        self.login()
        brief = BriefStub(status="live").single_result_response()
        brief['briefs']['frameworkName'] = 'Framework Name'
        brief['briefs']['clarificationQuestionsPublishedBy'] = '2016-03-29T10:11:13.000000Z'
        self.data_api_client.get_brief.return_value = brief

        self.notify_client.return_value.send_email.side_effect = EmailError

        res = self.client.post('/suppliers/opportunities/1234/ask-a-question', data={
            'clarification_question': "important question",
        })
        assert res.status_code == 503

    def test_submit_clarification_question_requires_existing_brief_id(self):
        self.login()
        self.data_api_client.get_brief.side_effect = HTTPError(mock.Mock(status_code=404))

        res = self.client.post('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 404

        assert self.notify_client.return_value.send_email.called is False

    @pytest.mark.parametrize('status', NON_LIVE_BRIEF_STATUSES)
    def test_submit_clarification_question_requires_live_brief(self, status):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status=status).single_result_response()

        res = self.client.post('/suppliers/opportunities/1/ask-a-question')
        assert res.status_code == 404

        assert self.notify_client.return_value.send_email.called is False

    def test_submit_clarification_question_returns_error_page_if_supplier_has_no_services_on_lot(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', lot_slug='digital-specialists'
        ).single_result_response()
        self.data_api_client.get_brief.return_value['briefs']['frameworkName'] = 'Digital Outcomes and Specialists'
        self.data_api_client.is_supplier_eligible_for_brief.return_value = False
        self.data_api_client.find_services.side_effect = lambda *args, **kwargs: (
            {"services": [{"something": "nonempty"}]} if kwargs.get("lot") is None else {"services": []}
        )

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "important question",
        })
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 403
        assert doc.xpath('normalize-space(//h1/text())') == ERROR_MESSAGE_PAGE_HEADING_CLARIFICATION
        assert len(doc.xpath(
            '//*[contains(normalize-space(text()), normalize-space("{}"))]'.format(
                ERROR_MESSAGE_NO_SERVICE_ON_LOT_CLARIFICATION
            )
        )) == 1
        assert self.data_api_client.create_audit_event.called is False
        assert self.notify_client.return_value.send_email.called is False

    def test_submit_clarification_question_returns_error_page_if_supplier_has_no_services_on_framework(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', lot_slug='digital-specialists'
        ).single_result_response()
        self.data_api_client.is_supplier_eligible_for_brief.return_value = False
        self.data_api_client.find_services.return_value = {"services": []}

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "important question",
        })
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 403
        assert doc.xpath('normalize-space(//h1/text())') == ERROR_MESSAGE_PAGE_HEADING_CLARIFICATION
        assert len(doc.xpath(
            '//*[contains(normalize-space(text()), normalize-space("{}"))]'.format(
                ERROR_MESSAGE_NO_SERVICE_ON_FRAMEWORK_CLARIFICATION
            )
        )) == 1
        assert self.data_api_client.create_audit_event.called is False
        assert self.notify_client.return_value.send_email.called is False

    def test_submit_clarification_question_returns_error_page_if_supplier_has_no_services_with_role(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(
            status='live', lot_slug='digital-specialists'
        ).single_result_response()
        self.data_api_client.get_brief.return_value['briefs']['frameworkName'] = 'Digital Outcomes and Specialists'
        self.data_api_client.is_supplier_eligible_for_brief.return_value = False
        self.data_api_client.find_services.return_value = {"services": [{"something": "nonempty"}]}

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "important question",
        })
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 403
        assert doc.xpath('normalize-space(//h1/text())') == ERROR_MESSAGE_PAGE_HEADING_CLARIFICATION
        assert len(doc.xpath(
            '//*[contains(normalize-space(text()), normalize-space("{}"))]'.format(
                ERROR_MESSAGE_NO_SERVICE_WITH_ROLE_CLARIFICATION
            )
        )) == 1
        assert self.data_api_client.create_audit_event.called is False
        assert self.notify_client.return_value.send_email.called is False

    def test_submit_empty_clarification_question_returns_validation_error(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "",
        })
        assert res.status_code == 400
        assert "cannot be empty" in res.get_data(as_text=True)
        assert self.notify_client.return_value.send_email.called is False

    def test_clarification_question_has_max_length_limit(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "a" * 5100,
        })
        assert res.status_code == 400
        assert "cannot be longer than" in res.get_data(as_text=True)
        assert self.notify_client.return_value.send_email.called is False

    def test_clarification_question_has_max_word_limit(self):
        self.login()
        self.data_api_client.get_brief.return_value = BriefStub(status='live').single_result_response()

        res = self.client.post('/suppliers/opportunities/1/ask-a-question', data={
            'clarification_question': "a " * 101,
        })
        assert res.status_code == 400
        assert "must be no more than 100 words" in res.get_data(as_text=True)
        assert self.notify_client.return_value.send_email.called is False

    def test_submit_clarification_question_escapes_html(self):
        self.login()
        brief = BriefStub(status="live").single_result_response()
        self.data_api_client.get_brief.return_value = brief
        brief['briefs']['frameworkName'] = 'Brief Framework Name'
        brief['briefs']['clarificationQuestionsPublishedBy'] = '2016-03-29T10:11:13.000000Z'

        res = self.client.post('/suppliers/opportunities/1234/ask-a-question', data={
            'clarification_question': '<a href="malicious">friendly.url</a>',
        })
        assert res.status_code == 200

        escaped_string = '&lt;a href=&#34;malicious&#34;&gt;friendly.url&lt;/a&gt;'
        assert escaped_string in \
            self.notify_client.return_value.send_email.mock_calls[0][2]['personalisation']['message']
        assert escaped_string in \
            self.notify_client.return_value.send_email.mock_calls[1][2]['personalisation']['message']


class TestApplyToBrief(BaseApplicationTest):
    """Tests requests for the multipage flow for applying for a brief"""

    def setup_method(self, method):
        super().setup_method(method)

        self.brief = BriefStub(status='live', lot_slug='digital-specialists').single_result_response()
        self.brief['briefs']['essentialRequirements'] = ['Essential one', 'Essential two', 'Essential three']
        self.brief['briefs']['niceToHaveRequirements'] = ['Nice one', 'Top one', 'Get sorted']

        lots = [
            LotStub(slug="digital-specialists", allows_brief=True).response(),
            LotStub(slug="digital-outcomes", allows_brief=True).response(),
            LotStub(slug="user-research-participants", allows_brief=True).response()
        ]
        self.framework = FrameworkStub(
            status="live", slug="digital-outcomes-and-specialists", clarification_questions_open=False, lots=lots
        ).single_result_response()

        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client')
        self.data_api_client = self.data_api_client_patch.start()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_framework.return_value = self.framework
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.submit_brief_response.return_value = self.brief_response(data={'status': 'submitted'})

        self.login()

    def teardown_method(self, method):
        super().teardown_method(method)
        self.data_api_client_patch.stop()

    @mock.patch("app.main.views.briefs.content_loader")
    def test_will_redirect_from_generic_brief_response_url_to_first_question(self, content_loader):
        content_loader.get_manifest.return_value \
            .filter.return_value \
            .get_section.return_value \
            .get_next_question_id.return_value = 'first'

        res = self.client.get('/suppliers/opportunities/1234/responses/5')
        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/first'

    def test_can_get_question_page_for_live_and_expired_framework(self):
        for framework_status in ['live', 'expired']:
            framework = self.framework.copy()
            framework.update({'status': framework_status})
            self.data_api_client.get_framework.return_value = framework

            res = self.client.get('/suppliers/opportunities/1234/responses/5/respondToEmailAddress')

            assert res.status_code == 200

    def test_can_post_question_page_for_live_and_expired_framework(self):
        for framework_status in ['live', 'expired']:
            framework = self.framework.copy()
            framework.update({'status': framework_status})
            self.data_api_client.get_framework.return_value = framework

            res = self.client.post('/suppliers/opportunities/1234/responses/5/respondToEmailAddress')

            assert res.status_code == 302
            assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application'

    def test_can_get_question_page_when_editing_for_live_and_expired_framework(self):
        self.data_api_client.find_brief_responses.return_value = {"briefResponses": [{"yay": "hey"}]}
        for framework_status in ['live', 'expired']:
            framework = self.framework.copy()
            framework.update({'status': framework_status})
            self.data_api_client.get_framework.return_value = framework

            res = self.client.get('/suppliers/opportunities/1234/responses/5/respondToEmailAddress/edit')

            assert res.status_code == 200

    def test_can_post_question_page_when_editing_for_live_and_expired_framework(self):
        self.data_api_client.find_brief_responses.return_value = {"briefResponses": [{"yay": "hey"}]}
        for framework_status in ['live', 'expired']:
            framework = self.framework.copy()
            framework.update({'status': framework_status})
            self.data_api_client.get_framework.return_value = framework

            res = self.client.post('/suppliers/opportunities/1234/responses/5/respondToEmailAddress/edit')

            assert res.status_code == 302
            assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application'

    def test_404_if_brief_response_does_not_exist(self):
        for method in ('get', 'post'):
            self.data_api_client.get_brief_response = mock.MagicMock(side_effect=HTTPError(mock.Mock(status_code=404)))

            res = self.client.open('/suppliers/opportunities/1234/responses/250/question-id', method=method)

            assert res.status_code == 404
            self.data_api_client.get_brief_response.assert_called_once_with(250)

    def test_404_if_brief_response_does_not_relate_to_brief(self):
        for method in ('get', 'post'):
            self.data_api_client.get_brief_response.return_value = {
                "briefResponses": {
                    "briefId": 234,
                    "supplierId": 1234
                }
            }

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    @mock.patch("app.main.views.briefs.current_user")
    def test_404_if_brief_response_does_not_relate_to_current_user(self, current_user):
        for method in ('get', 'post'):
            current_user.supplier_id = 789

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    @pytest.mark.parametrize('status', NON_LIVE_BRIEF_STATUSES)
    def test_404_for_not_live_brief(self, status):
        for method in ('get', 'post'):
            self.data_api_client.get_brief.return_value = BriefStub(
                status=status, lot_slug='digital-specialists'
            ).single_result_response()

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    def test_404_for_not_live_or_expired_framework(self):
        for framework_status in ['coming', 'open', 'pending', 'standstill']:
            for method in ('get', 'post'):
                framework = self.framework.copy()
                framework.update({'status': framework_status})
                self.data_api_client.get_framework.return_value = framework
                res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
                assert res.status_code == 404

    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    @mock.patch("app.main.views.briefs._render_not_eligible_for_brief_error_page", autospec=True)
    def test_show_not_eligible_page_if_supplier_not_eligible_to_apply_for_brief(
        self, _render_not_eligible_for_brief_error_page, is_supplier_eligible_for_brief
    ):
        is_supplier_eligible_for_brief.return_value = False
        _render_not_eligible_for_brief_error_page.return_value = 'dummy response', 403

        for method in ('get', 'post'):
            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 403
            _render_not_eligible_for_brief_error_page.assert_called_with(self.brief['briefs'])

    @mock.patch("app.main.views.briefs.content_loader")
    def test_should_404_for_non_existent_content_section(self, content_loader):
        for method in ('get', 'post'):
            content_loader.get_manifest.return_value.filter.return_value.get_section.return_value = None

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    @mock.patch("app.main.views.briefs.content_loader")
    def test_should_404_for_non_editable_content_section(self, content_loader):
        for method in ('get', 'post'):
            content_loader.get_manifest.return_value.filter.return_value.get_section.return_value.editable = False

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    @mock.patch("app.main.views.briefs.content_loader")
    def test_should_404_for_non_existent_question(self, content_loader):
        for method in ('get', 'post'):
            content_loader.get_manifest.return_value \
                .filter.return_value \
                .get_section.return_value \
                .get_question.return_value = None

            res = self.client.open('/suppliers/opportunities/1234/responses/5/question-id', method=method)
            assert res.status_code == 404

    @pytest.mark.parametrize(
        'section_name', ['dayRate', 'essentialRequirements', 'niceToHaveRequirements', 'respondToEmailAddress']
    )
    def test_all_questions_show_save_and_continue_button(self, section_name):
        res = self.client.get('/suppliers/opportunities/1234/responses/5/{}'.format(section_name))
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//button")[0].text.strip() == 'Save and continue'

    def test_first_question_does_not_show_previous_page_link(self):
        self.brief['briefs']['startDate'] = 'start date'
        res = self.client.get('/suppliers/opportunities/1234/responses/5/availability')
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert len(doc.xpath("//a[text()='Back to previous page']")) == 0

    def test_non_first_question_shows_previous_page_link(self):
        res = self.client.get('/suppliers/opportunities/1234/responses/5/dayRate')
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert (doc.xpath("//a[text()='Back to previous page']/@href")[0] ==
                '/suppliers/opportunities/1234/responses/5/availability')

    def test_respond_to_email_previous_page_link_skips_nice_to_have_requirements_if_no_nice_to_haves_for_brief(self):
        self.brief['briefs']['niceToHaveRequirements'] = []
        self.data_api_client.get_brief.return_value = self.brief

        res = self.client.get('/suppliers/opportunities/1234/responses/5/respondToEmailAddress')
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert (doc.xpath("//a[text()='Back to previous page']/@href")[0] ==
                '/suppliers/opportunities/1234/responses/5/essentialRequirements')

    def test_content_from_manifest_is_shown(self):
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/respondToEmailAddress'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//h1/text()")[0].strip() == 'Email address the buyer should use to contact you'
        assert (doc.xpath("//span[@class=\"question-heading\"]/text()")[0].strip() ==
                'Email address the buyer should use to contact you')
        assert (doc.xpath("//span[@class=\"question-advice\"]/text()")[0].strip() ==
                'All communication about your application will be sent to this address.')

    def test_essential_requirements_met_question_replays_all_brief_requirements(self):
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/essentialRequirementsMet'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        list_items = doc.xpath("//*[@id='input-essentialRequirementsMet-question-advice']/ul/li/text()")
        assert len(self.brief['briefs']['essentialRequirements']) == len(list_items)
        for index, requirement in enumerate(self.brief['briefs']['essentialRequirements']):
            assert requirement == list_items[index]

    def test_essential_requirements_met_question_escapes_brief_data(self):
        self.brief['briefs']['essentialRequirements'] = [
            '<h1>Essential one with xss</h1>',
            '**Essential two with markdown**'
        ]
        self.data_api_client.get_brief.return_value = self.brief

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/essentialRequirementsMet'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        list_items = doc.xpath("//*[@id='input-essentialRequirementsMet-question-advice']/ul/li")
        # if item is excaped correctly it will appear as text rather than an element
        assert list_items[0].find("h1") is None
        assert list_items[0].text == '<h1>Essential one with xss</h1>'
        assert list_items[1].find("strong") is None
        assert list_items[1].text == '**Essential two with markdown**'

    def test_day_rate_question_replays_buyers_budget_range_and_suppliers_max_day_rate(self):
        self.brief['briefs']['budgetRange'] = '1 million dollars'
        self.brief['briefs']['specialistRole'] = 'deliveryManager'
        self.data_api_client.find_services.return_value = {"services": [{"deliveryManagerPriceMax": 600}]}

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/dayRate'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        day_rate_headings = doc.xpath("//*[@id='input-dayRate-question-advice']/h2/text()")
        buyers_max_day_rate = doc.xpath(
            "//*[@id='input-dayRate-question-advice']/descendant::h2[1]/following::p[1]/text()")[0]
        suppliers_max_day_rate = doc.xpath(
            "//*[@id='input-dayRate-question-advice']/descendant::h2[2]/following::p[1]/text()")[0]

        assert day_rate_headings[0] == "Buyer's maximum day rate:"
        assert buyers_max_day_rate == '1 million dollars'
        assert day_rate_headings[1] == "Your maximum day rate:"
        assert suppliers_max_day_rate == '£600'

    def test_day_rate_question_escapes_brief_day_rate_markdown(self):
        self.brief['briefs']['budgetRange'] = '**markdown**'

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/dayRate'
        )
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert '**markdown**' in data

    def test_day_rate_question_escapes_brief_day_rate_html(self):
        self.brief['briefs']['budgetRange'] = '<h1>xss</h1>'

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/dayRate'
        )
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert '&lt;h1&gt;xss&lt;/h1&gt;' in data

    def test_day_rate_question_does_not_replay_buyers_budget_range_if_not_provided(self):
        self.brief['briefs']['specialistRole'] = 'deliveryManager'
        self.data_api_client.find_services.return_value = {"services": [{"deliveryManagerPriceMax": 600}]}

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/dayRate'
        )
        assert res.status_code == 200
        data = res.get_data(as_text=True)
        assert "Buyer's maximum day rate:" not in data

    def test_availability_question_shows_correct_content_for_lot(self):
        self.brief['briefs']['startDate'] = '17/01/2017'
        self.brief['briefs']['researchDates'] = '17/01/2017'
        lot_slugs = ['digital-specialists', 'digital-outcomes', 'user-research-participants']
        question_content = ['the specialist can start work?', 'the team can start?', 'you can recruit participants?']
        hint_content = ['the specialist to start:', 'the team to start:', 'participants:']

        for lot_slug, question, hint in zip(lot_slugs, question_content, hint_content):
            self.brief['briefs']['lotSlug'] = lot_slug

            res = self.client.get(
                '/suppliers/opportunities/1234/responses/5/availability'
            )
            assert res.status_code == 200

            doc = html.fromstring(res.get_data(as_text=True))
            page_heading = doc.xpath("//h1/text()")
            page_hint = doc.xpath("//span[@id='input-availability-question-advice']/p/text()")

            assert len(page_heading) == 1
            assert page_heading[0].strip() == 'When is the earliest {}'.format(question)
            assert len(page_hint) == 1
            assert page_hint[0] == 'The buyer needs {} 17/01/2017'.format(hint)

    @pytest.mark.parametrize(
        ('date_string', 'expected'),
        (('2017-04-25', 'Tuesday 25 April 2017'), ('foo', 'foo'))
    )
    def test_availability_question_renders_date_or_falls_back_to_string(self, date_string, expected):
        self.brief['briefs']['frameworkName'] = "Digital Outcomes and Specialists 2"
        self.brief['briefs']['frameworkSlug'] = "digital-outcomes-and-specialists-2"
        self.brief['briefs']['startDate'] = date_string
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/availability'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        page_hint = doc.xpath("//span[@id='input-availability-question-advice']/p/text()")
        assert page_hint[0] == 'The buyer needs the specialist to start: {}'.format(expected)

    def test_availability_question_escapes_brief_start_date_markdown(self):
        self.brief['briefs']['startDate'] = '**markdown**'

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/availability'
        )
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert "The buyer needs the specialist to start: **markdown**" in data

    def test_availability_question_escapes_brief_start_date_html(self):
        self.brief['briefs']['startDate'] = '<h1>xss</h1>'
        self.brief['briefs']['lot'] = 'digital-specialists'

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/availability'
        )
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert "The buyer needs the specialist to start: &lt;h1&gt;xss&lt;/h1&gt;" in data

    def test_essential_requirements_evidence_has_question_for_every_requirement(self):
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements'
        )
        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        questions = doc.xpath(
            "//*[@class='question-heading']/text()")
        questions = list(map(str.strip, questions))
        assert questions == ['Essential one', 'Essential two', 'Essential three']

    def test_essential_and_nice_to_have_requirements_evidence_escapes_brief_data(self):
        for question_slug in ('essentialRequirements', 'niceToHaveRequirements'):
            self.brief['briefs'][question_slug] = [
                '<h1>requirement with xss</h1>',
                '**requirement with markdown**'
            ]
            self.data_api_client.get_brief.return_value = self.brief

            res = self.client.get(
                '/suppliers/opportunities/1234/responses/5/{}'.format(question_slug)
            )
            assert res.status_code == 200

            data = res.get_data(as_text=True)

            assert '&lt;h1&gt;requirement with xss&lt;/h1&gt;' in data
            assert '**requirement with markdown**' in data

    def test_specialist_brief_essential_and_nice_to_have_requirements_evidence_shows_specialist_content(self):
        for question_slug in ('essentialRequirements', 'niceToHaveRequirements'):
            res = self.client.get(
                '/suppliers/opportunities/1234/responses/5/{}'.format(question_slug)
            )
            assert res.status_code == 200
            data = res.get_data(as_text=True)

            assert "the work the specialist did" in data
            assert "the work the team did" not in data

    def test_outcomes_brief_essential_and_nice_to_have_requirements_evidence_shows_outcomes_content(self):
        self.brief['briefs']['lotSlug'] = 'digital-outcomes'
        self.data_api_client.get_brief.return_value = self.brief

        for question_slug in ('essentialRequirements', 'niceToHaveRequirements'):
            res = self.client.get(
                '/suppliers/opportunities/1234/responses/5/{}'.format(question_slug)
            )
            assert res.status_code == 200
            data = res.get_data(as_text=True)

            assert "the work the team did" in data
            assert "the work the specialist did" not in data

    def test_existing_essential_requirements_evidence_prefills_existing_data(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'essentialRequirements': [
                    {'evidence': 'evidence0'}, {'evidence': 'evidence1'}, {'evidence': 'evidence2'}
                ]
            }
        )

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements'
        )
        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        for i in range(3):
            assert doc.xpath("//*[@id='input-evidence-" + str(i) + "']/text()")[0] == 'evidence' + str(i)

    def test_submit_essential_requirements_evidence(self):
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements',
            data={
                "evidence-0": 'first evidence',
                "evidence-1": 'second evidence',
                "evidence-2": 'third evidence'
            }
        )

        assert res.status_code == 302

        self.data_api_client.update_brief_response.assert_called_once_with(
            5,
            {
                "essentialRequirements": [
                    {'evidence': 'first evidence'}, {'evidence': 'second evidence'}, {'evidence': 'third evidence'}
                ]
            },
            'email@email.com',
            page_questions=['essentialRequirements']
        )

    def test_essentials_evidence_page_shows_errors_messages_and_replays_user_input(self):
        self.data_api_client.update_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=400),
            {
                'essentialRequirements': [
                    {'field': 'evidence', 'index': 0, 'error': 'under_100_words'},
                    {'field': 'evidence', 'index': 2, 'error': 'answer_required'}
                ]
            }
        )

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements',
            data={
                "evidence-0": "over100characters" * 10,
                "evidence-1": "valid evidence",
                "evidence-2": ""
            }
        )

        assert res.status_code == 400
        doc = html.fromstring(res.get_data(as_text=True))

        # Test list of questions with errors at top of page
        assert (doc.xpath("//h2[@class=\"validation-masthead-heading\"]/text()")[0].strip() ==
                'There was a problem with your answer to:')
        assert (doc.xpath("//a[@class=\"validation-masthead-link\"]/text()")[0].strip() ==
                'Essential one')
        assert (doc.xpath("//a[@class=\"validation-masthead-link\"]/text()")[1].strip() ==
                'Essential three')

        # Test individual questions errors and prefilled content
        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[0].strip() ==
                'Your answer must be no more than 100 words.')
        assert doc.xpath("//*[@id='input-evidence-0']/text()")[0] == "over100characters" * 10

        assert doc.xpath("//*[@id='input-evidence-1']/text()")[0] == "valid evidence"

        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[1].strip() ==
                'You need to provide evidence.')
        assert not doc.xpath("//*[@id='input-evidence-2']/text()") is None

    def test_essential_evidence_page_replays_user_input_instead_of_existing_brief_response_data(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={'essentialRequirements': [{'evidence': 'nice valid evidence'}] * 3}
        )

        self.data_api_client.update_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=400),
            {
                'essentialRequirements': [
                    {'field': 'evidence', 'index': 0, 'error': 'under_100_words'}
                ]
            }
        )

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements',
            data={
                "evidence-0": "over100characters" * 10,
                "evidence-1": "valid evidence",
                "evidence-2": ""
            }
        )

        assert res.status_code == 400
        doc = html.fromstring(res.get_data(as_text=True))

        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[0].strip() ==
                'Your answer must be no more than 100 words.')
        assert doc.xpath("//*[@id='input-evidence-0']/text()")[0] == "over100characters" * 10
        assert doc.xpath("//*[@id='input-evidence-1']/text()")[0] == "valid evidence"
        assert not doc.xpath("//*[@id='input-evidence-2']/text()")

    def test_essential_requirements_evidence_does_not_redirect_to_nice_to_haves_if_brief_has_no_nice_to_haves(self):
        self.brief['briefs']['niceToHaveRequirements'] = []
        self.data_api_client.get_brief.return_value = self.brief

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/essentialRequirements',
            data={
                "evidence-0": "valid evidence",
                "evidence-1": "valid evidence",
                "evidence-2": "valid evidence"
            }
        )

        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/respondToEmailAddress'  # noqa

    def test_nice_to_have_requirements_url_404s_if_no_nice_to_have_requirements(self):
        self.brief['briefs']['niceToHaveRequirements'] = []
        self.data_api_client.get_brief.return_value = self.brief

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements'
        )
        assert res.status_code == 404

    def test_nice_to_have_requirements_evidence_has_question_for_every_requirement(self):
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements'
        )
        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        questions = doc.xpath(
            "//*[@class='question-heading']/text()")
        questions = list(map(str.strip, questions))

        assert questions == [
            'Nice one', 'Evidence of Nice one', 'Top one', 'Evidence of Top one', 'Get sorted', 'Evidence of Get sorted'
        ]

    def test_existing_nice_to_have_requirements_evidence_prefills_existing_data(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'niceToHaveRequirements': [
                    {'yesNo': True, 'evidence': 'evidence0'}, {'yesNo': False}, {'yesNo': True, 'evidence': 'evidence2'}
                ]
            }
        )

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements'
        )
        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))

        # Check yesno radio buttons
        for i in (0, 2):
            assert len(doc.xpath("//*[@id='input-yesNo-" + str(i) + "-1' and @checked]")) == 1
        assert len(doc.xpath("//*[@id='input-yesNo-1-2' and @checked]")) == 1

        # Check evidence text
        for i in (0, 2):
            assert doc.xpath("//*[@id='input-evidence-" + str(i) + "']/text()")[0] == 'evidence' + str(i)

    def test_submit_nice_to_have_requirements_evidence(self):
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements',
            data={
                "yesNo-0": True,
                "evidence-0": 'first evidence',
                "yesNo-1": False,
                "evidence-1": "",
                "yesNo-2": False,
                "evidence-2": 'evidence we expect not to be sent'
            }
        )

        assert res.status_code == 302

        self.data_api_client.update_brief_response.assert_called_once_with(
            5,
            {
                "niceToHaveRequirements": [
                    {'yesNo': True, 'evidence': 'first evidence'},
                    {'yesNo': False},
                    {'yesNo': False}
                ]
            },
            'email@email.com',
            page_questions=['niceToHaveRequirements']
        )

    def test_nice_to_have_evidence_page_shows_errors_messages_and_replays_user_input(self):
        self.data_api_client.update_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=400),
            {
                'niceToHaveRequirements': [
                    {'field': 'yesNo', 'index': 0, 'error': 'answer_required'},
                    {'field': 'evidence', 'index': 1, 'error': 'answer_required'},
                    {'field': 'evidence', 'index': 2, 'error': 'under_100_words'}
                ]
            }
        )

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements',
            data={
                "evidence-0": "",
                "yesNo-1": True,
                "evidence-1": "",
                "yesNo-2": True,
                "evidence-2": "word " * 100
            }
        )

        assert res.status_code == 400
        doc = html.fromstring(res.get_data(as_text=True))

        # Test list of questions with errors at top of page
        assert (doc.xpath("//h2[@class=\"validation-masthead-heading\"]/text()")[0].strip() ==
                'There was a problem with your answer to:')
        masthead_errors = doc.xpath("//a[@class=\"validation-masthead-link\"]/text()")
        masthead_errors = list(map(str.strip, masthead_errors))
        assert masthead_errors == ['Nice one', 'Evidence of Top one', 'Evidence of Get sorted']

        # Test individual questions errors and prefilled content
        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[0].strip() ==
                'You must answer ‘yes’ or ‘no’ to this question.')

        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[1].strip() ==
                'You must provide evidence if you answer ‘yes’ to this question.')
        assert len(doc.xpath("//*[@id='input-yesNo-1-1' and @checked]")) == 1

        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[2].strip() ==
                'Your answer must be no more than 100 words.')
        assert len(doc.xpath("//*[@id='input-yesNo-2-1' and @checked]")) == 1
        assert doc.xpath("//*[@id='input-evidence-2']/text()")[0] == 'word ' * 100

    def test_nice_to_have_evidence_page_replays_user_input_instead_of_existing_brief_response_data(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={'niceToHaveRequirements': [{'yesNo': True, 'evidence': 'nice valid evidence'}] * 3}
        )

        self.data_api_client.update_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=400),
            {
                'niceToHaveRequirements': [
                    {'field': 'evidence', 'index': 0, 'error': 'under_100_words'}
                ]
            }
        )

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements',
            data={
                "yesNo-0": True,
                "evidence-0": "over 100 words " * 100,
                "yesNo-1": False,
                "evidence-1": "",
                "yesNo-2": True,
                "evidence-2": ""
            }
        )

        assert res.status_code == 400
        doc = html.fromstring(res.get_data(as_text=True))

        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[0].strip() ==
                'Your answer must be no more than 100 words.')
        assert doc.xpath("//*[@id='input-evidence-0']/text()")[0] == "over 100 words " * 100

        assert len(doc.xpath("//*[@id='input-yesNo-1-2' and @checked]")) == 1
        assert not doc.xpath("//*[@id='input-evidence-1']/text()")

        assert not doc.xpath("//*[@id='input-evidence-2']/text()")

    def test_existing_brief_response_data_is_prefilled(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={'respondToEmailAddress': 'test@example.com'}
        )

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/respondToEmailAddress'
        )
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//input[@type='text']/@value")[0] == 'test@example.com'

    def test_error_message_shown_and_attempted_input_prefilled_if_invalid_input(self):
        self.data_api_client.update_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=400),
            {'respondToEmailAddress': 'invalid_format'}
        )

        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/respondToEmailAddress',
            data={
                "respondToEmailAddress": "not-a-valid-email"
            }
        )

        assert res.status_code == 400
        doc = html.fromstring(res.get_data(as_text=True))
        assert (doc.xpath("//h2[@class=\"validation-masthead-heading\"]/text()")[0].strip() ==
                'There was a problem with your answer to:')
        assert (doc.xpath("//a[@class=\"validation-masthead-link\"]/text()")[0].strip() ==
                'Email address')
        assert (doc.xpath("//span[@class=\"validation-message\"]/text()")[0].strip() ==
                'You must enter a valid email address.')
        assert doc.xpath('//*[@id="input-respondToEmailAddress"]/@value')[0] == "not-a-valid-email"

    def test_post_form_updates_api_and_redirects_to_next_section(self):
        data = {'dayRate': '500'}
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/dayRate',
            data=data
        )
        assert res.status_code == 302

        self.data_api_client.update_brief_response.assert_called_once_with(
            5,
            data,
            'email@email.com',
            page_questions=['dayRate']
        )

        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/essentialRequirementsMet'  # noqa

    def test_post_final_section_submits_response_redirects_to_check_your_answers_page(self):
        data = {'respondToEmailAddress': 'bob@example.com'}
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/respondToEmailAddress',
            data=data
        )
        assert res.status_code == 302

        self.data_api_client.update_brief_response.assert_called_once_with(
            5,
            data,
            'email@email.com',
            page_questions=['respondToEmailAddress']
        )

        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application'
        self.assert_no_flashes()

    def test_post_check_your_answers_page_submits_and_redirects_to_result_page(self):
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/application',
            data={}
        )
        assert res.status_code == 302

        self.data_api_client.submit_brief_response.assert_called_once_with(
            5,
            'email@email.com',
        )
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/result'
        self.assert_flashes("Your application has been submitted.")

    def test_editing_previously_completed_section_redirects_to_check_your_answers(self):
        data = {'dayRate': '600'}
        res = self.client.post(
            '/suppliers/opportunities/1234/responses/5/dayRate/edit',
            data=data
        )

        self.data_api_client.update_brief_response.assert_called_once_with(
            5,
            data,
            'email@email.com',
            page_questions=['dayRate']
        )
        assert res.status_code == 302
        assert res.location == "http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application"
        self.assert_flashes("Your application has been updated.")


class TestCheckYourAnswers(BaseApplicationTest):

    def setup_method(self, method):
        super().setup_method(method)

        self.brief = BriefStub(status='live', lot_slug='digital-specialists').single_result_response()
        self.brief['briefs']['essentialRequirements'] = ['Essential one', 'Essential two', 'Essential three']
        self.brief['briefs']['niceToHaveRequirements'] = ['Nice one', 'Top one', 'Get sorted']

        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client')
        self.data_api_client = self.data_api_client_patch.start()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_framework.return_value = FrameworkStub(
            status="live",
            slug="digital-outcomes-and-specialists-2",
            clarification_questions_open=False,
            lots=[LotStub(slug="digital-specialists", allows_brief=True).response()]
        ).single_result_response()
        self.data_api_client.get_brief_response.return_value = self.brief_response()

        self.login()

    def teardown_method(self, method):
        super().teardown_method(method)
        self.data_api_client_patch.stop()

    @pytest.mark.parametrize('brief_response_status', ['draft', 'submitted'])
    @pytest.mark.parametrize(
        'brief_status, edit_links_shown', [
            ('live', True),
            ('closed', False), ('awarded', False), ('unsuccessful', False), ('cancelled', False)
        ]
    )
    def test_check_your_answers_page_shows_edit_links_and_check_your_answers_title_for_live_briefs(
        self, brief_status, edit_links_shown, brief_response_status
    ):
        self.brief['briefs']['status'] = brief_status
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'status': brief_response_status,
                'essentialRequirementsMet': True,
            }
        )
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        doc = html.fromstring(res.get_data(as_text=True))
        edit_application_links = [anchor.get('href') for anchor in doc.xpath('//a') if 'Edit' in anchor.text_content()]
        if edit_links_shown:
            assert edit_application_links == [
                '/suppliers/opportunities/1234/responses/5/dayRate/edit',
                '/suppliers/opportunities/1234/responses/5/availability/edit',
                '/suppliers/opportunities/1234/responses/5/respondToEmailAddress/edit',
                '/suppliers/opportunities/1234/responses/5/essentialRequirements/edit',
                '/suppliers/opportunities/1234/responses/5/niceToHaveRequirements/edit',
            ]
        else:
            assert len(edit_application_links) == 0

        page_title = doc.xpath("//main//*//h1//text()")[0].strip()
        if brief_response_status == "draft":
            assert page_title == "Check and submit your answers"
        else:
            assert page_title == "Your application for ‘I need a thing to do a thing’"

    @pytest.mark.parametrize('brief_response_status', ['pending-awarded', 'awarded'])
    @pytest.mark.parametrize('brief_status', ['live', 'closed', 'awarded', 'unsuccessful', 'cancelled'])
    def test_check_your_answers_page_hides_edit_links_for_awarded_or_pending_awarded_brief_responses(
        self, brief_status, brief_response_status
    ):
        self.brief['briefs']['status'] = brief_status
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'status': brief_response_status,
                'essentialRequirementsMet': True,
            }
        )
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        doc = html.fromstring(res.get_data(as_text=True))
        edit_application_links = [anchor.get('href') for anchor in doc.xpath('//a') if anchor.text_content() == 'Edit']
        assert len(edit_application_links) == 0

    def test_check_your_answers_page_shows_essential_requirements(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'essentialRequirements': [
                    {'evidence': 'nice valid evidence'},
                    {'evidence': 'more valid evidence'},
                    {'evidence': 'yet further valid evidence'},
                ],
                'essentialRequirementsMet': True,
            }
        )

        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        doc = html.fromstring(res.get_data(as_text=True))

        requirements_data = Table(doc, "Your essential skills and experience")
        assert requirements_data.exists()
        assert requirements_data.row(0).cell(1) == "nice valid evidence"
        assert requirements_data.row(1).cell(1) == "more valid evidence"
        assert requirements_data.row(2).cell(1) == "yet further valid evidence"

    def test_check_your_answers_page_shows_nice_to_haves_when_they_exist(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'niceToHaveRequirements': [
                    {'yesNo': False},
                    {'yesNo': True, 'evidence': 'nice valid evidence'},
                    {'yesNo': True, 'evidence': 'nice valid evidence'}
                ],
                'essentialRequirementsMet': True,
            }
        )
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))

        requirements_data = Table(doc, "Your nice-to-have skills and experience")
        assert requirements_data.exists()
        assert requirements_data.row(0).cell(1) == ""
        assert requirements_data.row(1).cell(1) == "nice valid evidence"
        assert requirements_data.row(2).cell(1) == "nice valid evidence"

    def test_check_your_answers_page_hides_nice_to_have_heading_when_not_included_in_brief(self):
        self.brief['briefs']['niceToHaveRequirements'] = []
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        assert len(
            doc.xpath('//h2[contains(normalize-space(text()), "Your nice-to-have skills and experience")]')
        ) == 0

    def test_check_your_answers_page_escapes_essential_and_nice_to_have_requirements(self):
        self.brief['briefs']['essentialRequirements'] = [
            '<h1>Essential one with xss</h1>',
            '**Essential two with markdown**'
        ]
        self.brief['briefs']['niceToHaveRequirements'] = [
            '<h1>n2h one with xss</h1>',
            '**n2h two with markdown**'
        ]
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'niceToHaveRequirements': [
                    {
                        'yesNo': True,
                        'evidence': 'Did a thing'
                    },
                    {
                        'yesNo': False
                    },
                ],
                'essentialRequirementsMet': True,
            }
        )
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        data = res.get_data(as_text=True)
        doc = html.fromstring(data)

        assert "&lt;h1&gt;Essential one with xss&lt;/h1&gt;" in data
        assert "&lt;h1&gt;n2h one with xss&lt;/h1&gt;" in data
        assert len(doc.xpath('//h1')) == 1

        assert "**Essential two with markdown**" in data
        assert "<strong>Essential two with markdown</strong>" not in data
        assert "**n2h two with markdown**" in data
        assert "<strong>n2h two with markdown</strong>" not in data

    def test_check_your_answers_page_shows_supplier_details(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'dayRate': "300",
                'availability': '02/02/2017',
                'respondToEmailAddress': "contact@big.com",
                'essentialRequirementsMet': True,
            }
        )

        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))

        requirements_data = Table(doc, "Your details")
        assert requirements_data.exists()
        assert requirements_data.row(0).cell(0) == "Day rate"
        assert requirements_data.row(0).cell(1) == "£300"
        assert requirements_data.row(1).cell(0) == "Earliest start date"
        assert requirements_data.row(1).cell(1) == "02/02/2017"
        assert requirements_data.row(2).cell(0) == "Email address"
        assert requirements_data.row(2).cell(1) == "contact@big.com"

    def test_check_your_answers_page_shows_submit_button_and_closing_date_for_draft_applications(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(data={'status': 'draft'})

        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 200

        closing_date_paragraph = doc.xpath("//main[@id='content']//form//p/text()")[0]
        assert closing_date_paragraph == \
            "Once you submit you can update your application until Thursday 7 April 2016 at 12:00am GMT."

        input_buttons = [item.text.strip() for item in doc.xpath("//button")]
        assert input_buttons == ["Submit application"]

        # 'View the opportunity' link is hidden
        view_opportunity_links = doc.xpath(
            '//a[@href="{0}"][contains(normalize-space(text()), normalize-space("{1}"))]'.format(
                "/digital-outcomes-and-specialists/opportunities/1234/",
                "View the opportunity",
            )
        )
        assert len(view_opportunity_links) == 0

    @pytest.mark.parametrize('brief_response_status', ['draft', 'submitted'])
    @pytest.mark.parametrize('brief_status', ['closed', 'awarded', 'cancelled', 'unsuccessful'])
    def test_check_your_answers_hides_submit_button_and_closing_date_for_non_live_briefs(
        self,
        brief_status,
        brief_response_status,
    ):
        self.brief['briefs']['status'] = brief_status
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={'status': brief_response_status},
        )

        res = self.client.get('/suppliers/opportunities/1234/responses/5/application')
        doc = html.fromstring(res.get_data(as_text=True))

        closing_date_paragraph = doc.xpath("//main[@id='content']//form//p/text()")
        assert len(closing_date_paragraph) == 0

        input_buttons = doc.xpath("//input[@class='button-save']/@value")
        assert len(input_buttons) == 0

    def test_check_your_answers_page_shows_view_opportunity_link_for_submitted_applications(self):
        self.data_api_client.get_brief_response.return_value = self.brief_response(data={'status': 'submitted'})

        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/application',
            data={}
        )
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 200

        view_opportunity_links = doc.xpath(
            '//a[@href="{0}"][contains(normalize-space(text()), normalize-space("{1}"))]'.format(
                "/digital-outcomes-and-specialists/opportunities/1234",
                "View the opportunity",
            )
        )
        assert len(view_opportunity_links) == 1
        view_your_opportunities_link = doc.xpath(
            '//a[@href="{0}"][contains(normalize-space(text()), normalize-space("{1}"))]'.format(
                "/suppliers/opportunities/frameworks/digital-outcomes-and-specialists",
                "Your Digital Outcomes and Specialists opportunities",
            )
        )
        assert len(view_your_opportunities_link) == 2  # Including breadcrumb link

        # Submit button and closing date paragraph are hidden
        closing_date_paragraph = doc.xpath("//main[@id='content']//form//p/text()")
        assert len(closing_date_paragraph) == 0
        input_buttons = doc.xpath("//input[@class='button-save']/text()")
        assert len(input_buttons) == 0

    @pytest.mark.parametrize('brief_response_status', ['submitted', 'pending-awarded', 'awarded'])
    @pytest.mark.parametrize('brief_status', ['awarded', 'cancelled', 'unsuccessful'])
    def test_check_your_answers_page_shows_view_opportunity_and_outcome_link_for_briefs_with_outcome(
        self, brief_status, brief_response_status
    ):
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={'status': brief_response_status}
        )
        self.brief['briefs']['status'] = brief_status
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/application',
            data={}
        )
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 200

        view_opportunity_links = doc.xpath(
            '//a[@href="{0}"][contains(normalize-space(text()), normalize-space("{1}"))]'.format(
                "/digital-outcomes-and-specialists/opportunities/1234",
                "View the opportunity and its outcome",
            )
        )
        assert len(view_opportunity_links) == 1

    def test_check_your_answers_page_shows_legacy_content_for_legacy_application_flow(self):
        # Legacy applications will always be for 'closed' briefs
        self.brief['briefs']['status'] = 'closed'
        # Legacy applications will be for DOS 1
        self.data_api_client.get_framework.return_value = FrameworkStub(
            status="live",
            slug="digital-outcomes-and-specialists",
            clarification_questions_open=False,
            lots=[LotStub(slug="digital-specialists", allows_brief=True).response()]
        ).single_result_response()
        self.data_api_client.get_brief_response.return_value = self.brief_response(
            data={
                'status': 'submitted',
                'dayRate': "300",
                'availability': '02/02/2017',
                'respondToEmailAddress': "contact@big.com",
                'essentialRequirements': [True, True, True],
                'brief': {'framework': {'slug': 'digital-outcomes-and-specialists'}}
            }
        )
        res = self.client.get('/suppliers/opportunities/1234/responses/5/application', data={})
        doc = html.fromstring(res.get_data(as_text=True))

        assert res.status_code == 200

        # Do not show edit links, submit or closing date
        edit_application_links = [anchor.get('href') for anchor in doc.xpath('//a') if anchor.text_content() == 'Edit']
        assert len(edit_application_links) == 0
        closing_date_paragraph = doc.xpath("//main[@id='content']//form//p/text()")
        assert len(closing_date_paragraph) == 0
        input_buttons = doc.xpath("//input[@class='button-save']/text()")
        assert len(input_buttons) == 0

        # View opportunity links still shown
        view_opportunity_links = doc.xpath(
            '//a[@href="{0}"][contains(normalize-space(text()), normalize-space("{1}"))]'.format(
                "/digital-outcomes-and-specialists/opportunities/1234",
                "View the opportunity",
            )
        )
        assert len(view_opportunity_links) == 1

        # Legacy content differs slightly
        section_headings = [h2.strip() for h2 in doc.xpath('//main//*//h2/text()')]
        assert section_headings == [
            'Your essential skills and experience',
            'Your nice-to-have skills and experience',
            'Your details',
        ]
        requirements_data = Table(doc, "Your details")
        assert requirements_data.row(1).cell(0) == "Date the specialist can start work"

    def test_check_your_answers_page_renders_for_incomplete_brief_responses(self):
        incomplete_brief_resp = self.brief_response(data={'status': 'draft'})
        self.data_api_client.get_brief_response.return_value = incomplete_brief_resp

        self.brief['briefs']['status'] = 'live'
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/application',
            data={}
        )
        assert res.status_code == 200

    @pytest.mark.parametrize('brief_status', ['withdrawn', 'draft'])
    def test_check_your_answers_page_404s_for_draft_or_withdrawn_brief(self, brief_status):
        self.data_api_client.get_brief.return_value = BriefStub(
            status=brief_status, lot_slug='digital-specialists'
        ).single_result_response()
        res = self.client.get(
            '/suppliers/opportunities/1234/responses/5/application',
            data={}
        )
        assert res.status_code == 404

    @pytest.mark.parametrize('method', ['get', 'post'])
    def test_check_your_answers_page_404s_if_brief_response_does_not_exist(self, method):
        self.data_api_client.get_brief_response = mock.MagicMock(side_effect=HTTPError(mock.Mock(status_code=404)))

        res = self.client.open('/suppliers/opportunities/1234/responses/250/application', method=method)

        assert res.status_code == 404
        self.data_api_client.get_brief_response.assert_called_once_with(250)

    @pytest.mark.parametrize('method', ['get', 'post'])
    def test_check_your_answers_page_404s_if_brief_response_does_not_relate_to_brief(self, method):
        self.data_api_client.get_brief_response.return_value = {
            "briefResponses": {
                "briefId": 234,
                "supplierId": 1234
            }
        }

        res = self.client.open('/suppliers/opportunities/1234/responses/5/application', method=method)
        assert res.status_code == 404

    @pytest.mark.parametrize('method', ['get', 'post'])
    @mock.patch("app.main.views.briefs.current_user")
    def test_check_your_answers_page_404s_if_brief_response_does_not_relate_to_current_user(self, current_user, method):
        current_user.supplier_id = 789

        res = self.client.open('/suppliers/opportunities/1234/responses/5/application', method=method)
        assert res.status_code == 404

    @pytest.mark.parametrize('method', ['get', 'post'])
    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    @mock.patch("app.main.views.briefs._render_not_eligible_for_brief_error_page", autospec=True)
    def test_check_your_answers_page_renders_ineligible_page_if_supplier_ineligible(
            self, _render_not_eligible_for_brief_error_page, is_supplier_eligible_for_brief, method
    ):
        is_supplier_eligible_for_brief.return_value = False
        _render_not_eligible_for_brief_error_page.return_value = 'dummy response', 403

        res = self.client.open('/suppliers/opportunities/1234/responses/5/application', method=method)
        assert res.status_code == 403
        _render_not_eligible_for_brief_error_page.assert_called_with(self.brief['briefs'])


class BriefResponseTestHelpers():
    def _get_data_from_table(self, doc, table_name):
        return Table(doc, table_name)


class TestStartBriefResponseApplication(BaseApplicationTest, BriefResponseTestHelpers):
    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()
        self.brief = BriefStub(status='live', lot_slug='digital-specialists').single_result_response()
        self.brief['briefs']['publishedAt'] = '2016-12-25T12:00:00.000000Z'
        self.login()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_will_return_404_if_brief_is_closed(self):
        self.brief = BriefStub(status='closed', lot_slug='digital-specialists').single_result_response()
        self.brief['briefs']['publishedAt'] = '2016-12-25T12:00:00.000000Z'
        self.data_api_client.get_brief.return_value = self.brief

        res = self.client.get('/suppliers/opportunities/1234/responses/start')

        assert res.status_code == 404

    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    @mock.patch("app.main.views.briefs._render_not_eligible_for_brief_error_page", autospec=True)
    def test_will_show_not_eligible_response_if_supplier_is_not_eligible_for_brief(
        self, _render_not_eligible_for_brief_error_page, is_supplier_eligible_for_brief
    ):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        is_supplier_eligible_for_brief.return_value = False
        _render_not_eligible_for_brief_error_page.return_value = 'dummy response', 403

        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 403
        _render_not_eligible_for_brief_error_page.assert_called_once_with(self.brief['briefs'])

    def test_start_application_contains_title_and_breadcrumbs(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 200

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath('//h1')[0].text.strip() == "Before you start"
        assert doc.xpath("//button")[0].text.strip() == 'Start application'

        brief = self.brief['briefs']
        expected_breadcrumbs = [
            ('Digital Marketplace', '/'),
            ('Supplier opportunities', '/digital-outcomes-and-specialists/opportunities'),
            (brief['title'], '/digital-outcomes-and-specialists/opportunities/{}'.format(brief['id'])),
            ("Apply for ‘{}’".format(brief['title']), '')
        ]
        self.assert_breadcrumbs(res, expected_breadcrumbs)

    def test_start_page_is_viewable_and_has_start_button_if_no_existing_brief_response(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//button")[0].text.strip() == 'Start application'

    def test_start_page_is_viewable_and_has_continue_link_if_draft_brief_response_exists(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [
                {
                    "id": 2,
                    "status": "draft",
                }
            ]
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')

        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//button")[0].text.strip() == 'Continue application'
        assert doc.xpath("//form[@method='get']/@action")[0] == '/suppliers/opportunities/1234/responses/2'

    def test_will_show_not_eligible_response_if_supplier_has_already_submitted_application(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [
                {
                    "id": 5,
                    "status": "submitted",
                    "submittedAt": "2016-07-20T10:34:08.993952Z",
                }
            ]
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application'

    def test_start_page_for_specialist_brief_shows_specialist_content(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert 'give the date the specialist will be available to start work' in data
        assert "provide the specialist's day rate" in data
        assert "say which skills and experience the specialist has" in data
        assert "give evidence for all the skills and experience the specialist has" in data
        assert "The buyer will assess and score your evidence to shortlist the best specialists." in data
        assert "the work the specialist did" in data

    def test_start_page_for_outcomes_brief_shows_outcomes_content(self):
        self.brief['briefs']['lotSlug'] = 'digital-outcomes'
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert 'give the date the team will be available to start work' in data
        assert "say which skills and experience the team have" in data
        assert "give evidence for all the skills and experience the team have" in data
        assert "The buyer will assess and score your evidence to shortlist the best suppliers." in data
        assert "the work the team did" in data

        assert "provide the specialist's day rate" not in data

    def test_start_page_for_user_research_participants_brief_shows_user_research_content(self):
        self.brief['briefs']['lotSlug'] = 'user-research-participants'
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        res = self.client.get('/suppliers/opportunities/1234/responses/start')
        assert res.status_code == 200

        data = res.get_data(as_text=True)

        assert 'give the date you will be available to start work' in data
        assert "say which skills and experience you have" in data
        assert "give evidence for all the skills and experience you have" in data
        assert "The buyer will assess and score your evidence to shortlist the best suppliers." in data
        assert "the work you did" in data

        assert "provide the specialist's day rate" not in data


class TestPostStartBriefResponseApplication(BaseApplicationTest):
    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()
        self.brief = BriefStub(status='live', lot_slug='digital-specialists').single_result_response()
        self.brief['briefs']['publishedAt'] = '2016-12-25T12:00:00.000000Z'
        self.login()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    @mock.patch("app.main.views.briefs._render_not_eligible_for_brief_error_page", autospec=True)
    def test_will_show_not_eligible_response_if_supplier_is_not_eligible_for_brief(
        self, _render_not_eligible_for_brief_error_page, is_supplier_eligible_for_brief
    ):
        self.data_api_client.get_brief.return_value = self.brief
        is_supplier_eligible_for_brief.return_value = False
        _render_not_eligible_for_brief_error_page.return_value = 'dummy response', 403

        res = self.client.post('/suppliers/opportunities/2345/responses/start')
        assert res.status_code == 403
        _render_not_eligible_for_brief_error_page.assert_called_once_with(self.brief['briefs'])

    def test_valid_post_calls_api_and_redirects_to_edit_the_created_brief_response_if_no_application_started(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': []
        }
        self.data_api_client.create_brief_response.return_value = {
            'briefResponses': {
                'id': 10
            }
        }

        res = self.client.post('/suppliers/opportunities/1234/responses/start')
        self.data_api_client.create_brief_response.assert_called_once_with(1234, 1234, {}, "email@email.com")
        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/10'

    def test_redirects_to_beginning_of_ongoing_application_if_application_in_progress_but_not_submitted(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [
                {
                    'id': 11,
                    'status': 'draft'
                }
            ]
        }

        res = self.client.post('/suppliers/opportunities/1234/responses/start')
        self.data_api_client.create_brief_response.assert_not_called()
        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/11'

    def test_redirects_to_response_page_with_flash_message_if_application_already_submitted(self):
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [
                {
                    'id': 5,
                    'status': 'submitted'
                }
            ]
        }

        res = self.client.post('/suppliers/opportunities/1234/responses/start')
        self.data_api_client.create_brief_response.assert_not_called()
        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/5/application'


class TestResponseResultPage(BaseApplicationTest, BriefResponseTestHelpers):

    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()
        lots = [LotStub(slug="digital-specialists", allows_brief=True).response()]
        self.framework = FrameworkStub(
            status="live",
            slug="digital-outcomes-and-specialists",
            clarification_questions_open=False,
            lots=lots
        ).single_result_response()
        self.brief = BriefStub(status='live').single_result_response()

        self.brief['briefs']['evaluationType'] = ['Interview']
        self.brief['briefs']['niceToHaveRequirements'] = []
        self.brief['briefs']['essentialRequirements'] = ['Must one', 'Must two', 'Must three']
        self.brief['briefs']['dayRate'] = '300'
        self.brief_responses = {
            'briefResponses': [
                {
                    'essentialRequirementsMet': True,
                    'essentialRequirements': [
                        {'evidence': 'Did a thing'},
                        {'evidence': 'Produced a thing'},
                        {'evidence': 'Did a thing'}
                    ]
                }
            ]
        }
        self.login()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def set_framework_and_eligibility_for_api_client(self):
        self.data_api_client.get_framework.return_value = self.framework
        self.data_api_client.is_supplier_eligible_for_brief.return_value = True

    @pytest.mark.parametrize('status', PUBLISHED_BRIEF_STATUSES)
    def test_view_response_200s_for_every_published_brief_status(self, status):
        self.set_framework_and_eligibility_for_api_client()
        self.brief['briefs']['status'] = status
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses

        res = self.client.get('/suppliers/opportunities/1234/responses/result')
        assert res.status_code == 200

    def test_view_response_shows_page_title_with_brief_name_and_breadcrumbs(self):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses

        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//h1[contains(text(),'What happens next')]")

        expected_breadcrumbs = [
            ('Digital Marketplace', '/'),
            ('Your account', '/suppliers'),
            (
                'Your Digital Outcomes and Specialists opportunities',
                '/suppliers/opportunities/frameworks/digital-outcomes-and-specialists'
            ),
            ('Your response to ‘I need a thing to do a thing’', ),
        ]
        self.assert_breadcrumbs(res, expected_breadcrumbs)

    @pytest.mark.parametrize('status', ['live', 'closed'])
    def test_next_steps_content_shown_on_results_page(self, status):
        self.set_framework_and_eligibility_for_api_client()
        brief = self.brief.copy()
        brief["briefs"]['status'] = status
        self.data_api_client.get_brief.return_value = brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses

        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        assert doc.xpath("//h2[contains(text(),'Shortlist')]")

    def test_evaluation_methods_load_default_value(self):
        no_extra_eval_brief = self.brief.copy()
        no_extra_eval_brief['briefs'].pop('evaluationType')

        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = no_extra_eval_brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses
        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        assert len(doc.xpath('//li[contains(normalize-space(text()), "a work history")]')) == 1

    def test_evaluation_methods_shown_with_a_or_an(self):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses
        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 200
        doc = html.fromstring(res.get_data(as_text=True))
        assert len(doc.xpath('//li[contains(normalize-space(text()), "a work history")]')) == 1
        assert len(doc.xpath('//li[contains(normalize-space(text()), "an interview")]')) == 1

    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    @mock.patch("app.main.views.briefs._render_not_eligible_for_brief_error_page", autospec=True)
    def test_will_show_not_eligible_response_if_supplier_is_not_eligible_for_brief(
        self, _render_not_eligible_for_brief_error_page, is_supplier_eligible_for_brief
    ):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = self.brief_responses
        is_supplier_eligible_for_brief.return_value = False
        _render_not_eligible_for_brief_error_page.return_value = 'dummy response', 403

        res = self.client.get('/suppliers/opportunities/1234/responses/result')
        assert res.status_code == 403
        _render_not_eligible_for_brief_error_page.assert_called_once_with(self.brief['briefs'])

    @pytest.mark.parametrize(
        'response_msg, response_status_code, expected_error_message, expected_status_code',
        [
            (
                {'essentialRequirements': 'answer_required'},
                400,
                'You need to complete all the sections before you can submit your application.',
                400
            ),
            (
                {'essentialRequirements': 'different_error'},
                400,
                'There was a problem submitting your application.',
                400
            ),
            (
                "Hoddmimis",
                400,
                'There was a problem submitting your application.',
                400
            ),
            (
                "Ragnarok",
                500,
                "Sorry, we’re experiencing technical difficulties",
                500
            ),
        ]
    )
    def test_error_message_shown_for_exceptions_when_submitting_application(
            self, response_msg, response_status_code, expected_error_message, expected_status_code
    ):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [self.brief_response(data={'essentialRequirementsMet': True})['briefResponses']]
        }
        self.data_api_client.is_supplier_eligible_for_brief.return_value = True
        # The 'submit' action failed with an exception
        self.data_api_client.submit_brief_response.side_effect = HTTPError(
            mock.Mock(status_code=response_status_code), response_msg
        )

        res = self.client.post(
            '/suppliers/opportunities/{brief_id}/responses/{brief_response_id}/application'.format(
                brief_id=self.brief['briefs']['id'],
                brief_response_id=self.brief_response()['briefResponses']['id']
            ),
            data={}
        )
        assert res.status_code == expected_status_code
        data = res.get_data(as_text=True)

        # Error message should be shown
        assert expected_error_message in data

    def test_error_message_shown_for_failed_submit(self):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [self.brief_response(data={'essentialRequirementsMet': True})['briefResponses']]
        }
        self.data_api_client.is_supplier_eligible_for_brief.return_value = True
        # The 'submit' action returned 200 but didn't update the DB
        self.data_api_client.submit_brief_response.return_value = {
            'briefResponses': {'status': 'draft'}
        }

        res = self.client.post(
            '/suppliers/opportunities/{brief_id}/responses/{brief_response_id}/application'.format(
                brief_id=self.brief['briefs']['id'],
                brief_response_id=self.brief_response()['briefResponses']['id']
            ),
            data={}
        )
        assert res.status_code == 400  # No redirect
        data = res.get_data(as_text=True)

        # Error flash message should be shown
        assert 'There was a problem submitting your application.' in data

    @pytest.mark.parametrize('brief_status', ['closed', 'awarded', 'cancelled', 'unsuccessful'])
    def test_submit_to_already_closed_brief(self, brief_status):
        self.set_framework_and_eligibility_for_api_client()
        self.brief['briefs']['status'] = brief_status
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [self.brief_response(data={'essentialRequirementsMet': True})['briefResponses']]
        }
        self.data_api_client.is_supplier_eligible_for_brief.return_value = True

        res = self.client.post(
            '/suppliers/opportunities/{brief_id}/responses/{brief_response_id}/application'.format(
                brief_id=self.brief['briefs']['id'],
                brief_response_id=self.brief_response()['briefResponses']['id'],
            ),
            data={}
        )
        assert res.status_code == 400
        data = res.get_data(as_text=True)
        doc = html.fromstring(data)

        # Error flash message should be shown
        assert doc.xpath(
            "//*[contains(@class, 'banner-destructive-without-action')][normalize-space(string())=$t]",
            t="This opportunity has already closed for applications.",
        )

        # view shouldn't have bothered calling this
        assert self.data_api_client.submit_brief_response.called is False

    @pytest.mark.parametrize('brief_status', ("withdrawn", "draft",))
    def test_submit_to_withdrawn_or_draft_brief(self, brief_status):
        self.set_framework_and_eligibility_for_api_client()
        self.brief['briefs']['status'] = brief_status
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [self.brief_response(data={'essentialRequirementsMet': True})['briefResponses']]
        }

        res = self.client.post(
            '/suppliers/opportunities/{brief_id}/responses/{brief_response_id}/application'.format(
                brief_id=self.brief['briefs']['id'],
                brief_response_id=self.brief_response()['briefResponses']['id'],
            ),
            data={}
        )
        assert res.status_code == 404

        # view shouldn't have bothered calling this
        assert self.data_api_client.submit_brief_response.called is False
        assert self.data_api_client.is_supplier_eligible_for_brief.called is False

    def test_analytics_and_messages_applied_on_first_submission(self):
        """Go through submitting to edit_brief_response and the redirect to view_response_result. Assert messages."""
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.get_brief_response.return_value = self.brief_response()
        self.data_api_client.find_brief_responses.return_value = {
            'briefResponses': [
                self.brief_response(data={'essentialRequirementsMet': True, 'status': 'submitted'})['briefResponses']
            ]
        }

        self.data_api_client.is_supplier_eligible_for_brief.return_value = True

        # The submit action succeeded
        self.data_api_client.submit_brief_response.return_value = {'briefResponses': {'status': 'submitted'}}

        res = self.client.post(
            '/suppliers/opportunities/{brief_id}/responses/{brief_response_id}/application'.format(
                brief_id=self.brief['briefs']['id'],
                brief_response_id=self.brief_response()['briefResponses']['id']
            ),
            data={},
            follow_redirects=True
        )
        assert res.status_code == 200
        data = res.get_data(as_text=True)
        doc = html.fromstring(data)

        # Assert the analytics exists
        analytics_div = doc.xpath('//div[@data-analytics="trackPageView"]/@data-url')[0]
        assert analytics_div == '/suppliers/opportunities/1234/responses/result?result=success'

        # Assert we get the correct banner message (and only the correct one).
        assert 'Your application has been submitted.' in data

    def test_view_response_result_no_application_redirect_to_start_page(self):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {"briefResponses": []}
        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/start'

    def test_view_response_result_draft_application_redirect_to_check_your_answers_page(self):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.get_brief.return_value = self.brief
        self.data_api_client.find_brief_responses.return_value = {
            "briefResponses": [
                {"id": 999, 'essentialRequirementsMet': True, 'status': 'draft'}
            ]
        }

        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 302
        assert res.location == 'http://localhost.localdomain/suppliers/opportunities/1234/responses/999/application'

    @mock.patch("app.main.views.briefs.is_supplier_eligible_for_brief")
    def test_view_result_legacy_flow_redirects_to_check_your_answer(self, is_supplier_eligible_for_brief):
        self.set_framework_and_eligibility_for_api_client()
        self.data_api_client.find_brief_responses.return_value = {
            "briefResponses": [
                {"id": 999, "essentialRequirements": [True, True, True]}
            ]
        }
        self.brief['briefs']['status'] = 'closed'
        self.data_api_client.get_brief.return_value = self.brief
        is_supplier_eligible_for_brief.return_value = True

        res = self.client.get('/suppliers/opportunities/1234/responses/result')

        assert res.status_code == 302
        assert res.location == "http://localhost.localdomain/suppliers/opportunities/1234/responses/999/application"


@mock.patch("app.main.views.briefs.current_user")
@mock.patch("app.main.views.briefs.render_template", autospec=True)
class TestRenderNotEligibleForBriefErrorPage(BaseApplicationTest):
    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()
        self.brief = BriefStub(status='live').response()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_clarification_question_true(self, render_template, current_user):
        _render_not_eligible_for_brief_error_page(self.brief, True)

        render_template.assert_called_with(
            "briefs/not_is_supplier_eligible_for_brief_error.html",
            clarification_question=True,
            framework_name='Digital Outcomes and Specialists',
            lot=mock.ANY,
            reason=mock.ANY,
            data_reason_slug=mock.ANY,
        )

    def test_not_on_framework(self, render_template, current_user):
        current_user.supplier_id = 100
        self.data_api_client.find_services.return_value = {"services": []}

        _render_not_eligible_for_brief_error_page(self.brief)

        self.data_api_client.find_services.assert_called_once_with(
            supplier_id=100,
            framework='digital-outcomes-and-specialists',
            status='published'
        )
        render_template.assert_called_with(
            "briefs/not_is_supplier_eligible_for_brief_error.html",
            clarification_question=False,
            framework_name='Digital Outcomes and Specialists',
            lot='digital-specialists',
            reason='supplier-not-on-framework',
            data_reason_slug='supplier-not-on-digital-outcomes-and-specialists',
        )

    def test_not_on_lot(self, render_template, current_user):
        current_user.supplier_id = 100
        self.data_api_client.find_services.side_effect = lambda *args, **kwargs: (
            {"services": [{"something": "nonempty"}]} if kwargs.get("lot") is None else {"services": []}
        )

        _render_not_eligible_for_brief_error_page(self.brief)

        self.data_api_client.find_services.assert_has_calls(
            [
                mock.call(
                    supplier_id=100,
                    framework='digital-outcomes-and-specialists',
                    status='published'
                ),
                mock.call(
                    supplier_id=100,
                    framework='digital-outcomes-and-specialists',
                    status='published',
                    lot='digital-specialists'
                ),
            ],
            any_order=True
        )
        render_template.assert_called_with(
            "briefs/not_is_supplier_eligible_for_brief_error.html",
            clarification_question=False,
            framework_name='Digital Outcomes and Specialists',
            lot='digital-specialists',
            reason='supplier-not-on-lot',
            data_reason_slug='supplier-not-on-lot',
        )

    def test_not_on_role(self, render_template, current_user):
        current_user.supplier_id = 100
        self.data_api_client.find_services.return_value = {"services": [{"service": "data"}]}

        _render_not_eligible_for_brief_error_page(self.brief)

        self.data_api_client.find_services.assert_has_calls(
            [
                mock.call(
                    supplier_id=100,
                    framework='digital-outcomes-and-specialists',
                    status='published'
                ),
                mock.call(
                    supplier_id=100,
                    framework='digital-outcomes-and-specialists',
                    status='published',
                    lot='digital-specialists'
                ),
            ],
            any_order=True
        )
        render_template.assert_called_with(
            "briefs/not_is_supplier_eligible_for_brief_error.html",
            clarification_question=False,
            framework_name='Digital Outcomes and Specialists',
            lot='digital-specialists',
            reason='supplier-not-on-role',
            data_reason_slug='supplier-not-on-role',
        )


class TestRedirectToPublicOpportunityPage(BaseApplicationTest):

    def setup_method(self, method):
        super().setup_method(method)
        self.data_api_client_patch = mock.patch('app.main.views.briefs.data_api_client', autospec=True)
        self.data_api_client = self.data_api_client_patch.start()

        lots = [LotStub(slug="digital-specialists", allows_brief=True).response()]
        self.framework = FrameworkStub(
            status="live",
            slug="digital-outcomes-and-specialists",
            clarification_questions_open=False,
            lots=lots
        ).single_result_response()
        self.brief = BriefStub(status='live').single_result_response()

    def teardown_method(self, method):
        self.data_api_client_patch.stop()
        super().teardown_method(method)

    def test_suppliers_opportunity_brief_id_redirects_to_public_page(self):
        self.data_api_client.get_brief.return_value = self.brief
        brief_id = self.brief['briefs']['id']
        resp = self.client.get('suppliers/opportunities/{}'.format(brief_id))

        assert resp.status_code == 302
        assert resp.location == 'http://localhost.localdomain/digital-outcomes-and-specialists/opportunities/{}'.format(brief_id)  # noqa

    def test_suppliers_opportunity_brief_id_404s_if_brief_not_found(self):
        self.data_api_client.get_brief.side_effect = HTTPError(mock.Mock(status_code=404))
        resp = self.client.get('suppliers/opportunities/99999999')

        assert resp.status_code == 404
