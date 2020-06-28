#!/usr/bin/python3
from time import sleep, time
from datetime import datetime, timedelta
import requests
import json
import paho.mqtt.client as mqtt
try:
    # This hack means I don't have to risk checking my actual secrets into source control
    from secrets_real import *
except ImportError:
    from secrets import *

REPORT_INTERVAL_MINUTES = 5

class amber_api():

    def __init__(self, postcode):
        self.raw_data = {}
        self.postcode = postcode
        self.last_poll_time = datetime.min

    def poll(self, force=False):
        # Grabs data and populates self.raw_data
        if ((datetime.now() - self.last_poll_time).seconds/60) < REPORT_INTERVAL_MINUTES and not force:
            return
        self.last_poll_time = datetime.now()
        data = {}
        data['postcode'] = self.postcode
        data = requests.post(API_URI, data=json.dumps(data))
        data.raise_for_status()
        # print(data.text)
        self.raw_data = json.loads(data.text)['data']
        self.static_prices = self.raw_data['staticPrices']['E1']
        self.prices = self.raw_data['variablePricesAndRenewables']
        # for period in self.raw_data['variablePricesAndRenewables']:
        #     if period['periodType'] == 'ACTUAL':
        #         print('{}: {}, {}'.format(period['period'], round(float(period['wholesaleKWHPrice']),4), period['periodSource']))
        # print(self.raw_data)
        # print(self.raw_data['staticPrices'])
        # print(self.raw_data['staticPrices'].B1.totalfixedKWHPrice)

    def calc_import_price(self, record):
        return float(self.static_prices['totalfixedKWHPrice']) + \
                float(self.static_prices['lossFactor']) * float(record['wholesaleKWHPrice'])

    def get_5m_period(self):
        # Returns the whole contents of the 5MIN record, or None if there isn't one
        self.poll()
        record = [record for record in self.prices if record['periodSource'] == "5MIN"]
        if not record:
            return None
        return record[0]

    def get_30m_period(self):
        self.poll()
        return [record for record in self.prices if record['periodSource'] == "30MIN"][-1]

    def get_5m_bid_price(self):
        d = self.get_5m_period()
        if not d:
            return None
        return self.calc_import_price(d)

    def get_30m_price(self):
        d = self.get_30m_period()
        if not d:
            return None
        return self.calc_import_price(d)

    def get_usage_prices(self, period):
        return float(self.raw_data['staticPrices']['E1']['totalfixedKWHPrice']) + \
                float(self.raw_data['staticPrices']['E1']['lossFactor']) * \
                float(self.raw_data['variablePricesAndRenewables'][period]['wholesaleKWHPrice'])

    def get_export_to_grid_price(self, period):
        pass
        # return self.raw_data.staticPrices.B1.totalfixedKWHPrice - self.raw_data.staticPrices.B1.lossFactor * self.raw_data.variablePricesAndRenewables.[period].wholesaleKWHPrice

class amber_to_mqtt():
    api_lag_allowance_s = 10 # Wait this many seconds after the period start before polling for the value
    sleep_interval_s = 10

    def __init__(self, postcode=POSTCODE):
        self.last_report_time = 0
        self.amber = amber_api(postcode)

    def connect(self):
        self.client = mqtt.Client()
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect(MQTT_HOSTNAME, MQTT_PORT, 60)
        self.client.loop_start()

    def on_connect(self, client, userdata, flags, rc):
        print("Connected")
        self.client.publish("Borp", "dorp")

    def on_disconnect(self, client, userdata, flags, rc):
        print("Disconnected")

    def on_message(self, client, userdata, msg):
        print("Got message: {}".format(msg))

    def publish_values(self):
        # This pulls the latest numbers from the API and publishes them to MQTT.
        # self.amber.poll()
        # blah blah
        bid = self.amber.get_5m_bid_price()
        if bid is None:
            final = self.amber.get_30m_price()
            self.client.publish(MQTT_TOPIC_PREFIX+"/30minute_Price", final)
        else:
            self.client.publish(MQTT_TOPIC_PREFIX+"/5m_Price", bid)

    def calc_next_report_time(self):
        # Returns a time around REPORT_INTERVAL_MINUTES in the future that is divisible by REPORT_INTERVAL_MINUTES
        report_time = datetime.now()
        report_time = report_time.replace(second = self.api_lag_allowance_s, microsecond = 0)
        report_time += timedelta(minutes = REPORT_INTERVAL_MINUTES)
        return report_time.replace(minute = REPORT_INTERVAL_MINUTES*(round(report_time.minute/REPORT_INTERVAL_MINUTES)))

    def loop_forever(self):
        # This wakes every sleep_interval_s seconds to poll new values from the API, publish them to MQTT,
        # then goes back to sleep.
        self.publish_values()
        self.scheduled_report_time = self.calc_next_report_time()
        while True:
            while datetime.now() < self.scheduled_report_time:
                sleep(self.sleep_interval_s)
            self.scheduled_report_time = self.calc_next_report_time()
            self.publish_values()

relay = amber_to_mqtt()
relay.connect()
relay.loop_forever()
a = amber_api(POSTCODE)
a.poll()
print(a.get_5m_bid_price())
print(a.get_30m_price())