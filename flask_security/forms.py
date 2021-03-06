# -*- coding: utf-8 -*-
"""
    flask.ext.security.forms
    ~~~~~~~~~~~~~~~~~~~~~~~~

    Flask-Security forms module

    :copyright: (c) 2012 by Matt Wright.
    :license: MIT, see LICENSE for more details.
"""

import inspect
import urlparse

from flask import request, current_app
from flask.ext.wtf import Form as BaseForm, TextField, PasswordField, \
     SubmitField, HiddenField, Required, BooleanField, EqualTo, Email, \
     ValidationError, Length, Field
from flask.ext.login import current_user
from werkzeug.local import LocalProxy

from .confirmable import requires_confirmation
from .utils import verify_password, verify_and_update_password, get_message

# Convenient reference
_datastore = LocalProxy(lambda: current_app.extensions['security'].datastore)

email_required = Required(message='Email not provided')

email_validator = Email(message='Invalid email address')

password_required = Required(message="Password not provided")


def unique_user_email(form, field):
    if _datastore.find_user(email=field.data) is not None:
        raise ValidationError(field.data +
                              ' is already associated with an account')


def valid_user_email(form, field):
    form.user = _datastore.find_user(email=field.data)
    if form.user is None:
        raise ValidationError('Specified user does not exist')


class Form(BaseForm):
    def __init__(self, *args, **kwargs):
        if current_app.testing:
            self.TIME_LIMIT = None
        super(Form, self).__init__(*args, **kwargs)


class EmailFormMixin():
    email = TextField("Email Address",
        validators=[email_required,
                    email_validator])


class UserEmailFormMixin():
    user = None
    email = TextField("Email Address",
        validators=[email_required,
                    email_validator,
                    valid_user_email])


class UniqueEmailFormMixin():
    email = TextField("Email Address",
        validators=[email_required,
                    email_validator,
                    unique_user_email])


class PasswordFormMixin():
    password = PasswordField("Password",
        validators=[password_required])


class NewPasswordFormMixin():
    password = PasswordField("Password",
        validators=[password_required,
                    Length(min=6, max=128)])


class PasswordConfirmFormMixin():
    password_confirm = PasswordField("Retype Password",
        validators=[EqualTo('password', message="Passwords do not match")])


class NextFormMixin():
    next = HiddenField()

    def validate_next(self, field):
        url_next = urlparse.urlsplit(field.data)
        url_base = urlparse.urlsplit(request.host_url)
        if url_next.netloc and url_next.netloc != url_base.netloc:
            field.data = ''
            raise ValidationError('Redirections outside the domain are forbidden')


class RegisterFormMixin():
    submit = SubmitField("Register")

    def to_dict(form):
        def is_field_and_user_attr(member):
            return isinstance(member, Field) and \
                hasattr(_datastore.user_model, member.name)

        fields = inspect.getmembers(form, is_field_and_user_attr)
        return dict((key, value.data) for key, value in fields)


class SendConfirmationForm(Form, UserEmailFormMixin):
    """The default forgot password form"""

    submit = SubmitField("Resend Confirmation Instructions")

    def __init__(self, *args, **kwargs):
        super(SendConfirmationForm, self).__init__(*args, **kwargs)
        if request.method == 'GET':
            self.email.data = request.args.get('email', None)

    def validate(self):
        if not super(SendConfirmationForm, self).validate():
            return False
        if self.user.confirmed_at is not None:
            self.email.errors.append(get_message('ALREADY_CONFIRMED')[0])
            return False
        return True


class ForgotPasswordForm(Form, UserEmailFormMixin):
    """The default forgot password form"""

    submit = SubmitField("Recover Password")


class PasswordlessLoginForm(Form, UserEmailFormMixin):
    """The passwordless login form"""

    submit = SubmitField("Send Login Link")

    def __init__(self, *args, **kwargs):
        super(PasswordlessLoginForm, self).__init__(*args, **kwargs)

    def validate(self):
        if not super(PasswordlessLoginForm, self).validate():
            return False
        if not self.user.is_active():
            self.email.errors.append(get_message('DISABLED_ACCOUNT')[0])
            return False
        return True


class LoginForm(Form, NextFormMixin):
    """The default login form"""

    email = TextField('Email Address')
    password = PasswordField('Password')
    remember = BooleanField("Remember Me")
    submit = SubmitField("Login")

    def __init__(self, *args, **kwargs):
        super(LoginForm, self).__init__(*args, **kwargs)

    def validate(self):
        if not super(LoginForm, self).validate():
            return False

        if self.email.data.strip() == '':
            self.email.errors.append(get_message('EMAIL_NOT_PROVIDED')[0])
            return False

        if self.password.data.strip() == '':
            self.password.errors.append(get_message('PASSWORD_NOT_PROVIDED')[0])
            return False

        self.user = _datastore.find_user(email=self.email.data)

        if self.user is None:
            self.email.errors.append(get_message('USER_DOES_NOT_EXIST')[0])
            return False
        if not verify_and_update_password(self.password.data, self.user):
            self.password.errors.append(get_message('INVALID_PASSWORD')[0])
            return False
        if requires_confirmation(self.user):
            self.email.errors.append(get_message('CONFIRMATION_REQUIRED')[0])
            return False
        if not self.user.is_active():
            self.email.errors.append(get_message('DISABLED_ACCOUNT')[0])
            return False
        return True


class ConfirmRegisterForm(Form, RegisterFormMixin,
                          UniqueEmailFormMixin, NewPasswordFormMixin):
    pass


class RegisterForm(ConfirmRegisterForm, PasswordConfirmFormMixin):
    pass


class ResetPasswordForm(Form, NewPasswordFormMixin, PasswordConfirmFormMixin):
    """The default reset password form"""

    submit = SubmitField("Reset Password")


class ChangePasswordForm(Form, PasswordFormMixin):
    """The default change password form"""

    new_password = PasswordField("New Password",
        validators=[password_required,
                    Length(min=6, max=128)])

    new_password_confirm = PasswordField("Retype Password",
        validators=[EqualTo('new_password', message="Passwords do not match")])

    submit = SubmitField("Change Password")

    def validate(self):
        if not super(ChangePasswordForm, self).validate():
            return False

        if self.password.data.strip() == '':
            self.password.errors.append('Password not provided')
            return False
        if not verify_and_update_password(self.password.data, current_user):
            self.password.errors.append(get_message('INVALID_PASSWORD')[0])
            return False
        return True
