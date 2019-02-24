from django.conf import settings
from django.shortcuts import render
from django.contrib import messages
from django.shortcuts import get_object_or_404
from django.http import HttpResponse, HttpResponseRedirect, Http404
from django.core.urlresolvers import reverse, reverse_lazy
from django.views.decorators.csrf import csrf_exempt

from djtwilio.apps.sms.forms import BulkForm, IndiForm, StatusCallbackForm
from djtwilio.apps.sms.models import Bulk, Error, Message, Status
from djtwilio.apps.sms.errors import MESSAGE_DELIVERY_CODES
from djtwilio.core.utils import send_message
from djtwilio.core.models import Sender
from djtwilio.apps.sms.data import CtcBlob

from djtools.utils.mail import send_mail
from djtools.utils.cypher import AESCipher
from djzbar.utils.informix import get_session
from djzbar.decorators.auth import portal_auth_required

from twilio.rest import Client

import re
import csv
import json
import unicodedata
import logging

logger = logging.getLogger(__name__)
EARL = settings.INFORMIX_EARL


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def bulk_detail(request, bid):
    user = request.user
    bulk = get_object_or_404(Bulk, pk=bid)
    if bulk.sender.user != user and not user.is_superuser:
        response = HttpResponseRedirect(reverse('sms_send_form'))
    else:
        objects = Message.objects.filter(bulk=bulk)
        response = render(
            request, 'apps/sms/bulk_detail.html', {'bulk':bulk, 'objects': objects}
        )

    return response


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def bulk_list(request):

    user = request.user
    if user.is_superuser:
        bulk = Bulk.objects.all().order_by('-date_created')
    else:
        bulk = Bulk.objects.filter(
            messaging_service__user = user
        ).order_by('-date_created')

    return render(
        request, 'apps/sms/bulk_list.html', {'bulk': bulk,}
    )


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def individual_list(request):

    user = request.user
    if user.is_superuser:
        messages = Message.objects.all().order_by('-date_created')
    else:
        messages = []
        for sender in user.sender.all():
            for m in sender.messenger.all().order_by('-date_created'):
                messages.append(m)

    return render(
        request, 'apps/sms/individual_list.html', {'messages': messages,}
    )


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def detail(request, sid, medium='screen'):

    user = request.user
    try:
        message = Message.objects.get(status__MessageSid=sid)
    except:
        raise Http404

    template = 'apps/sms/detail_{}.html'.format(medium)
    if message.messenger.user != user and not user.is_superuser:
        response = HttpResponseRedirect(
            reverse('sms_send_form')
        )
    else:
        response = render(
        request, template, {'message': message,}
    )

    return response


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def home(request):

    limit = 100
    user = request.user
    if user.is_superuser:
        bulk = Bulk.objects.all().order_by('-date_created')[:limit]
        messages = Message.objects.all().order_by('-date_created')[:limit]
    else:
        bulk = Bulk.objects.filter(
            messaging_service__user=request.user
        ).order_by('-date_created')[:100]
        messages = []
        limit = limit / user.sender.count()
        for sender in user.sender.all():
            for m in sender.messenger.all().order_by('-date_created')[:limit]:
                messages.append(m)

    return render(
        request, 'apps/sms/home.html', {'messages': messages,'bulk':bulk}
    )


@csrf_exempt
@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
def get_sender(request):

    results = {'sender':'','student_number':'','message':""}
    if request.method=='POST':
        phone = request.POST.get('phone_to')
        if phone:
            sids = []
            for s in request.user.sender.all():
                sids.append(s.id)
            messages = Message.objects.filter(recipient=phone).filter(
                messenger__id__in=sids
            ).order_by('-date_created')
            if messages:
                message = messages[0]
                results['sender'] = '{}'.format(message.messenger.id)
                results['student_number'] = '{}'.format(
                    message.student_number
                )
                msg = "Success"
            else:
                msg = "No phone number provided."
        else:
            msg = "No phone number provided."
    else:
        # requires POST
        msg = "Method must be POST."

    results['message'] = msg
    return HttpResponse(
        json.dumps(results), content_type='application/json; charset=utf-8'
    )


