import sys
import time
import math
import traceback
import requests
from PIL import Image, ImageDraw, ImageFont

sys.path.append("/home/tflowers/e-Paper/RaspberryPi_JetsonNano/python/lib")
from waveshare_epd import epd2in13_V4 as epd_driver

URL = "http://192.168.50.10/get_livedata_info"
ROTATE_180 = True
UPDATE_SECONDS = 60


def item_map(items):
    return {x["id"]: x for x in items}


def get_weather():
    response = requests.get(URL, timeout=10)
    response.raise_for_status()
    data = response.json()
    common = item_map(data["common_list"])
    rain = item_map(data["piezoRain"])
    indoor = data["wh25"][0]

    return {
        "out_temp": common["0x02"]["val"],
        "humidity": common["0x07"]["val"].replace(" ", ""),
        "feels": common["3"]["val"],
        "wind": common["0x0C"]["val"].replace(" mph", ""),
        "gust": common["0x19"]["val"].replace(" mph", ""),
        "wind_dir": common["0x6D"]["val"],
        "uv": common["0x17"]["val"],
        "rain": rain["0x10"]["val"].replace(" in", ""),
        "indoor_temp": indoor["intemp"],
        "indoor_humidity": indoor["inhumi"].replace(" ", ""),
        "updated": time.strftime("%I:%M %p").lstrip("0"),
    }


def draw_compass(draw, cx, cy, r, degrees, font):
    draw.ellipse((cx-r, cy-r, cx+r, cy+r), outline=0, width=2)
    draw.text((cx-4, cy-r-13), "N", font=font, fill=0)
    draw.text((cx+r+3, cy-6), "E", font=font, fill=0)
    draw.text((cx-4, cy+r+1), "S", font=font, fill=0)
    draw.text((cx-r-12, cy-6), "W", font=font, fill=0)

    rad = math.radians(float(degrees) - 90)
    x2 = cx + int(math.cos(rad) * (r - 7))
    y2 = cy + int(math.sin(rad) * (r - 7))

    draw.line((cx, cy, x2, y2), fill=0, width=3)

    head_len = 8
    for angle in (rad + math.radians(150), rad - math.radians(150)):
        pass

    x3 = x2 + int(math.cos(rad + math.radians(150)) * head_len)
    y3 = y2 + int(math.sin(rad + math.radians(150)) * head_len)
    x4 = x2 + int(math.cos(rad - math.radians(150)) * head_len)
    y4 = y2 + int(math.sin(rad - math.radians(150)) * head_len)
    draw.polygon([(x2, y2), (x3, y3), (x4, y4)], fill=0)


def draw_screen(w, epd):
    width, height = epd.height, epd.width
    image = Image.new("1", (width, height), 255)
    draw = ImageDraw.Draw(image)

    font_big = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 31)
    font_small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 12)
    font_small_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 12)

    draw.text((0, 0), f'{w["out_temp"]}°', font=font_big, fill=0)
    draw.text((84, 20), w["humidity"], font=font_small_bold, fill=0)

    draw.line((120, 3, 120, 39), fill=0, width=2)

    draw.text((128, 0), f'{w["indoor_temp"]}°', font=font_big, fill=0)
    draw.text((220, 20), w["indoor_humidity"], font=font_small_bold, fill=0)

    draw.line((0, 42, width, 42), fill=0)

    draw.text((0, 47), f'Feels {w["feels"]}°  UV {w["uv"]}', font=font_small_bold, fill=0)
    draw.text((0, 62), f'Wind {w["wind"]} mph', font=font_small_bold, fill=0)
    draw.text((0, 77), f'Gust {w["gust"]} mph', font=font_small_bold, fill=0)
    draw.text((0, 92), f'Rain {w["rain"]}"', font=font_small_bold, fill=0)
    draw.text((0, 110), f'Updated: {w["updated"]}', font=font_small, fill=0)

    draw_compass(draw, 205, 82, 23, w["wind_dir"], font_small)

    if ROTATE_180:
        return image.rotate(180)
    return image




def main():
    epd = epd_driver.EPD()
    next_update = time.monotonic()
    partial_ready = False

    try:
        while True:
            now = time.monotonic()
            if now < next_update:
                time.sleep(next_update - now)
            next_update += UPDATE_SECONDS

            try:
                weather = get_weather()
            except Exception as e:
                print("Weather update skipped:", e)
                traceback.print_exc()
                continue

            try:
                image = draw_screen(weather, epd)
                buffer = epd.getbuffer(image)

                if not partial_ready:
                    print("Initializing partial refresh base image")
                    epd.init()
                    epd.displayPartBaseImage(buffer)
                    partial_ready = True
                    continue

                print("Partial refresh update")
                epd.displayPartial(buffer)

            except Exception as e:
                partial_ready = False
                print("Display update failed:", e)
                traceback.print_exc()
                try:
                    epd.sleep()
                except Exception:
                    pass
    finally:
        try:
            epd.sleep()
        except Exception:
            pass


if __name__ == "__main__":
    main()
