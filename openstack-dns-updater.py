#!/usr/bin/env python

# OpenStack DNS Updater listens on the RabbitMQ message bus. Whenever an
# instance is created or deleted DNS updater creates or removes
# its DNS A record. The name of the instance is directly used as its FQDN.
# Hence instances in OpenStack should be named with their FQDN.
# The IP address stored in DNS is the IP address of the first network interface
# on the private network. You can easily change the script to store floating
# IP address in DNS instead.
#
# OpenStack DNS Updater works well on CentOS 7. You can copy it into your
# /usr/local/bin directory and run it as user "nova". See the accompanying
# systemd script. OpenStack DNS Updater logs into /var/log/nova/dns-updater.log
# by default.

import os
import json
import logging as log
import powerdns
import ipaddress
import configparser

from fqdn import FQDN
from subprocess import Popen, PIPE
from kombu import BrokerConnection
from kombu import Exchange
from kombu import Queue
from kombu.mixins import ConsumerMixin

config = configparser.ConfigParser()
config.read(os.environ['CONFIG_FILE'])

LOG_FILE = config['LOGGING']['LOG_FILE']
LOG_LEVEL = config['LOGGING']['LOG_LEVEL']

EXCHANGE_NAME = config['AMQP']['EXCHANGE_NAME']
ROUTING_KEY = config['AMQP']['ROUTING_KEY']
QUEUE_NAME = config['AMQP']['QUEUE_NAME']
EVENT_CREATE = config['AMQP']['EVENT_CREATE']
EVENT_DELETE = config['AMQP']['EVENT_DELETE']
BROKER_URI = config['AMQP']['BROKER_URI']

PDNS_API = config['POWERDNS']['PDNS_API']
PDNS_KEY = config['POWERDNS']['PDNS_KEY']

api_client = powerdns.PDNSApiClient(api_endpoint=PDNS_API, api_key=PDNS_KEY)
api = powerdns.PDNSEndpoint(api_client)

log.basicConfig(filename=LOG_FILE, level=getattr(logging, LOG_LEVEL),
    format='%(asctime)s %(message)s')

class DnsUpdater(ConsumerMixin):

    def __init__(self, connection):
        self.connection = connection
        return

    def get_consumers(self, consumer, channel):
        exchange = Exchange(EXCHANGE_NAME, type="topic", durable=False)
        queue = Queue(QUEUE_NAME, exchange, routing_key = ROUTING_KEY,
            durable=True, auto_delete=False, no_ack=True)
        return [ consumer(queue, callbacks = [ self.on_message ]) ]

    def on_message(self, body, message):
        try:
            self._handle_message(body)
        except Exception, e:
            log.info(repr(e))

    def _handle_message(self, body):
        log.debug('Body: %r' % body)
        jbody = json.loads(body["oslo.message"])
        event_type = jbody["event_type"]
        if event_type == EVENT_CREATE or event_type == EVENT_DELETE:
            instancename = jbody["payload"]["hostname"]
            fqdn = instancename + '.'
            if FQDN(str(fqdn)).is_valid:
                log.debug('FQDN is valide')
                suggested_zone = api.servers[0].suggest_zone(fqdn)
                zone = api.servers[0].get_zone(suggested_zone.name)
                hostname = fqdn.replace(zone.name, "")
                record = hostname[:-1]
                if event_type == EVENT_CREATE:
                    fixed_ips0 = jbody["payload"]["fixed_ips"][0]["address"]
                    fixed_ips1 = jbody["payload"]["fixed_ips"][1]["address"]
                    if ipaddress.IPv4Address(fixed_ips0):
                        ipv4addr = fixed_ips0
                        ipv6addr = fixed_ips1
                    else:
                        ipv4addr = fixed_ips1
                        ipv6addr = fixed_ips0
                    log.info("Adding {} {} {}".format(fqdn, ipv4addr, ipv6addr))
                    zone.create_records([
                        powerdns.RRSet(record, 'A', [(ipv4addr, False)]),
                        powerdns.RRSet(record, 'AAAA', [(ipv6addr, False)]),
                    ])
                if event_type == EVENT_DELETE:
                    log.info("Deleting {}".format(fqdn))
                    zone.delete_record([
                        powerdns.RRSet(record, 'A', []),
                        powerdns.RRSet(record, 'AAAA', []),
                    ])

if __name__ == "__main__":
    log.info("Connecting to broker {}".format(BROKER_URI))
    with BrokerConnection(BROKER_URI) as connection:
        DnsUpdater(connection).run()
