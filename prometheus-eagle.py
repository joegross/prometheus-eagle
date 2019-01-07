#!/usr/bin/env python3

import argparse
import logging
import sys
import time
from collections import defaultdict

import requests
from prometheus_client import Gauge, start_http_server

logger = logging.getLogger(__name__)

# defaults
LISTEN_PORT = 8002
EAGLE_HOST = 'eagle'
LOOP_SLEEP_TIME = 5  # seconds
METRIC_TTL = 5 * 60  # seconds

POST_BODY = """
<LocalCommand>
  <Name>get_usage_data</Name>
  <MacId>{mac}</MacId>
</LocalCommand>
<LocalCommand>
  <Name>get_price_blocks</Name>
  <MacId>{mac}</MacId>
</LocalCommand>
"""


class eagle_server(object):
    def __init__(self, user, password, eagle_host, sleep, port, mac):
        self.sleep = sleep
        self.user = user
        self.password = password
        self.eagle_host = eagle_host
        self.post_body = POST_BODY.format(mac=mac)
        self.last_seen = defaultdict(lambda: 0)
        start_http_server(port)
        self.demand = Gauge('demand', 'demand in Watts', ['host'])
        self.summation_delivered = Gauge(
            'summation_delivered', 'summation delivered in kWh', ['host'])
        self.eagle_last_seen = Gauge(
            'last_seen', 'last_seen', ['host'])

    def expire_sensors(self):
        for host in list(self.last_seen.keys()):
            age = time.time() - self.last_seen[host]
            if age > METRIC_TTL:
                logging.info(
                    'removing stale eagle: %s age: %s', host, age)
                self.demand.remove(host)
                self.summation_delivered.remove(host)
                self.eagle_last_seen.remove(host)
                del self.last_seen[host]

    def serve_forever(self):
        while True:
            try:
                r = requests.post(
                    'http://{eagle_host}/cgi-bin/cgi_manager'.format(
                        eagle_host=self.eagle_host),
                    auth=(self.user, self.password),
                    data=self.post_body
                )
            except:
                logging.warning(sys.exc_info())
            if r.ok:
                demand = float(r.json()['demand']) * 1000
                summation_delivered = r.json()['summation_delivered']
                logging.debug('demand: %s summation_delivered: %s',
                              demand, summation_delivered)
                self.demand.labels(host=self.eagle_host).set(demand)
                self.summation_delivered.labels(
                    host=self.eagle_host).set(summation_delivered)
                now = time.time()
                self.eagle_last_seen.labels(
                    host=self.eagle_host).set(now)
                self.last_seen[self.eagle_host] = now
                self.expire_sensors()

            logging.debug("sleeping %s...", self.sleep)
            time.sleep(self.sleep)


def init_logging(level=logging.INFO):
    logging.basicConfig(
        level=level, format='%(asctime)s %(name)-18s %(levelname)-8s %(message)s')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument('-e', '--eagle_host',
                        default=EAGLE_HOST, help='eagle URL')
    parser.add_argument('-u', '--user', help='username')
    parser.add_argument('-p', '--password', help='password')
    parser.add_argument('-v', '--verbose', action='store_true', help='verbose')
    parser.add_argument('-m', '--mac', help='device macid')
    parser.add_argument('--port', default=LISTEN_PORT, help='listen port')
    parser.add_argument('--sleep', default=LOOP_SLEEP_TIME, help='listen port')
    args = parser.parse_args()
    if args.verbose:
        init_logging(logging.DEBUG)
    else:
        init_logging(logging.INFO)
    eagle_server(user=args.user, password=args.password, eagle_host=args.eagle_host,
                 sleep=args.sleep, port=args.port, mac=args.mac).serve_forever()
