# -*- coding: utf-8 -*-
from django import forms

from djtwilio.core.models import Account, Sender

from localflavor.us.forms import USPhoneNumberField, USZipCodeField


class StudentNumberForm(forms.Form):

    student_number = forms.IntegerField(
        label = "Student ID",
        widget=forms.TextInput(attrs={'placeholder': 'Student ID'})
    )


class SenderForm(forms.ModelForm):

    phone = USPhoneNumberField(
        label = "Phone number",
        help_text = "Format: XXX XXX XXXX"
    )
    messaging_service_sid = forms.CharField(
        label = "Messaging service ID",
        max_length = 34,
        help_text = """
            A 34 character code that is associated with the phone number
        """
    )
    account = forms.ModelChoiceField(
        label = "Account",
        queryset = Account.objects.all(),
        required = True
    )
    nickname = forms.CharField(
        label = "Nickname",
        required = True
    )

    class Meta:
        model = Sender
        exclude = ('user',)

    def clean_messaging_service_sid(self):

        sid = self.cleaned_data.get('messaging_service_sid')
        if sid and len(sid) < 34:
            self._errors['messaging_service_sid'] = self.error_class(
                ["Messaging Services SID is 34 characters."]
            )

        return sid

    def clean(self):
        cd = self.cleaned_data
        if not cd.get('phone') or not cd.get('messaging_service_sid'):
            self._errors['messaging_service_sid'] = self.error_class(
                ["Provide either a phone or a service SID."]
            )
            self._errors['phone'] = self.error_class(
                ["Provide either a phone or a service SID."]
            )
