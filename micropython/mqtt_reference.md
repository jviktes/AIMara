# ESP32 LED Strip — MQTT Reference

## LED Strip Control

| Topic | Payload | Description |
|---|---|---|
| `home/leds/1` to `home/leds/5` | `R,G,B` | Set color on individual strip |
| `home/leds/all` | `R,G,B` | Set same color on all 5 strips |

### Examples
```
home/leds/1       →  255,0,0       (strip 1 red)
home/leds/3       →  0,0,255       (strip 3 blue)
home/leds/all     →  0,255,0       (all strips green)
home/leds/all     →  0,0,0         (all strips off)
```

---

## Snake Animation

| Topic | Payload | Description |
|---|---|---|
| `home/leds/snake` | `start` or `stop` | Start or stop the snake animation |
| `home/leds/speed` | `10` to `200` | Snake speed in ms — lower = faster |
| `home/leds/snakecolor` | `R,G,B` | Snake head and tail color |
| `home/leds/bgcolor` | `R,G,B` | Background color behind snake |

### Examples
```
home/leds/snake       →  start
home/leds/snake       →  stop
home/leds/speed       →  30          (fast)
home/leds/speed       →  100         (slow)
home/leds/snakecolor  →  0,255,0     (red in GRB)
home/leds/bgcolor     →  200,200,200 (white)
```

---

## Color Reference

| Color | R,G,B payload | Note |
|---|---|---|
| Red | `0,255,0` | GRB order — R and G are swapped! |
| Green | `255,0,0` | GRB order |
| Blue | `0,0,255` | |
| White | `255,255,255` | |
| Off | `0,0,0` | |
| Warm white | `200,200,150` | |
| Orange | `0,165,255` | GRB order |

---

## Important Notes

> **Payload format:** Always `R,G,B` — no spaces, no brackets.  
> **GRB order:** WS2812B LEDs use GRB not RGB, so `0,255,0` = red.  
> **Snake + color:** You can change `snakecolor` and `bgcolor` while snake is running.  
> **Stop snake:** Send `stop` to `home/leds/snake` — all LEDs turn off.

---

## GPIO Wiring

| GPIO | Connected to |
|---|---|
| GPIO 4 | Strip 1 data |
| GPIO 5 | Strip 2 data |
| GPIO 13 | Strip 3 data |
| GPIO 14 | Strip 4 data |
| GPIO 15 | Strip 5 data |

> **Remember:** Always use a 330Ω resistor on each data line!
