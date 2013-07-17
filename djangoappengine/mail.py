from email.MIMEBase import MIMEBase

from django.core.mail.backends.base import BaseEmailBackend
from django.core.mail import EmailMultiAlternatives
from django.core.exceptions import ImproperlyConfigured

from google.appengine.api.app_identity import get_application_id
from google.appengine.api import mail as aeemail
from google.appengine.runtime import apiproxy_errors

def _check_for_app_admins(message):
    # "admins@APP-ID.appspotmail.com"
    # ignore multiple admins adresses...
    for to in message.to:
        if 'admins@%s.appspotmail.com' % get_application_id() in to or '<admins@%s.appspotmail.com>' % get_application_id() in to:
            return True

def _send_app_admins(message):
    kw = {}

    # kw['to'] = message.to => unused warning
    # those sould be empty
    # kw['cc'] = message.cc
    # kw['bcc'] = message.bcc
    if hasattr(message, 'reply_to'):
        kw['reply_to'] = message.reply_to    
    if hasattr(message, 'html'):
        kw['html'] = message.html
    if hasattr(message, 'attachments'):
        kw['attachments'] = message.attachments
    if hasattr(message, 'headers'):
        kw['headers'] = message.headers
    
    aeemail.send_mail_to_admins(message.sender, message.subject, message.body, **kw)

def _send_deferred(message, fail_silently=False):
    try:
        if _check_for_app_admins(message):
            _send_app_admins(message)
        else:
            message.send()
    except (aeemail.Error, apiproxy_errors.Error):
        if not fail_silently:
            raise


class EmailBackend(BaseEmailBackend):
    can_defer = False

    def send_messages(self, email_messages):
        num_sent = 0
        for message in email_messages:
            if self._send(message):
                num_sent += 1
        return num_sent

    def _copy_message(self, message):
        """
        Creates and returns App Engine EmailMessage class from message.
        """
        gmsg = aeemail.EmailMessage(sender=message.from_email,
                                    to=message.to,
                                    subject=message.subject,
                                    body=message.body)
        if message.extra_headers.get('Reply-To', None):
            gmsg.reply_to = message.extra_headers['Reply-To']
        if message.cc:
            gmsg.cc = list(message.cc)
        if message.bcc:
            gmsg.bcc = list(message.bcc)
        if message.attachments:
            # Must be populated with (filename, filecontents) tuples.
            attachments = []
            for attachment in message.attachments:
                if isinstance(attachment, MIMEBase):
                    attachments.append((attachment.get_filename(),
                                        attachment.get_payload(decode=True)))
                else:
                    attachments.append((attachment[0], attachment[1]))
            gmsg.attachments = attachments
        # Look for HTML alternative content.
        if isinstance(message, EmailMultiAlternatives):
            for content, mimetype in message.alternatives:
                if mimetype == 'text/html':
                    gmsg.html = content
                    break
        return gmsg

    def _send(self, message):
        try:
            message = self._copy_message(message)
        except (ValueError, aeemail.InvalidEmailError), err:
            import logging
            logging.warn(err)
            if not self.fail_silently:
                raise
            return False
        if self.can_defer:
            self._defer_message(message)
            return True
        try:
            if _check_for_app_admins(message):
                _send_app_admins(message)
            else:
                message.send()
        except (aeemail.Error, apiproxy_errors.Error):
            if not self.fail_silently:
                raise
            return False
        return True

    def _defer_message(self, message):
        from google.appengine.ext import deferred
        from django.conf import settings
        queue_name = getattr(settings, 'EMAIL_QUEUE_NAME', 'default')
        deferred.defer(_send_deferred,
                       message,
                       fail_silently=self.fail_silently,
                       _queue=queue_name)


class AsyncEmailBackend(EmailBackend):
    can_defer = True
