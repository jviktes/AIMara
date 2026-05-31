
import neopixel
from machine import Pin
from umqtt.simple import MQTTClient
import gc, time

print('Hello main')

# ── config ────────────────────────────
MQTT_BROKER = '192.168.0.136'   # e.g. '192.168.1.100'
MQTT_CLIENT = 'esp32-leds-123'

TOPIC_STRIP1 = b'home/leds/strip1'  # payload: "255,0,0"
TOPIC_STRIP2 = b'home/leds/strip2'
TOPIC_ALL    = b'home/leds/all'
# ──────────────────────────────────────

NUM_LEDS = 28
strip1 = neopixel.NeoPixel(Pin(4, Pin.OUT), NUM_LEDS)
strip2 = neopixel.NeoPixel(Pin(5, Pin.OUT), NUM_LEDS)

def set_strip(strip, r, g, b):
    for i in range(NUM_LEDS):
        strip[i] = (r, g, b)
    strip.write()

def parse_color(payload):
    """Parse '255,0,128' into (255, 0, 128)"""
    try:
        r, g, b = payload.decode().split(',')
        return int(r), int(g), int(b)
    except:
        return None

def on_message(topic, msg):
    print("MQTT:", topic, msg)
    color = parse_color(msg)
    if color is None:
        print("Invalid color format, use R,G,B")
        return
    r, g, b = color

    if topic == TOPIC_STRIP1:
        set_strip(strip1, r, g, b)
    elif topic == TOPIC_STRIP2:
        set_strip(strip2, r, g, b)
    elif topic == TOPIC_ALL:
        set_strip(strip1, r, g, b)
        set_strip(strip2, r, g, b)
    gc.collect()

# Connect MQTT
client = MQTTClient(MQTT_CLIENT, MQTT_BROKER)
client.set_callback(on_message)
client.connect(clean_session=True)
client.subscribe(TOPIC_STRIP1)
client.subscribe(TOPIC_STRIP2)
client.subscribe(TOPIC_ALL)
print("MQTT connected, waiting for messages...")

# Turn off both strips on start
set_strip(strip1, 0, 0, 0)
set_strip(strip2, 0, 0, 0)

# Main loop
while True:
    try:
        client.check_msg()   # non-blocking MQTT check
    except Exception as e:
        print("MQTT error:", e)
        time.sleep(5)
        client.connect()     # reconnect if dropped
        client.subscribe(TOPIC_STRIP1)
        client.subscribe(TOPIC_STRIP2)
        client.subscribe(TOPIC_ALL)
    time.sleep_ms(100)
    gc.collect()



