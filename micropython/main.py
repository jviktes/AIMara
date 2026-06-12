import neopixel, time, gc
from machine import Pin
from machine import I2C
from machine import ADC
from umqtt.simple import MQTTClient
import ubinascii, machine, network

log('Version 2.3')

sync_time()

# ══════════════════════════════════════
# ── HARDWARE CONFIG ───────────────────
# Set True/False for what this ESP32 has
# ══════════════════════════════════════
HAS_LED_STRIPS = False
HAS_I2C        = False
HAS_PIR        = False
HAS_LDR        = False
HAS_HCSR04 = False
# ══════════════════════════════════════

# ── PCF8574 driver ────────────────────
class PCF8574:
    def __init__(self, i2c, address):
        self.i2c      = i2c
        self.address  = address
        self._state   = 0xFF

    def write(self, value):
        self._state = value
        self.i2c.writeto(self.address, bytes([value]))

    def read(self):
        return self.i2c.readfrom(self.address, 1)[0]

    def set_pin(self, pin, value):
        if value:
            self._state |=  (1 << pin)
        else:
            self._state &= ~(1 << pin)
        self.write(self._state)

    def get_pin(self, pin):
        val = self.read()
        return bool(val & (1 << pin))

# ── I2C + PCF8574 init ────────────────
pcf_in  = None
pcf_out = None

if HAS_I2C:
    try:
        i2c     = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
        devices = i2c.scan()
        log("I2C devices found:", [hex(a) for a in devices])
        if 0x24 in devices:
            pcf_in = PCF8574(i2c, 0x24)
            log("PCF input  OK (0x24)", color=CLR_GREEN)
        if 0x20 in devices:
            pcf_out = PCF8574(i2c, 0x20)
            pcf_out.write(0x00)
            log("PCF output OK (0x20)", color=CLR_GREEN)
    except Exception as e:
        log("I2C init failed:", e, color=CLR_RED)
else:
    log("I2C disabled in config")

# PCF8574 topics
TOPIC_PCF_OUT     = b'home/pcf/out'
TOPIC_PCF_OUT_ALL = b'home/pcf/outall'
TOPIC_PCF_BTN     = b'home/pcf/button'

# ── Light sensor on GPIO 34 ───────────
ldr = None
if HAS_LDR:
    try:
        ldr = ADC(Pin(34))
        ldr.atten(ADC.ATTN_11DB)
        log("LDR OK", color=CLR_GREEN)
    except Exception as e:
        log("LDR init failed:", e, color=CLR_RED)

#region PIR sensors — GPIO 32, 33
pir1 = None
pir2 = None
if HAS_PIR:
    try:
        pir1 = Pin(32, Pin.IN)
        pir2 = Pin(33, Pin.IN)
        log("PIR OK", color=CLR_GREEN)
    except Exception as e:
        log("PIR init failed:", e, color=CLR_RED)
#endregion

#region LED config
NUM_LEDS     = 27
SNAKE_LENGTH = 5

if HAS_LED_STRIPS:
    strips = [
        neopixel.NeoPixel(Pin(4,  Pin.OUT), NUM_LEDS),
        neopixel.NeoPixel(Pin(5,  Pin.OUT), NUM_LEDS),
        neopixel.NeoPixel(Pin(13, Pin.OUT), NUM_LEDS),
        neopixel.NeoPixel(Pin(14, Pin.OUT), NUM_LEDS),
        neopixel.NeoPixel(Pin(15, Pin.OUT), NUM_LEDS),
    ]
    log("LED strips OK", color=CLR_GREEN)
else:
    strips = []
    log("LED strips disabled in config")
#endregion


hcsr04_trig       = None
hcsr04_echo       = None
last_hcsr04_read  = 0
HCSR04_INTERVAL   = 500   # read every 500ms
HAS_HCSR04 = False

# ── State ─────────────────────────────
MAX_BRIGHTNESS    = 64            # 0-255, default 50%
snake_running     = False
snake_speed       = 80
snake_color       = (0, 255, 0)
bg_color          = (200, 200, 200)
snake_pos         = -SNAKE_LENGTH
last_button_state = 0xFF
config_applied    = False
ota_in_progress   = False

