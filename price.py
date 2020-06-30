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

BID_INTERVAL_MINUTES = 5
TARIFF_INTERVAL_MINUTES = 30

class amber_api():

    def __init__(self, postcode):
        self.raw_data = {}
        self.postcode = postcode
        self.last_poll_time = datetime.min

    def poll(self, force=False):
        # Grabs data and populates raw_data, static_import_prices, static_output_prices and prices.
        if ((datetime.now() - self.last_poll_time).seconds/60) < BID_INTERVAL_MINUTES and not force:
            return
        self.last_poll_time = datetime.now()
        data = {}
        data['postcode'] = self.postcode
        data = requests.post(API_URI, data=json.dumps(data))
        data.raise_for_status()
        self.raw_data = json.loads(data.text)['data']
        self.static_import_prices = self.raw_data['staticPrices']['E1']
        self.static_export_prices = self.raw_data['staticPrices']['B1']
        self.prices = self.raw_data['variablePricesAndRenewables']

    def calc_import_price(self, record):
        # Returns the price of importing power from the grid in $/kWh
        return (float(self.static_import_prices['totalfixedKWHPrice']) + \
                float(self.static_import_prices['lossFactor']) * float(record['wholesaleKWHPrice']))/100

    def calc_export_price(self, record):
        # Returns the price of exporting power to the grid in $/kWh
        return (float(self.static_export_prices['totalfixedKWHPrice']) - \
                float(self.static_export_prices['lossFactor']) * float(record['wholesaleKWHPrice']))/100

    def get_5m_period(self):
        # Returns the whole contents of the 5MIN record, or None if there isn't one
        self.poll()
        record = [record for record in self.prices if record['periodSource'] == "5MIN"]
        if not record:
            return None
        return record[0]

    def get_30m_period(self):
        # Returns the most recent 30 minute record.
        self.poll()
        return [record for record in self.prices if record['periodSource'] == "30MIN" and record['periodType'] == "ACTUAL"][-1]

    def get_5m_bid_prices(self):
        # Returns the real $/kWH bid used to determine the price of importing power for the current 30m period
        # and the export price
        # and the raw wholesaleKWHPrice
        d = self.get_5m_period()
        if not d:
            return (None, None, None)
        return (self.calc_import_price(d), self.calc_export_price(d), d['wholesaleKWHPrice'])

    def get_30m_prices(self):
        # Returns the real $/kWH for importing power from the grid for the most recent 30m period
        # and the export price
        # and the raw wholesaleKWHPrice
        d = self.get_30m_period()
        if not d:
            return (None, None, None)
        return (self.calc_import_price(d), self.calc_export_price(d), d['wholesaleKWHPrice'])

class amber_to_mqtt():
    api_lag_allowance_s = 10 # Wait this many seconds after the period start before polling for the value
    sleep_interval_s = 10

    def __init__(self, postcode=POSTCODE):
        self.last_final_report_time = 0
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

    def publish_5m_values(self):
        # This pulls the latest numbers from the API and publishes them to MQTT.
        import_price, export_price, raw = self.amber.get_5m_bid_prices()
        if import_price is not None:
            self.client.publish(MQTT_TOPIC_PREFIX+"/import/5m_bid", import_price)
            self.client.publish(MQTT_TOPIC_PREFIX+"/export/5m_bid", export_price)
            self.client.publish(MQTT_TOPIC_PREFIX+"/import/5m_bid_raw", raw)

    def publish_30m_values(self):
        import_price, export_price, raw = self.amber.get_30m_prices()
        self.client.publish(MQTT_TOPIC_PREFIX+"/import/30m", import_price)
        self.client.publish(MQTT_TOPIC_PREFIX+"/export/30m", export_price)
        self.client.publish(MQTT_TOPIC_PREFIX+"/import/30m_raw", raw)

    def calc_next_report_time(self, minutes):
        # Returns a time around minutes in the future that is divisible by minutes
        report_time = datetime.now()
        report_time = report_time.replace(second = self.api_lag_allowance_s, microsecond = 0)
        report_time += timedelta(minutes = minutes)
        return report_time.replace(minute = minutes*(round(report_time.minute/minutes)))

    def loop_forever(self):
        # This blocks forever, polling and reporting new values every 5/30 minutes.
        self.publish_5m_values()
        self.publish_30m_values()
        self.shedule_5m_report_time = self.calc_next_report_time(BID_INTERVAL_MINUTES)
        self.shedule_30m_report_time = self.calc_next_report_time(TARIFF_INTERVAL_MINUTES)
        while True:
            if datetime.now() >= self.shedule_5m_report_time:
                self.shedule_5m_report_time = self.calc_next_report_time(BID_INTERVAL_MINUTES)
                self.publish_5m_values()
            if datetime.now() >= self.shedule_30m_report_time:
                self.shedule_30m_report_time = self.calc_next_report_time(TARIFF_INTERVAL_MINUTES)
                self.publish_30m_values()
            sleep(self.sleep_interval_s)

if __name__ == "__main__":
    relay = amber_to_mqtt()
    relay.connect()
    relay.loop_forever()
    # a = amber_api(POSTCODE)
    # a.poll()
    # print(a.get_5m_import_bid_price())
    # print(a.get_30m_import_price())