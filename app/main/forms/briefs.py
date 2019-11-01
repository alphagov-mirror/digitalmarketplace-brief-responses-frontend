from flask import Markup
from flask_wtf import FlaskForm
from wtforms import validators

from dmutils.formats import dateformat
from dmutils.forms.fields import DMStripWhitespaceStringField
from dmutils.forms.widgets import DMTextArea


class AskClarificationQuestionForm(FlaskForm):
    """Form for a supplier to ask a clarification question about a given brief."""
    clarification_question = DMStripWhitespaceStringField(
        "Ask a question about ‘{brief[title]}’",
        question_advice=(
            """
            Your question will be published with the buyer’s answer by {submission_deadline}.
            All questions and answers will be posted on the Digital Marketplace. Your company name won’t be visible.
            You shouldn’t include any confidential information in your question.
            Read more about <a class="govuk-link" href="{guidance_url}">how supplier questions are managed</a>.
            """
        ),
        validators=[validators.DataRequired(message='Question cannot be empty'),
                    validators.Length(max=5000, message='Question cannot be longer than 5000 characters'),
                    validators.Regexp(regex="^$|(^(?:\\S+\\s+){0,99}\\S+$)",
                                      message='Question must be no more than 100 words')],
        widget=DMTextArea(max_length_in_words=100),
    )

    def __init__(self, brief, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clarification_question.question = self.clarification_question.question.format(brief=brief)
        self.clarification_question.question_advice = Markup(self.clarification_question.question_advice.format(
            submission_deadline=dateformat(brief['clarificationQuestionsPublishedBy']),
            guidance_url="https://www.gov.uk/guidance/how-to-answer-supplier-questions-about-your-digital-outcomes-and-specialists-requirements",  # noqa
        ))