pir_debounce_ms = 500
pir1_last = 0  # last known state of PIR1
pir2_last = 0  # last known state of PIR2

# ── MQTT config ───────────────────────
MQTT_BROKER = '192.168.0.136'
MQTT_CLIENT = 'esp32-' + ubinascii.hexlify(machine.unique_id()).decode()

# Config topic — unique per device
DEVICE_ID            = ubinascii.hexlify(machine.unique_id()).decode()
TOPIC_CONFIG         = ('home/esp32/' + DEVICE_ID + '/config').encode()
TOPIC_CONFIG_REQUEST = ('home/esp32/' + DEVICE_ID + '/request_config').encode()
TOPIC_OTA            = ('home/esp32/' + DEVICE_ID + '/ota').encode()
TOPIC_HCSR04 = ('home/esp32/' + DEVICE_ID + '/distance').encode()
log("DEVICE_ID:", DEVICE_ID)

#region LEDS
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
TOPIC_BRIGHTNESS  = b'home/leds/brightness'  # payload: 0-255

# ── Helpers ───────────────────────────
def set_strip(strip, r, g, b):
    r = int(r * MAX_BRIGHTNESS // 255)
    g = int(g * MAX_BRIGHTNESS // 255)
    b = int(b * MAX_BRIGHTNESS // 255)
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
    # Apply brightness
    sr = int(sr * MAX_BRIGHTNESS // 255)
    sg = int(sg * MAX_BRIGHTNESS // 255)
    sb = int(sb * MAX_BRIGHTNESS // 255)
    br = int(br * MAX_BRIGHTNESS // 255)
    bg_b = int(bg_b * MAX_BRIGHTNESS // 255)
    bb = int(bb * MAX_BRIGHTNESS // 255)
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

def stop_snake():
    global snake_running
    if snake_running:
        snake_running = False
        log("Snake stopped by LED command")
#endregion

#region Light sensor reading and MQTT publishing
def read_light():
    if not ldr:
        return
    raw     = ldr.read()
    voltage = raw / 4095 * 3.6
    client.publish("esp32/light", str(raw))
    client.publish("esp32/light_voltage", "{:.2f}".format(voltage))
    log("Light raw:", raw, "voltage:", voltage)
#endregion

#region PIR sensor reading and MQTT publishing
def read_pir():
    if not pir1 or not pir2:
        return
    p1 = pir1.value()
    p2 = pir2.value()
    client.publish(b'esp32/pir/1', b'1' if p1 else b'0')
    client.publish(b'esp32/pir/2', b'1' if p2 else b'0')
    log("PIR1:", p1, "PIR2:", p2)
#endregion

#region HCSR04 distance sensor
def read_hcsr04():
    if not hcsr04_trig or not hcsr04_echo:
        return None
    try:
        # Send 10us trigger pulse
        hcsr04_trig.value(0)
        time.sleep_us(2)
        hcsr04_trig.value(1)
        time.sleep_us(10)
        hcsr04_trig.value(0)

        # Wait for echo start
        timeout = time.ticks_us()
        while hcsr04_echo.value() == 0:
            if time.ticks_diff(time.ticks_us(), timeout) > 30000:
                log("HCSR04 timeout waiting for echo start", color=CLR_RED)
                return None

        # Measure echo duration
        echo_start = time.ticks_us()
        while hcsr04_echo.value() == 1:
            if time.ticks_diff(time.ticks_us(), echo_start) > 30000:
                log("HCSR04 timeout waiting for echo end", color=CLR_RED)
                return None
        echo_end = time.ticks_us()

        # Calculate distance in cm
        duration = time.ticks_diff(echo_end, echo_start)
        distance = (duration * 0.0343) / 2
        return round(distance, 1)
    except Exception as e:
        log("HCSR04 error:", e, color=CLR_RED)
        return None
#endregion

# def Measurement():
#     # ... existing BMP280 + DHT code ...
#     read_light()

#region apply_config
def apply_config():
    global strips, pcf_in, pcf_out, ldr, pir1, pir2,hcsr04_trig, hcsr04_echo
    log("Applying config...", color=CLR_CYAN)

    # ── Disable hardware if config says False ──
    if not HAS_LED_STRIPS:
        strips = []
        log("LED strips disabled")

    if not HAS_I2C:
        pcf_in  = None
        pcf_out = None
        log("I2C disabled")

    if not HAS_PIR:
        pir1 = None
        pir2 = None
        log("PIR disabled")

    if not HAS_LDR:
        ldr = None
        log("LDR disabled")

    # ── Initialize if enabled ──────────
    if HAS_LED_STRIPS and not strips:
        try:
            strips = [
                neopixel.NeoPixel(Pin(4,  Pin.OUT), NUM_LEDS),
                neopixel.NeoPixel(Pin(5,  Pin.OUT), NUM_LEDS),
                neopixel.NeoPixel(Pin(13, Pin.OUT), NUM_LEDS),
                neopixel.NeoPixel(Pin(14, Pin.OUT), NUM_LEDS),
                neopixel.NeoPixel(Pin(15, Pin.OUT), NUM_LEDS),
            ]
            all_strips_off()
            log("LED strips initialized", color=CLR_GREEN)
        except Exception as e:
            log("LED strips init failed:", e, color=CLR_RED)

    if HAS_I2C and not pcf_in and not pcf_out:
        try:
            i2c     = I2C(0, sda=Pin(21), scl=Pin(22), freq=400000)
            devices = i2c.scan()
            log("I2C devices:", [hex(a) for a in devices])
            if 0x24 in devices:
                pcf_in = PCF8574(i2c, 0x24)
                log("PCF input OK (0x24)", color=CLR_GREEN)
            if 0x20 in devices:
                pcf_out = PCF8574(i2c, 0x20)
                pcf_out.write(0x00)
                log("PCF output OK (0x20)", color=CLR_GREEN)
        except Exception as e:
            log("I2C init failed:", e, color=CLR_RED)

    if HAS_PIR and not pir1:
        try:
            pir1 = Pin(32, Pin.IN)
            pir2 = Pin(33, Pin.IN)
            log("PIR initialized", color=CLR_GREEN)
        except Exception as e:
            log("PIR init failed:", e, color=CLR_RED)

    if HAS_LDR and not ldr:
        try:
            ldr = ADC(Pin(34))
            ldr.atten(ADC.ATTN_11DB)
            log("LDR initialized", color=CLR_GREEN)
        except Exception as e:
            log("LDR init failed:", e, color=CLR_RED)

    if not HAS_HCSR04:
            hcsr04_trig = None
            hcsr04_echo = None
            log("HCSR04 disabled")

    if HAS_HCSR04 and not hcsr04_trig:
            try:
                hcsr04_trig = Pin(25, Pin.OUT)
                hcsr04_echo = Pin(26, Pin.IN)
                hcsr04_trig.value(0)
                log("HCSR04 initialized", color=CLR_GREEN)
            except Exception as e:
                log("HCSR04 init failed:", e, color=CLR_RED)
            
    log("Config applied!", color=CLR_GREEN)
#endregion

#region OTA update
def ota_update(url):
    import urequests
    log("OTA: downloading from", url, color=CLR_YELLOW)
    try:
        r = urequests.get(url)
        if r.status_code == 200:
            log("OTA: download OK, saving...", color=CLR_YELLOW)
            f = open('main_new.py', 'w')
            f.write(r.text)
            f.close()
            r.close()
            import os
            try:
                os.remove('main_old.py')
            except:
                pass
            os.rename('main.py',     'main_old.py')
            os.rename('main_new.py', 'main.py')
            client.publish(TOPIC_OTA, b'', retain=True)
            log("OTA: success! rebooting...", color=CLR_GREEN)
            time.sleep(2)
            machine.reset()
        else:
            log("OTA: HTTP error", r.status_code, color=CLR_RED)
            r.close()
    except Exception as e:
        log("OTA: failed:", e, color=CLR_RED)
#endregion

# ── MQTT callback ─────────────────────
def on_message(topic, msg):
    global snake_running, snake_speed, snake_color, bg_color, snake_pos, last_snake_move, HAS_LED_STRIPS, HAS_I2C, HAS_PIR, HAS_LDR,HAS_HCSR04,MAX_BRIGHTNESS

    msg = msg.strip()
    log("MQTT:", topic, msg)
    topic_str = topic.decode()

    # ── Device config ──────────────────
    # Topic: home/esp32/<id>/config
    # Payload: LED_STRIPS=1,I2C=1,PIR=0,LDR=0
    if topic == TOPIC_CONFIG:
        global config_applied
        if config_applied:
            log("Config already applied, ignoring", color=CLR_YELLOW)
            return
        try:
            cfg = {}
            for p in msg.decode().split(','):
                k, v = p.split('=')
                cfg[k.strip()] = int(v.strip())
            HAS_LED_STRIPS = bool(cfg.get('LED_STRIPS', 0))
            HAS_I2C        = bool(cfg.get('I2C',        0))
            HAS_PIR        = bool(cfg.get('PIR',        0))
            HAS_LDR        = bool(cfg.get('LDR',        0))
            HAS_HCSR04     = bool(cfg.get('HCSR04',     0))
            log("Config received:", color=CLR_CYAN)
            log("  HAS_LED_STRIPS:", HAS_LED_STRIPS)
            log("  HAS_I2C:",        HAS_I2C)
            log("  HAS_PIR:",        HAS_PIR)
            log("  HAS_LDR:",        HAS_LDR)
            log("  HAS_HCSR04:",     HAS_HCSR04)
            apply_config()
            config_applied = False
        except Exception as e:
            log("Config error:", e, color=CLR_RED)
        return

    # ── Individual LED ─────────────────
    # Topic: home/leds/s1/12   payload: 255,0,0
    parts = topic_str.split('/')
    if topic_str.startswith('home/leds/s') and len(parts) == 4 and parts[2][1:].isdigit() and not topic_str.endswith('/range'):
        stop_snake()
        if HAS_LED_STRIPS:
            try:
                strip_num = int(parts[2][1:]) - 1
                led_num   = int(parts[3])
                if 0 <= strip_num <= 4 and 0 <= led_num < NUM_LEDS:
                    color = parse_color(msg)
                    if color:
                        r, g, b = color
                        strips[strip_num][led_num] = (r, g, b)
                        strips[strip_num].write()
                        log("Set s%d LED %d → %d,%d,%d" % (strip_num+1, led_num, r, g, b))
                else:
                    log("Invalid strip or LED number", color=CLR_RED)
            except Exception as e:
                log("Single LED error:", e, color=CLR_RED)
        return

    # ── Range control ──────────────────
    # Topic: home/leds/s1/range   payload: 0,10,255,0,0
    if topic_str.startswith('home/leds/s') and topic_str.endswith('/range'):
        stop_snake()
        if HAS_LED_STRIPS:
            try:
                strip_num = int(parts[2][1:]) - 1
                values    = msg.decode().split(',')
                start = max(0, min(int(values[0]), NUM_LEDS - 1))
                end   = max(0, min(int(values[1]), NUM_LEDS - 1))
                r     = int(values[2])
                g     = int(values[3])
                b     = int(values[4])
                for i in range(start, end + 1):
                    strips[strip_num][i] = (r, g, b)
                strips[strip_num].write()
                log("Set s%d LEDs %d-%d → %d,%d,%d" % (strip_num+1, start, end, r, g, b))
            except Exception as e:
                log("Range error:", e, color=CLR_RED)
        return

    #region Light sensor
    if topic == b'esp32/light/get':
        read_light()
        return
    #endregion

    # ── PCF8574 output ─────────────────
    # Topic: home/pcf/out   payload: 3,1 or 3,0
    if topic == TOPIC_PCF_OUT:
        if pcf_out:
            try:
                parts = msg.decode().split(',')
                pin   = int(parts[0])
                value = int(parts[1])
                pcf_out.set_pin(pin, value)
                log("PCF out pin %d → %d" % (pin, value))
            except Exception as e:
                log("PCF out error:", e, color=CLR_RED)
        return

    # Topic: home/pcf/outall   payload: 255
    if topic == TOPIC_PCF_OUT_ALL:
        if pcf_out:
            try:
                pcf_out.write(int(msg.decode()))
                log("PCF out all →", msg)
            except Exception as e:
                log("PCF outall error:", e, color=CLR_RED)
        return

    # ── Individual strip color ─────────
    for i, t in enumerate(TOPIC_STRIP):
        if topic == t:
            stop_snake()
            if HAS_LED_STRIPS:
                color = parse_color(msg)
                if color:
                    set_strip(strips[i], *color)
            return

    # ── All strips ─────────────────────
    if topic == TOPIC_ALL:
        stop_snake()
        if HAS_LED_STRIPS:
            color = parse_color(msg)
            if color:
                for s in strips:
                    set_strip(s, *color)
        return

    # ── Snake start/stop ───────────────
    if topic == TOPIC_SNAKE:
        if HAS_LED_STRIPS:
            if msg == b'start':
                snake_running   = True
                snake_pos       = -SNAKE_LENGTH
                last_snake_move = time.ticks_ms()
                log("Snake started", color=CLR_GREEN)
            elif msg == b'stop':
                snake_running = False
                all_strips_off()
                log("Snake stopped")
        return

    # ── Snake speed ────────────────────
    if topic == TOPIC_SPEED:
        if HAS_LED_STRIPS:
            try:
                snake_speed = max(10, min(200, int(msg.decode())))
                log("Speed:", snake_speed)
            except:
                pass
        return

    # ── Snake color ────────────────────
    if topic == TOPIC_SNAKE_COLOR:
        if HAS_LED_STRIPS:
            color = parse_color(msg)
            if color:
                snake_color = color
        return

    # ── Background color ───────────────
    if topic == TOPIC_BG_COLOR:
        if HAS_LED_STRIPS:
            color = parse_color(msg)
            if color:
                bg_color = color
        return
    
    # ── Brightness ─────────────────────
    # Topic: home/leds/brightness   payload: 0-255
    if topic == TOPIC_BRIGHTNESS:
        if HAS_LED_STRIPS:
            try:
                MAX_BRIGHTNESS = max(0, min(255, int(msg.decode())))
                log("Brightness:", MAX_BRIGHTNESS)
            except Exception as e:
                log("Brightness error:", e, color=CLR_RED)
        return
    
    # ── OTA update ─────────────────────
    # Topic: home/esp32/<id>/ota
    # Payload: http://192.168.0.x:1880/firmware/main.py
    if topic == TOPIC_OTA:
        global ota_in_progress
        if ota_in_progress:
            log("OTA already in progress, ignoring", color=CLR_YELLOW)
            return
        ota_in_progress = True
        url = msg.decode()
        log("OTA triggered:", url, color=CLR_YELLOW)
        ota_update(url)
        return

    gc.collect()

# ── Main loop setup ───────────────────
last_snake_move   = time.ticks_ms()
last_button_check = time.ticks_ms()
last_hcsr04_read  = time.ticks_ms()
snake_pos         = -SNAKE_LENGTH
wlan              = network.WLAN(network.STA_IF)

# ── MQTT connect ──────────────────────
def mqtt_connect():
    c = MQTTClient(MQTT_CLIENT, MQTT_BROKER, keepalive=300)
    c.set_callback(on_message)
    c.connect(clean_session=True)
    c.subscribe(TOPIC_CONFIG)
    c.subscribe(TOPIC_ALL)
    c.subscribe(TOPIC_SNAKE)
    c.subscribe(TOPIC_SPEED)
    c.subscribe(TOPIC_SNAKE_COLOR)
    c.subscribe(TOPIC_BG_COLOR)
    c.subscribe(TOPIC_PCF_OUT)
    c.subscribe(TOPIC_PCF_OUT_ALL)
    c.subscribe(b'esp32/light/get')
    for t in TOPIC_STRIP:
        c.subscribe(t)
    c.subscribe(b'home/leds/s1/+')
    c.subscribe(b'home/leds/s2/+')
    c.subscribe(b'home/leds/s3/+')
    c.subscribe(b'home/leds/s4/+')
    c.subscribe(b'home/leds/s5/+')
    c.subscribe(TOPIC_BRIGHTNESS)
    c.subscribe(TOPIC_OTA)
    c.publish(TOPIC_CONFIG_REQUEST, DEVICE_ID.encode())
    log("MQTT connected as:", MQTT_CLIENT, color=CLR_YELLOW)
    log("Config requested...", color=CLR_YELLOW)
    return c

client = mqtt_connect()

# Turn off all on start
all_strips_off()
if pcf_out:
    pcf_out.write(0x00)
log("Ready!", color=CLR_GREEN)

# ── Main loop ─────────────────────────
while True:
    # WiFi watchdog
    if not wlan.isconnected():
        log("WiFi lost, reconnecting...", color=CLR_YELLOW)
        connect_wifi('YOUR_SSID', 'YOUR_PASSWORD')

    # MQTT check
    try:
        client.check_msg()
    except Exception as e:
        log("MQTT error:", e, color=CLR_RED)
        time.sleep(3)
        try:
            client = mqtt_connect()
        except:
            pass

    # ── Button polling ─────────────────
    now = time.ticks_ms()
    if time.ticks_diff(now, last_button_check) >= 50:
        if pcf_in:
            try:
                current = pcf_in.read()
                if current != last_button_state:
                    for pin in range(8):
                        old_bit = (last_button_state >> pin) & 1
                        new_bit = (current >> pin) & 1
                        if old_bit != new_bit:
                            payload = ('%d,%d' % (pin, new_bit)).encode()
                            client.publish(TOPIC_PCF_BTN, payload)
                            log("Button pin %d → %d" % (pin, new_bit), color=CLR_BLUE)
                    last_button_state = current
            except Exception as e:
                log("PCF in error:", e, color=CLR_RED)
        last_button_check = now

    # ── Snake animation ────────────────
    if HAS_LED_STRIPS and snake_running:
        now = time.ticks_ms()
        diff = time.ticks_diff(now, last_snake_move)
        if diff >= snake_speed:
            draw_snake(snake_pos)
            snake_pos += 1
            if snake_pos >= NUM_LEDS:
                snake_pos = -SNAKE_LENGTH
            last_snake_move = now

    #region PIR — edge detection, publish only on change
    if HAS_PIR and pir1 and pir2:
        p1 = pir1.value()
        p2 = pir2.value()
        if p1 != pir1_last:
            pir1_last = p1
            client.publish(b'esp32/pir/1', b'1' if p1 else b'0')
            log("PIR1:", "motion start" if p1 else "motion end", color=CLR_CYAN)
            time.sleep_ms(pir_debounce_ms)
        if p2 != pir2_last:
            pir2_last = p2
            client.publish(b'esp32/pir/2', b'1' if p2 else b'0')
            log("PIR2:", "motion start" if p2 else "motion end", color=CLR_CYAN)
            time.sleep_ms(pir_debounce_ms)
    #endregion

    #region HCSR04 — read distance and publish
    if HAS_HCSR04 and hcsr04_trig and hcsr04_echo:
        now = time.ticks_ms()
        if time.ticks_diff(now, last_hcsr04_read) >= HCSR04_INTERVAL:
            dist = read_hcsr04()
            if dist is not None:
                log("Distance:", dist, "cm")
                client.publish(TOPIC_HCSR04, str(dist).encode())
            last_hcsr04_read = now
    #endregion

    time.sleep_ms(10)
    gc.collect()