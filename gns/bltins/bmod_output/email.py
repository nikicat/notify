import smtplib
import email.mime.multipart
import email.mime.text
import email.utils

import logging

from ulib import validators
import ulib.validators.common # pylint: disable=W0611
import ulib.validators.network

from raava import worker

from . import common
from ... import env


##### Public constants #####
S_EMAIL  = "email"

O_SERVER   = "server"
O_SSL      = "ssl"
O_USER     = "user"
O_PASSWD   = "passwd"
O_FROM     = "from"
O_CC       = "cc"


###
CONFIG_MAP = {
    common.S_OUTPUT: {
        S_EMAIL: {
            O_SERVER: ("localhost",      lambda arg: validators.network.valid_ip_or_host(arg)[0]),
            O_SSL:    (False,            validators.common.valid_bool),
            O_USER:   (None,             validators.common.valid_empty),
            O_PASSWD: (None,             str),
            O_FROM:   ("root@localhost", str),
            O_CC:     ([],               validators.common.valid_string_list),
        },
    },
}


###
DEFAULT_SUBJECT_TEMPLATE = """
    GNS message: ${event.get("host", "<Host?>")}:${event.get("service", "<Service?>")}
"""

DEFAULT_TEXT_TEMPLATE = """
    <%
        import yaml
        host = event.get("host", "<Host?>")
        service = event.get("service", "<Service?>")
        status = event.get("status", "<Status?>")
        dumper = ( lambda arg: yaml.dump(arg, default_flow_style=False, indent=4).strip() )
        data = dumper(dict(event))
        extra = dumper(event.get_extra())
    %>
    The event ${host}:${service} is ${status}.
    See this event in Golem: https://golem.yandex-team.ru/events.sbml?object=${host}&eventtype=${service}&downtime=show

    Event:
    =====
    ${data}
    =====

    Extra information:
    =====
    ${extra}
    =====
"""


##### Private objects #####
_logger = logging.getLogger(common.LOGGER_NAME)


##### Private methods #####
def _send_raw(task, to_list, subject, text):
    if isinstance(to_list, tuple):
        to_list = list(to_list)
    elif not isinstance(to_list, list):
        to_list = [str(to_list)]

    send_from = env.get_config(common.S_OUTPUT, S_EMAIL, O_FROM)
    cc_list = env.get_config(common.S_OUTPUT, S_EMAIL, O_CC)

    message = email.mime.multipart.MIMEMultipart()
    message["From"] = send_from
    message["To"] = ", ".join(to_list)
    if len(cc_list) != 0:
        message["CC"] = ", ".join(cc_list)
    message["Date"] = email.utils.formatdate(localtime=True)
    message["Subject"] = subject
    message.attach(email.mime.text.MIMEText(text))

    server_host = env.get_config(common.S_OUTPUT, S_EMAIL, O_SERVER)
    user = env.get_config(common.S_OUTPUT, S_EMAIL, O_USER)

    _logger.debug("Sending email to: %s; cc: %s; via SMTP %s@%s", to_list, cc_list, user, server_host)

    task.checkpoint()
    if not env.get_config(common.S_OUTPUT, common.O_NOOP):
        smtp_class = ( smtplib.SMTP_SSL if env.get_config(common.S_OUTPUT, S_EMAIL, O_SSL) else smtplib.SMTP )
        try:
            server = smtp_class(server_host)
            if user is not None:
                server.login(user, env.get_config(common.S_OUTPUT, S_EMAIL, O_PASSWD))
            server.sendmail(send_from, to_list + cc_list, message.as_string())
            _logger.info("Email sent to: %s; cc: %s", to_list, cc_list)
        except Exception:
            _logger.exception("Failed to send email to: %s; cc: %s", to_list, cc_list)
        finally:
            server.close()
    else:
        _logger.info("Email sent to: %s; cc: %s (noop)", to_list, cc_list)
    task.checkpoint()

def _send_event(task, to_list, event, subject = DEFAULT_SUBJECT_TEMPLATE, text = DEFAULT_TEXT_TEMPLATE):
    _send_raw(task, to_list, env.format_event(subject, event), env.format_event(text, event))


##### Private classes #####
class _Email:
    send_raw = worker.make_task_builtin(_send_raw)
    send = worker.make_task_builtin(_send_event)


##### Public constants #####
BUILTINS_MAP = {
    "email": _Email,
}
