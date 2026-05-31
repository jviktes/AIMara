
import network
import time

print('Hello boot')

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