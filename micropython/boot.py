
import network
import time

print('Hello boot')

# Add color constants at top of main.py
CLR_RED    = '\033[31m'
CLR_GREEN  = '\033[32m'
CLR_YELLOW = '\033[33m'
CLR_BLUE   = '\033[34m'
CLR_CYAN   = '\033[36m'
CLR_RESET  = '\033[0m'

def log(*args, color=None):
    t = time.localtime()
    msg = ' '.join(str(a) for a in args)
    if color:
        print("%s%04d-%02d-%02d %02d:%02d:%02d | %s%s" % (
            color, t[0], t[1], t[2], t[3], t[4], t[5], msg, CLR_RESET))
    else:
        print("%04d-%02d-%02d %02d:%02d:%02d | %s" % (
            t[0], t[1], t[2], t[3], t[4], t[5], msg))
    
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

connect_wifi('dlink', '.MoNitor2?')

def sync_time():
    try:
        import ntptime
        ntptime.host = 'pool.ntp.org'
        ntptime.settime()
        print("Time synced:", time.localtime())
    except Exception as e:
        print("NTP sync failed:", e)


