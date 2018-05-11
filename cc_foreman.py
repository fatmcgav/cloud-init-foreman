# vi: ts=4 expandtab
#
#    Copyright (C) 2012 CERN
#
#    Author: Tomas Karasek <tomas.karasek@cern.ch>
#    Modified: Gavin Williams <gavin.williams@weareact.com>
#
#    This program is free software: you can redistribute it and/or modify
#    it under the terms of the GNU General Public License version 3, as
#    published by the Free Software Foundation.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU General Public License for more details.
#
#    You should have received a copy of the GNU General Public License
#    along with this program.  If not, see <http://www.gnu.org/licenses/>.

import base64
import json
import os
import urllib2
import urllib

from cloudinit import helpers
from cloudinit import util

def getEnv():
    env = os.environ
    # Check if Puppet PC1 directory on PATH
    if 'puppetlabs' not in env["PATH"]:
        env["PATH"] = env["PATH"] + ":/opt/puppetlabs/bin"
    return env

def getFacterFact(factname, outputType=None):
    command = "facter %s" % factname

    if outputType:
        command += " %s" % outputType

    try:
        (facter_out, facter_err) = util.subp(command, shell=True, env=getEnv())
        if facter_err:
            raise Exception("facter returned an error when querying for %s: %s" % factname, string)
        output = facter_out.strip()
        if not output:
            raise Exception("facter did not return anything for %s" % factname)
        return output
    except util.ProcessExecutionError as e:
        raise Exception("facter execution failed: %s" % e)
    return false

