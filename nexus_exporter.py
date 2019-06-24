#!/usr/bin/env python

import os
import json
import time
import requests
try:
    import urllib2
    from urlparse import urlparse
    from urllib2 import URLError, HTTPError
except ImportError:
    # Python 3
    import urllib.request as urllib2
    from urllib.parse import urlparse
    from urllib.error import URLError, HTTPError
from prometheus_client import start_http_server
from prometheus_client.core import GaugeMetricFamily, REGISTRY
import argparse


def valid_url(string):
    """Validate url input argument.
    Takes a string. Return valid url or raise URLError.
    """
    try:
        if not getattr(urlparse(string), "scheme") or \
                not getattr(urlparse(string), "netloc"):
            raise URLError("""Invalid URL: %s.
                        Don't forget including the scheme (usually http)
                        Example: http://localhost:8081""" % string)
        return string
    except AttributeError:
        raise URLError("""Invalid URL: %s.
                       Don't forget including the scheme (usually http)
                       Example: http://localhost:8081""" % string)


def parse():
    parser = argparse.ArgumentParser(
        description='Export Prometheus metrics for Sonatype Nexus > 3.6')
    parser.add_argument(
        '--host', metavar='HOST',
        type=valid_url,
        help='address with port where Nexus is available. Defaults to\
        http://localhost:8081',
        default=os.environ.get("NEXUS_HOST", "http://localhost:8081")
    )
    parser.add_argument(
        "--password", "-p", help="admin password",
        default=os.environ.get("NEXUS_ADMIN_PASSWORD", "admin123")
    )
    parser.add_argument(
        "--user", "-u", help="Nexus user name, defaults to admin",
        default=os.environ.get("NEXUS_USERNAME", "admin")
    )
    return parser.parse_args()


