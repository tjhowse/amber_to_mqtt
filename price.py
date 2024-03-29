#!/usr/bin/python3
from time import sleep, time
from datetime import datetime, timedelta
import json
import logging
import paho.mqtt.client as mqtt
try:
    # This hack means I don't have to risk checking my actual secrets into source control
    from secrets_real import *
except ImportError:
    from secrets import *

import amberelectric
from amberelectric.api import amber_api

BID_INTERVAL_MINUTES = 5
TARIFF_INTERVAL_MINUTES = 30
class amber_to_mqtt():
    api_lag_allowance_s = 10 # Wait this many seconds after the period start before polling for the value
    sleep_interval_s = 30

    def __init__(self, postcode=POSTCODE):
        self.last_final_report_time = 0
        self.connect_amber()

    def connect_amber(self):
        configuration = amberelectric.Configuration(
            access_token = AMBER_API_KEY
        )
        self.amber = amber_api.AmberApi.create(configuration)

    def connect(self):
        try:
            self.sites = self.amber.get_sites()
        except Exception as e:
            logging.error("Error getting sites from Amber API: {}".format(str(e)))
            return False
        self.client = mqtt.Client()
        self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message
        self.client.connect(MQTT_HOSTNAME, MQTT_PORT, 60)
        self.client.loop_start()
        return True

    def on_connect(self, client, userdata, flags, rc):
        logging.error("Connected to MQTT")
    def on_disconnect(self, client, userdata, rc):
        logging.error("Disconnected from MQTT")
    def on_message(self, client, userdata, msg):
        logging.error("Got message: {}".format(msg))

    def publish_realtime_values(self):
        # This pulls the latest numbers from the API and publishes them to MQTT.
        intervals = self.amber.get_current_price(self.sites[0].id, resolution = 5)
        logging.info(intervals)
        import_price, export_price = None,None
        try:
            for interval in intervals:
                if interval.channel_type == amberelectric.model.channel.ChannelType.GENERAL:
                    import_price = interval.per_kwh
                elif interval.channel_type == amberelectric.model.channel.ChannelType.FEED_IN:
                    export_price = interval.per_kwh
        except Exception as e:
            logging.error("Error getting prices: {}".format(str(e)))

        if import_price is not None:
            self.client.publish(MQTT_TOPIC_PREFIX+"/import/5m_bid", import_price/100)
            self.client.publish(MQTT_TOPIC_PREFIX+"/export/5m_bid", -export_price/100)
            self.client.publish(MQTT_TOPIC_PREFIX+"/import/5m_bid_raw", intervals[0].spot_per_kwh)
        # else:
        #     raise ValueError("No 5m data available.")

    def loop_forever(self):
        while True:
            self.publish_realtime_values()
            sleep(self.sleep_interval_s)

if __name__ == "__main__":
    # Set logger to include an ISO8601 timestamp
    logging.basicConfig(format='%(asctime)s %(message)s', level=logging.INFO)
    relay = amber_to_mqtt()
    relay.connect()
    relay.loop_forever()
# while True:
#     try:
#         relay = amber_to_mqtt()
#         relay.connect()
#         relay.loop_forever()
#     except Exception as e:
#         logging.error("Whoopsie! Restarting. Error: {}".format(str(e)))
#         sleep(5)
    # a = amber_api(POSTCODE)
    # a.poll()
    # logging.error(a.get_5m_import_bid_price())
    # logging.error(a.get_30m_import_price())