class ForemanAdapter:
    mandatory_fields = ['server', 'hostgroup', 'login', 'password']

    def __init__(self, log, user_data):
        self.log = log
        log.debug("Got to ForemanAdapter.init")
        facter_os = json.loads(getFacterFact("os", outputType="--json"))['os']
        log.debug("Facter_os is a %s, looks like: %s", type(facter_os), facter_os)
        fq_os = "%s %s" % (facter_os['name'], facter_os['release']['full'])
        log.debug("Fq_os = %s", fq_os)

        log.debug("Setting defaults...")
        self.defaults = {
            "architecture": getFacterFact("architecture"),
        #    "model" : "Virtual Machine",
            "operatingsystem": fq_os,
            "environment": "production",
            "domain": getFacterFact("domain"),
        #    "ptable": "RedHat default",
        }
        log.debug("Set defaults")

        self.user_data = user_data
        for field in self.mandatory_fields:
            if field not in self.user_data:
                raise Exception(("%s must be supplied in [puppet] "
                                 " section in userdata." % field))
        log.debug("All mandatory fields present")
        self.login = self.user_data.pop("login")
        self.password = self.user_data.pop("password")

    def makeRequest(self, url, data=None, headers={}, request_type="GET", allowed_responses=[], auth=True):
        log = self.log
        log.debug("Got to makeRequest for URL: %s. Data = %s, Headers = %s, Allowed_responses = %s" % (url, data, headers, allowed_responses))

        if request_type == 'POST':
            data = json.dumps(data)

        if request_type == "GET" and data is not None:
            url_suffix = "?" + urllib.urlencode(data)
            url = url + url_suffix
            data = None

        log.debug("Final URL = %s", url)

        req = urllib2.Request(url, data=data, headers=headers)
        req.get_method = lambda: request_type

        if auth:
            auth_string = base64.encodestring("%s:%s" % (self.login, self.password))
            auth_string = auth_string.strip()
            auth_header = "Basic %s" % auth_string

            # Add header to request
            req.add_header('Authorization', auth_header)

        try:
            out = urllib2.urlopen(req)
        except urllib2.HTTPError as e:
            if e.code in allowed_responses:
                log.debug("Response code %s is in allowed_responses list", e.code)
                return e
            else:
                log.warn("Error encountered opening URL '%s': %s", url, e)
                raise Exception(("Error encountered opening URL '%s': %s" % (url, e)))
        else:
            log.debug("Request completed successfully")
            return out

    def foremanRequest(self, resource, request_type, data=None):
        log = self.log
        log.debug("Got to foremanRequest. Resource = %s, request_type = %s, data = %s", resource, request_type, data)

        headers = {"Content-Type": "application/json",
                   "Accept": "application/json"}

        url = self.user_data['server'] + "/api/" +  resource
        return json.loads(self.makeRequest(url, data=data, headers=headers, request_type=request_type).read())

    def registerToForeman(self):
        log = self.log
        log.debug("Got to registerToForeman.")
        host_dict = {}
        host_dict['hostgroup_id'] = self.getMetafieldID(
            "hostgroup", self.user_data['hostgroup'])

        for field in self.defaults.keys():
            value = self.user_data.get(field, self.defaults[field])
            host_dict[field + "_id"] = self.getMetafieldID(field, value)

        host_dict['name'] = getFacterFact("fqdn")
        host_dict['ip'] = getFacterFact("ipaddress")
        host_dict['mac'] = getFacterFact("macaddress").lower()

        log.debug("Checking for duplicate hosts using values: %s", host_dict)
        self.checkForDuplicates(host_dict)
        log.debug("No duplicates found, creating host...")

        # Host needs to be marked as Building
        host_dict['build'] = True

        newhost_dict = self.foremanRequest(resource = "hosts",
                                           request_type = "POST",
                                           data = {"host": host_dict})
        log.info("New host created with ID: %s", newhost_dict["id"])
        return newhost_dict["id"]

    def hostExists(self, hostname):
        log = self.log
        url = "%s/api/hosts/%s" % (self.user_data['server'], hostname)
        response = self.makeRequest(url, allowed_responses=[200,404])
        log.debug("Response code = %s, Body looks like: %s" % (response.getcode(), response.read()))
        if response.getcode() == 200:
            log.debug("Matching host already exists.")
            return True
        elif response.getcode() == 404:
            log.debug("No matching host found.")
            return False
        else:
            log.debug("Unexpected code returned. Raising exception.")
            raise Exception("Unexpected response received when checking if host exists. Code: %s, Body: %s" % (response.getcode(), response.read()))

    def checkForDuplicates(self, host_dict):
        log = self.log
        hostname = host_dict["name"]
        if not hostname.strip():
            raise Exception("Invalid hostname to check")
        log.debug("Looking for hostname matching '%s'", hostname)
        # if given hostname already exists, delete the old record
        # maybe update would be better?
        if self.hostExists(hostname):
            log.warn("deleting %s from foreman" % hostname)
            d = self.foremanRequest(resource="hosts/" + hostname,
                request_type="DELETE")

        for field in ['ip', 'mac']:
            log.debug("Checking for hosts with matching %s", field)
            matching_hosts = self.foremanRequest(
                resource = "hosts",
                request_type="GET",
                data = {"search": "%s=%s" % (field, host_dict[field])}
            )
            log.debug("Matching hosts looks like: %s", matching_hosts)
            if matching_hosts and matching_hosts['results']:
                msg = ("Host with %s %s already exists: %s" %
                      (field, host_dict[field], matching_hosts))
                raise Exception(msg)

    def getMetafieldID(self, fieldname, fieldvalue):
        log = self.log
        log.debug("Got to getMetafieldID. Looking for field %s with value %s", fieldname, fieldvalue)
        get_data = {"search": fieldvalue}
        lookup_key = 'name'

        # operatinsystems can't be searched on foreman-side for some reason so
        # we need to list all entries and pick the matching one
        if fieldname in ["hostgroup", "operatingsystem"]:
            #get_data = {"search": ""}
            lookup_key = 'title'

        field_dict = self.foremanRequest(
            resource=fieldname + "s",
            request_type="GET",
            data=get_data)

        log.debug("Response from Foreman = %s", field_dict)

        for item in field_dict['results']:
            if item[lookup_key] == fieldvalue:
                log.debug("Got a match. ID = %i", int(item['id']))
                return int(item['id'])
        return None

    def runForemanFinishScript(self):
        log = self.log
        log.debug("Got to runForemanFinishScript")

        # Get finish script
        url = self.user_data['server'] + "/unattended/finish"
        log.debug("Requesting URL %s", url)
        response = self.makeRequest(url)
        log.debug("Response looks like: %s", response)
        finish_script = response.read()

        log.debug("Running finish script")
        try:
            (output, err) = util.subp(finish_script, shell=True)
            log.debug("Finish script run. Output = \n%s", output)
        except util.ProcessExecutionError as e:
            log.warn("Error encountered when running finish script: %s", e)
            raise Exception(("Error running finish script: %s" % e))

        log.debug("Marking host as built")
        url = self.user_data['server'] + "/unattended/built"
        log.debug("Opening URL %s", url)

        self.makeRequest(url)
        log.info("Host marked as successfully built.")

def handle(_name, cfg, cloud, log, _args):
    if 'foreman' not in cfg:
        return

    foreman_cfg = cfg['foreman']
    log.debug("Foreman_cfg looks like: %s", foreman_cfg)
    adapter = ForemanAdapter(log, foreman_cfg)
    log.debug("ForemanAdapter init completed...")
    newhost_id = adapter.registerToForeman()

    if foreman_cfg.get('runfinish', False):
        log.debug("Running Foreman finish script")
        adapter.runForemanFinishScript()

    log.info("cc_foreman complete...")