@csrf_exempt
def reply_callback(request):
    if request.method=='POST':
        post = request.POST
        if settings.DEBUG:
            logger.debug('MessageSid: {}'.format(post.get('MessageSid')))
            logger.debug('SmsSid: {}'.format(post.get('SmsSid')))
            logger.debug('AccountSid: {}'.format(post.get('AccountSid')))
            logger.debug('MessagingServiceSid: {}'.format(post.get('MessagingServiceSid')))
            logger.debug('From: {}'.format(post.get('From')))
            logger.debug('To: {}'.format(post.get('To')))
            logger.debug('Body: {}'.format(post.get('Body')))
            logger.debug('NumMedia: {}'.format(post.get('NumMedia')))
            logger.debug('FromCity: {}'.format(post.get('FromCity')))
            logger.debug('FromState: {}'.format(post.get('FromState')))
            logger.debug('FromZip: {}'.format(post.get('FromZip')))
            logger.debug('FromCountry: {}'.format(post.get('FromCountry')))
            logger.debug('ToCity: {}'.format(post.get('ToCity')))
            logger.debug('ToState: {}'.format(post.get('ToState')))
            logger.debug('ToZip: {}'.format(post.get('ToZip')))
            logger.debug('ToCountry: {}'.format(post.get('ToCountry')))
            #logger.debug(': {}'.format(post.get('')))
        else:
            try:
                where = post.get('MessagingServiceSid')
                if where:
                    sender = Sender.objects.get(messaging_service_sid=where)
                else:
                    where = post.get('To')
                    sender = Sender.objects.get(phone=where)
                to = sender.user.email
                m = Message.objects.filter(recipient=post.get('To')).order_by(
                    '-date_created').first()
                status = Status(
                )
                reply = Message(
                    messenger=sender, recipient=post.get('To'),
                    student_number=m.student_number, body=post.get('Body'),
                )
            except:
                to = [settings.MANAGERS[0][1],]
            subject = "[DJ Twilio] reply from one your contacts"
            send_mail(
                request, to, subject, settings.DEFAULT_FROM_EMAIL,
                template, post, [settings.MANAGERS[0][1],]
            )

        frum = post.get('From')
        session = request.session
        logger.debug("session = {}".format(session.__dict__))
        logger.debug("frum = {}".format(frum))
        convo = session.get(frum, 0)
        convo += 1
        session[frum] = convo
        logger.debug("session[frum] = {}".format(session[frum]))
        msg = """"
            We have sent an email to the original sender with your message.
            They will respond to you presently.
        """
    else:
        # requires POST
        msg = "Requires POST"

    return HttpResponse(
        msg, content_type='text/plain; charset=utf-8'
    )


@csrf_exempt
def status_callback(request, mid=None):
    """
    see: https://www.twilio.com/docs/sms/twiml#request-parameters
    """
    if request.method=='POST':
        msg = ""
        post = request.POST
        try:
            if mid:
                cipher = AESCipher(bs=16)
                mid = cipher.decrypt(mid)
                message = Message.objects.get(pk=mid)
                status = message.status
            else:
                status = None
                # callback from the API when recipient has replied to an SMS
                try:
                    # remove extraneous characters and country code for US
                    frum = str(post.get('From')).translate(None, '.+()- ')[1:]
                    recipient = str(post.get('To')).translate(None, '.+()- ')
                    logger.debug('frum: {}'.format(frum))
                    # default sender
                    where = post.get('MessagingServiceSid')
                    if where:
                        sender = Sender.objects.get(messaging_service_sid=where)
                    else:
                        where = recipient
                        sender = Sender.objects.get(phone=where)
                    email_to = sender.user.email
                    m = Message.objects.filter(recipient=frum).order_by(
                        '-date_created'
                    ).first()
                    message = Message(
                        messenger=sender, recipient=recipient,
                        student_number=m.student_number, body=post.get('Body')
                    )
                    message.save()
                except Exception, e:
                    logger.debug('call back child exception: {}'.format(str(e)))
                    email_to = [settings.MANAGERS[0][1],]

                if settings.DEBUG:
                    email_to = [settings.MANAGERS[0][1],]

                subject = "[DJ Twilio] reply from one your contacts"
                send_mail(
                    request, email_to, subject, settings.DEFAULT_FROM_EMAIL,
                    "apps/sms/reply_email.html", post, [settings.MANAGERS[0][1],]
                )

            if message:
                form = StatusCallbackForm(post, instance=status)
                if form.is_valid():
                    status = form.save(commit=False)
                    if status.ErrorCode:
                        error = Error.objects.get(code=status.ErrorCode)
                        status.error = error
                    status.save()
                    # if we do not have a message status, it is a reply
                    if not message.status:
                        status.MessageStatus = 'delivered'
                        message.status = status
                        msg = """"
                            We have sent an email to the original sender with
                            your message. They will respond to you presently.
                        """
                    # update informix
                    if status.MessageStatus == 'delivered':
                        # create the ctc_blob object with the value of
                        # the message body for txt
                        session = get_session(EARL)
                        # informix does not like unicode for their blob and
                        # it has to be a string, so here we deal with
                        # non-standar characters that do not work with
                        # python strings
                        body = unicodedata.normalize(
                            'NFKD', message.body
                        ).encode('ascii','ignore')
                        blob = CtcBlob(txt=body)
                        session.add(blob)
                        session.flush()

                        sql = '''
                            INSERT INTO ctc_rec (
                                id, tick, add_date, due_date, cmpl_date,
                                resrc, bctc_no, stat
                            )
                            VALUES (
                                {},"ADM",TODAY,TODAY,TODAY,"TEXTOUT",{},"C"
                            )
                        '''.format(
                                message.student_number, blob.bctc_no
                        )

                        session.execute(sql)
                        session.commit()
                        session.close()
                        if not msg:
                            if settings.DEBUG:
                                msg = status.MessageStatus
                            else:
                                logger.debug("msg = {}".format(msg))
                else:
                    if settings.DEBUG:
                        msg = "Invalid POST data"
                    else:
                        logger.debug("msg = {}".format(msg))
            else:
                if settings.DEBUG:
                    msg = "No message found for status callback or reply callback"
                else:
                    logger.debug("msg = {}".format(msg))
        except Exception, e:
            logger.debug('call back parent exception: {}'.format(str(e)))
            if settings.DEBUG:
                msg = "No message mataching message ID"
    else:
        if settings.DEBUG:
            msg = "Requires POST"
        else:
            logger.debug("msg = {}".format(msg))

    return HttpResponse(
        msg, content_type='text/plain; charset=utf-8'
    )


