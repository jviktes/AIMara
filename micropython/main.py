import neopixel, time, gc
from machine import Pin
from umqtt.simple import MQTTClient
import ubinascii, machine, network

# ── WiFi ──────────────────────────────
def connect_wifi(ssid, password):
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    if not wlan.isconnected():
        print('Connecting to WiFi...')
        wlan.connect(ssid, password)
        while not wlan.isconnected():
            time.sleep(0.5)
            print('.')
    print('WiFi connected:', wlan.ifconfig()[0])

connect_wifi('YOUR_SSID', 'YOUR_PASSWORD')

# ── LED config ────────────────────────
NUM_LEDS     = 27
SNAKE_LENGTH = 5

strips = [
    neopixel.NeoPixel(Pin(4,  Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(5,  Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(13, Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(14, Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(15, Pin.OUT), NUM_LEDS),
]

# ── State ─────────────────────────────
snake_running = False
snake_speed   = 30
snake_color   = (0, 255, 0)    # GRB = red
bg_color      = (200, 200, 200)
snake_pos     = -SNAKE_LENGTH

# ── MQTT config ───────────────────────
MQTT_BROKER = '192.168.0.136'
MQTT_CLIENT = 'esp32-' + ubinascii.hexlify(machine.unique_id()).decode()

TOPIC_STRIP = [
    b'home/leds/1',
    b'home/leds/2',
    b'home/leds/3',
    b'home/leds/4',
    b'home/leds/5',
]
TOPIC_ALL         = b'home/leds/all'
TOPIC_SNAKE       = b'home/leds/snake'
TOPIC_SPEED       = b'home/leds/speed'
TOPIC_SNAKE_COLOR = b'home/leds/snakecolor'
TOPIC_BG_COLOR    = b'home/leds/bgcolor'

# ── Helpers ───────────────────────────
def set_strip(strip, r, g, b):
    for i in range(NUM_LEDS):
        strip[i] = (r, g, b)
    strip.write()

def all_strips_off():
    for s in strips:
        set_strip(s, 0, 0, 0)

def parse_color(payload):
    try:
        parts = payload.decode().split(',')
        return int(parts[0]), int(parts[1]), int(parts[2])
    except:
        return None

# ── Snake ─────────────────────────────
def draw_snake(position):
    sr, sg, sb   = snake_color
    br, bg_b, bb = bg_color

    for strip in strips:
        for i in range(NUM_LEDS):
            dist = position - i
            if dist == 0:
                strip[i] = (sr, sg, sb)
            elif 0 < dist < SNAKE_LENGTH:
                fade = 1 - dist / SNAKE_LENGTH
                strip[i] = (
                    int(sr * fade + br * (1 - fade)),
                    int(sg * fade + bg_b * (1 - fade)),
                    int(sb * fade + bb * (1 - fade)),
                )
            else:
                strip[i] = (br, bg_b, bb)
        strip.write()

# ── MQTT callback ─────────────────────
def on_message(topic, msg):
    global snake_running, snake_speed, snake_color, bg_color

    print("MQTT:", topic, msg)
    topic_str = topic.decode()

    # ── Individual LED ─────────────────
    # Topic: home/leds/s1/12   payload: 255,0,0
    if topic_str.startswith('home/leds/s') and not topic_str.endswith('/range'):
        try:
            parts     = topic_str.split('/')
            strip_num = int(parts[2][1:]) - 1   # s1→0, s5→4
            led_num   = int(parts[3])
            if 0 <= strip_num <= 4 and 0 <= led_num < NUM_LEDS:
                color = parse_color(msg)
                if color:
                    r, g, b = color
                    strips[strip_num][led_num] = (r, g, b)
                    strips[strip_num].write()
                    print("Set s%d LED %d → %d,%d,%d" % (strip_num+1, led_num, r, g, b))
            else:
                print("Invalid strip or LED number")
        except Exception as e:
            print("Single LED error:", e)
        return

    # ── Range control ──────────────────
    # Topic: home/leds/s1/range   payload: 0,10,255,0,0
    if topic_str.startswith('home/leds/s') and topic_str.endswith('/range'):
        try:
            parts     = topic_str.split('/')
            strip_num = int(parts[2][1:]) - 1   # s1→0, s5→4
            values    = msg.decode().split(',')
            start = int(values[0])
            end   = int(values[1])
            r     = int(values[2])
            g     = int(values[3])
            b     = int(values[4])
            start = max(0, min(start, NUM_LEDS - 1))
            end   = max(0, min(end,   NUM_LEDS - 1))
            for i in range(start, end + 1):
                strips[strip_num][i] = (r, g, b)
            strips[strip_num].write()
            print("Set s%d LEDs %d-%d → %d,%d,%d" % (strip_num+1, start, end, r, g, b))
        except Exception as e:
            print("Range error:", e)
        return

    # ── Individual strip color ─────────
    for i, t in enumerate(TOPIC_STRIP):
        if topic == t:
            color = parse_color(msg)
            if color:
                set_strip(strips[i], *color)
            return

    # ── All strips ─────────────────────
    if topic == TOPIC_ALL:
        color = parse_color(msg)
        if color:
            for s in strips:
                set_strip(s, *color)

    # ── Snake start/stop ───────────────
    elif topic == TOPIC_SNAKE:
        if msg == b'start':
            snake_running = True
            print("Snake started")
        elif msg == b'stop':
            snake_running = False
            all_strips_off()
            print("Snake stopped")

    # ── Snake speed ────────────────────
    elif topic == TOPIC_SPEED:
        try:
            snake_speed = max(10, min(200, int(msg.decode())))
            print("Speed:", snake_speed)
        except:
            pass

    # ── Snake color ────────────────────
    elif topic == TOPIC_SNAKE_COLOR:
        color = parse_color(msg)
        if color:
            snake_color = color

    # ── Background color ───────────────
    elif topic == TOPIC_BG_COLOR:
        color = parse_color(msg)
        if color:
            bg_color = color

    gc.collect()

# ── MQTT connect ──────────────────────
def mqtt_connect():
    c = MQTTClient(MQTT_CLIENT, MQTT_BROKER, keepalive=60)
    c.set_callback(on_message)
    c.connect(clean_session=True)
    c.subscribe(TOPIC_ALL)
    c.subscribe(TOPIC_SNAKE)
    c.subscribe(TOPIC_SPEED)
    c.subscribe(TOPIC_SNAKE_COLOR)
    c.subscribe(TOPIC_BG_COLOR)
    for t in TOPIC_STRIP:
        c.subscribe(t)
    # Individual LED topics
    c.subscribe(b'home/leds/s1/+')
    c.subscribe(b'home/leds/s2/+')
    c.subscribe(b'home/leds/s3/+')
    c.subscribe(b'home/leds/s4/+')
    c.subscribe(b'home/leds/s5/+')
    print("MQTT connected as:", MQTT_CLIENT)
    return c

client = mqtt_connect()

# Turn off all on start
all_strips_off()
print("Ready!")

# ── Main loop ─────────────────────────
last_snake_move = time.ticks_ms()
snake_pos = -SNAKE_LENGTH
wlan = network.WLAN(network.STA_IF)

while True:
    # WiFi watchdog
    if not wlan.isconnected():
        print("WiFi lost, reconnecting...")
        connect_wifi('YOUR_SSID', 'YOUR_PASSWORD')

    # MQTT check
    try:
        client.check_msg()
    except Exception as e:
        print("MQTT error:", e)
        time.sleep(3)
        try:
            client = mqtt_connect()
        except:
            pass

    # Snake animation
    if snake_running:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_snake_move) >= snake_speed:
            draw_snake(snake_pos)
            snake_pos += 1
            if snake_pos >= NUM_LEDS:
                snake_pos = -SNAKE_LENGTH
            last_snake_move = now

    time.sleep_ms(10)
    gc.collect()