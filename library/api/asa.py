#from library.database import *
#import library.neutron as neutronlib
import textwrap, json, sys
#import netaddr
import requests

def get_version(device_number):

    host = "10.4.130.105"
    uri = "/api/cli"

    data = { "commands": [ "sh ver" ] }

    r = requests.post('https://%s%s', data)
    print r.text



