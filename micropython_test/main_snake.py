import neopixel, time, gc
from machine import Pin

NUM_LEDS     = 27
SNAKE_LENGTH = 5
snake_speed  = 80
snake_pos    = -SNAKE_LENGTH
snake_running = True

strips = [
    neopixel.NeoPixel(Pin(4,  Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(5,  Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(13, Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(14, Pin.OUT), NUM_LEDS),
    neopixel.NeoPixel(Pin(15, Pin.OUT), NUM_LEDS),
]

snake_color = (0, 255, 0)
bg_color    = (200, 200, 200)

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

last_snake_move = time.ticks_ms()
print("starting...")

while True:
    now = time.ticks_ms()
    diff = time.ticks_diff(now, last_snake_move)
    if diff >= snake_speed:
        print("drawing pos:", snake_pos, "diff:", diff)
        draw_snake(snake_pos)
        snake_pos += 1
        if snake_pos >= NUM_LEDS:
            snake_pos = -SNAKE_LENGTH
        last_snake_move = now
    time.sleep_ms(10)