# Amber to MQTT relay

This is some basic glue that connects to [Amber Electric](https://www.amberelectric.com.au/)'s
realtime wholesale electricity pricing API. It pulls out some stats, does some calculations
and publishes the result to an MQTT server for integration with home automation systems.

The API is not ready for general consumption, I've kindly been given access for experimentation,
but you may have success in contacting their support folk and asking nicely.

## Purpose
The goal of this interface is to enable smarter decisions on domestic power usage in order to minimise
power bills and benefit the environment. I can selectively charge up my home battery storage and hot
water systems while electricity is cheap/free/negative and avoid drawing from the grid when the prices
are high.