class NexusCollector(object):
    def __init__(self, target, user, password):
        self._target = target.rstrip("/")
        self._auth = (user, password)

    def collect(self):
        data = self._request_data()

        run_time = data['system-runtime']
        yield GaugeMetricFamily('nexus_processors_available',
            'Available Processors', value=run_time['availableProcessors'])
        yield GaugeMetricFamily('nexus_free_memory_bytes',
            'Free Memory (bytes)', value=run_time['freeMemory'])
        yield GaugeMetricFamily('nexus_total_memory_bytes',
            'Total Memory (bytes)', value=run_time['totalMemory'])
        yield GaugeMetricFamily('nexus_max_memory_bytes',
            'Max Memory (bytes)', value=run_time['maxMemory'])
        yield GaugeMetricFamily('nexus_threads_used',
            'Threads Used', value=run_time['threads'])

        print(data['system-filestores'])
        for fsname, details in data['system-filestores'].items():

            mount = self._mount_point(details['description'])
            fts = GaugeMetricFamily(
                'nexus_filestore_total_space_bytes',
                'Total Filestore Space (%s)' % details['description'],
                labels=["mount_point", "fsname", "fstype", "readonly"])
            fts.add_metric(
                [mount, fsname, details['type'],
                 str(details['readOnly'])], details['totalSpace'])
            yield fts
            fus = GaugeMetricFamily(
                'nexus_filestore_usable_space_bytes',
                'Usable Filestore Space (%s)' % details['description'],
                labels=["mount_point", "fsname", "fstype", "readonly"])
            fus.add_metric(
                [mount, fsname, details['type'],
                 str(details['readOnly'])], details['usableSpace'])
            yield fus
            fas = GaugeMetricFamily(
                'nexus_filestore_unallocated_space_bytes',
                'Unallocated Filestore Space (%s)' % details['description'],
                labels=["mount_point", "fsname", "fstype", "readonly"])
            fas.add_metric(
                [mount, fsname, details['type'],
                 str(details['readOnly'])], details['unallocatedSpace'])
            yield fas

        gauges = data['gauges']
        yield GaugeMetricFamily('nexus_jvm_memory_heap_committed_bytes',
            '', value=gauges['jvm.memory.heap.committed']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_heap_init_bytes',
            '', value=gauges['jvm.memory.heap.init']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_heap_max_bytes',
            '', value=gauges['jvm.memory.heap.max']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_heap_used_bytes',
            '', value=gauges['jvm.memory.heap.used']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_nonheap_committed_bytes',
            '', value=gauges['jvm.memory.non-heap.committed']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_nonheap_init_bytes',
            '', value=gauges['jvm.memory.non-heap.init']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_nonheap_max_bytes',
            '', value=gauges['jvm.memory.non-heap.max']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_nonheap_used_bytes',
            '', value=gauges['jvm.memory.non-heap.used']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_total_committed_bytes',
            '', value=gauges['jvm.memory.total.committed']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_total_init_bytes',
            '', value=gauges['jvm.memory.total.init']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_total_max_bytes',
            '', value=gauges['jvm.memory.total.max']['value'])
        yield GaugeMetricFamily('nexus_jvm_memory_total_used_bytes',
            '', value=gauges['jvm.memory.total.used']['value'])
        yield GaugeMetricFamily('nexus_jvm_uptime_seconds',
            '', value=gauges['jvm.vm.uptime']['value']/1000.0)

        metrics = data['meters']
        et = GaugeMetricFamily('nexus_events_total', 'Nexus Events Count', labels=['level'])
        et.add_metric(['trace'], metrics['metrics.trace']['count'])
        et.add_metric(['debug'], metrics['metrics.debug']['count'])
        et.add_metric(['info'], metrics['metrics.info']['count'])
        et.add_metric(['warn'], metrics['metrics.warn']['count'])
        et.add_metric(['error'], metrics['metrics.error']['count'])
        yield et

        hr = GaugeMetricFamily(
            'nexus_webapp_http_response_total',
            'Nexus Webapp HTTP Response Count', labels=['code'])
        hr.add_metric(['1xx'],
            metrics['org.eclipse.jetty.webapp.WebAppContext.1xx-responses']['count'])
        hr.add_metric(['2xx'],
            metrics['org.eclipse.jetty.webapp.WebAppContext.2xx-responses']['count'])
        hr.add_metric(['3xx'],
            metrics['org.eclipse.jetty.webapp.WebAppContext.3xx-responses']['count'])
        hr.add_metric(['4xx'],
            metrics['org.eclipse.jetty.webapp.WebAppContext.4xx-responses']['count'])
        hr.add_metric(['5xx'],
            metrics['org.eclipse.jetty.webapp.WebAppContext.5xx-responses']['count'])
        yield hr

        timers = data['timers']
        hq = GaugeMetricFamily('nexus_webapp_http_request_total',
            'Nexus Webapp HTTP Request Count', labels=['method'])
        hq.add_metric(['connect'],
            timers['org.eclipse.jetty.webapp.WebAppContext.connect-requests']['count'])
        hq.add_metric(['delete'],
            timers['org.eclipse.jetty.webapp.WebAppContext.delete-requests']['count'])
        hq.add_metric(['get'],
            timers['org.eclipse.jetty.webapp.WebAppContext.get-requests']['count'])
        hq.add_metric(['head'],
            timers['org.eclipse.jetty.webapp.WebAppContext.head-requests']['count'])
        hq.add_metric(['move'],
            timers['org.eclipse.jetty.webapp.WebAppContext.move-requests']['count'])
        hq.add_metric(['options'],
            timers['org.eclipse.jetty.webapp.WebAppContext.options-requests']['count'])
        hq.add_metric(['other'],
            timers['org.eclipse.jetty.webapp.WebAppContext.other-requests']['count'])
        hq.add_metric(['post'],
            timers['org.eclipse.jetty.webapp.WebAppContext.post-requests']['count'])
        hq.add_metric(['put'],
            timers['org.eclipse.jetty.webapp.WebAppContext.put-requests']['count'])
        hq.add_metric(['trace'],
            timers['org.eclipse.jetty.webapp.WebAppContext.trace-requests']['count'])
        yield hq

    def _mount_point(self, description):
        return description.split('(')[0].strip()

    def _request_data(self):
        url = "{0}/service/rest/atlas/system-information".format(self._target)
        result = requests.get(url, auth=self._auth)
        url = "{0}/service/metrics/data".format(self._target)
        result2 = requests.get(url, auth=self._auth)
        result.raise_for_status()
        result2.raise_for_status()
        print(result2.text)
        data = result.json()
        data['gauges'] = result2.json()['gauges']
        data['meters'] = result2.json()['meters']
        data['timers'] = result2.json()['timers']
        return data

def fatal(msg):
    print(msg)
    os._exit(1)  # hard exit without throwing exception

if __name__ == "__main__":
    print("starting...")
    args = parse()
    REGISTRY.register(NexusCollector(args.host, args.user, args.password))
    start_http_server(9184)
    while True:
        time.sleep(1)
