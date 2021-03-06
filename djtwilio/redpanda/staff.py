# -*- coding: utf-8 -*-

import json
import os
import requests
import sys

# env
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'djtwilio.settings.shell')

# required if using django models
import django
django.setup()

from django.conf import settings
from django.db import connections
from djimix.core.database import get_connection
from djimix.core.database import xsql
from djtools.utils.mail import send_mail
from djtwilio.core.models import Sender
from djtwilio.core.utils import send_message
from twilio.rest import Client


# informix environment
os.environ['INFORMIXSERVER'] = settings.INFORMIXSERVER
os.environ['DBSERVERNAME'] = settings.DBSERVERNAME
os.environ['INFORMIXDIR'] = settings.INFORMIXDIR
os.environ['ODBCINI'] = settings.ODBCINI
os.environ['ONCONFIG'] = settings.ONCONFIG
os.environ['INFORMIXSQLHOSTS'] = settings.INFORMIXSQLHOSTS
os.environ['LD_LIBRARY_PATH'] = settings.LD_LIBRARY_PATH
os.environ['LD_RUN_PATH'] = settings.LD_RUN_PATH


def main():
    """Send staff notification to complete daily health check."""
    request = None
    frum = settings.DEFAULT_FROM_EMAIL
    subject = "Daily Health Check Reminder"
    # cids from redpanda database
    cids = []
    with connections['redpanda'].cursor() as cursor:
        reggies = cursor.execute('SELECT * FROM research_registration WHERE mobile=True')
        for reggie in cursor.fetchall():
            cids.append(int(reggie[11]))
    # fetch our staff mobiles
    phile = os.path.join(settings.BASE_DIR, 'redpanda/staff.sql')
    with open(phile) as incantation:
        sql = '{0} {1}'.format(incantation.read(), tuple(cids))
        print(sql)
    with get_connection() as connection:
        peeps = xsql(sql, connection).fetchall()

    # twilio client
    client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
    sender = Sender.objects.get(pk=settings.REDPANDA_SENDER_ID)
    print('sender = {0}'.format(sender))
    # fetch our UUID
    mobi = 0
    mail = 0
    with get_connection(settings.MSSQL_EARL, encoding=False) as mssql_cnxn:
        for peep in peeps:
            sql = "SELECT * FROM fwk_user WHERE HostID like '%{}'".format(peep[0])
            row = xsql(sql, mssql_cnxn).fetchone()
            if row:
                '''
                earl = 'https://{0}{1}{2}?uid={3}'.format(
                    settings.REDPANDA_SERVER_URL,
                    settings.REDPANDA_ROOT_URL,
                    settings.REDPANDA_SHORT_URL_API,
                    row[0],
                )
                '''
                earl = 'https://{0}{1}'.format(
                    settings.REDPANDA_SERVER_URL,
                    settings.REDPANDA_ROOT_URL,
                )
                print(earl)
                #response = requests.get(earl)
                #jason_data = json.loads(response.text)
                #earl = jason_data['lynx']
                #print(earl)
                # send an SMS or an email
                if peep[6]:
                    body = settings.REDPANDA_TEXT_MESSAGE(earl=earl)
                    print(body)
                    response = send_message(client, sender, peep[6], body, peep[0])
                    mobi += 1
                else:
                    email = '{0}@carthage.edu'.format(peep[8])
                    mail += 1
                    print(email)
                    #context_data = {'earl': earl, 'peep': peep}
                    #send_mail(
                        #request,
                        #[email],
                        #subject,
                        #frum,
                        #'redpanda/email_reminder.html',
                        #context_data,
                    #)
            else:
                print('peep not found in the portal: {0}'.format(peep[0]))

    print(mobi)
    print(mail)


if __name__ == '__main__':

    sys.exit(main())
