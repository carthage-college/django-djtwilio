from .local import *

#from djzbar.settings import INFORMIX_EARL_PROD as INFORMIX_EARL
from djzbar.settings import INFORMIX_EARL_TEST as INFORMIX_EARL

ALLOWED_HOSTS =  [
    'localhost','127.0.0.1','psm.carthage.edu','hygiea.carthage.edu',
    'www.carthage.edu'
]
#DEBUG = False
DEBUG = True
ROOT_URL = '/apps/twilio'
LOGIN_REDIRECT_URL = ROOT_URL