@portal_auth_required(
    session_var='DJTWILIO_AUTH', redirect_url=reverse_lazy('access_denied')
)
@csrf_exempt
def send_form(request):

    bulk = False
    response = False
    template = 'apps/sms/form.html'
    user = request.user

    if request.method=='POST':
        form_indi = IndiForm(
            request.POST, request=request, prefix='indi', use_required_attribute=False
        )
        form_bulk = BulkForm(
            request.POST, request.FILES, prefix='bulk', use_required_attribute=False
        )
        if user.is_superuser:
            sids = Sender.objects.filter(messaging_service_sid__isnull=False)
        else:
            sids = user.sender.filter(messaging_service_sid__isnull=False)
        form_bulk.fields['sender'].queryset = sids
        if request.POST.get('bulk-submit'):
            bulk = True
            if form_bulk.is_valid():
                data = form_bulk.cleaned_data
                bulk = form_bulk.save()
                with open(bulk.distribution.path, 'rb') as f:
                    reader = csv.reader(f, delimiter='\t', quoting=csv.QUOTE_NONE)
                    for r in reader:
                        sent = send_message(
                            Client(bulk.sender.account.sid, bulk.sender.account.token),
                            bulk.sender, r[2], data['message'], r[3], bulk=bulk
                        )
                messages.add_message(
                    request, messages.SUCCESS, """
                        Your messages have been sent. View the
                        <a href="{}" class="message-status text-primary">
                        delivery report</a>.
                    """.format(reverse('sms_bulk_detail', args=[bulk.id])),
                    extra_tags='alert alert-success'
                )
                response = HttpResponseRedirect( reverse('sms_send_form') )
        else:
            if form_indi.is_valid():
                data = form_indi.cleaned_data
                sender = Sender.objects.get(pk=data['phone_from'])
                body = data['message']
                recipient = data['phone_to']
                sent = send_message(
                    Client(sender.account.sid, sender.account.token),
                    sender, recipient, body, data.get('student_number')
                )
                if sent['message']:

                    convo = session.get(recipient, 0)
                    convo += 1
                    session[recipient] = convo

                    messages.add_message(
                        request, messages.SUCCESS, """
                          {}) Your message has been sent. View the
                          <a data-target="#messageStatus" data-toggle="modal"
                          data-load-url="{}" class="message-status text-primary">
                          message status</a>.
                        """.format(
                            reverse(
                                convo, 'sms_detail', args=[
                                    sent['message'].status.MessageSid,'modal'
                                ]
                            )
                        ), extra_tags='alert alert-success'
                    )
                else:
                    messages.add_message(
                        request, messages.ERROR, sent['response'],
                        extra_tags='alert alert-danger'
                    )

                response = HttpResponseRedirect(
                    reverse('sms_send_form')
                )
    else:
        form_bulk = BulkForm( prefix='bulk', use_required_attribute=False )
        form_indi = IndiForm(
            prefix='indi', request=request, use_required_attribute=False
        )

        if user.is_superuser:
            sids = Sender.objects.filter(messaging_service_sid__isnull=False)
        else:
            sids = user.sender.filter(messaging_service_sid__isnull=False)
        form_bulk.fields['sender'].queryset = sids

    if not response:
        response = render(
            request, template, {
                'form_indi': form_indi, 'form_bulk': form_bulk, 'bulk': bulk
            }
        )

    return response


def search(request):
    return render(
        request, 'apps/sms/search.html'
    )
