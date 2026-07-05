import sys
import time
import math
import traceback
import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont

sys.path.append("/home/tflowers/e-Paper/RaspberryPi_JetsonNano/python/lib")
from waveshare_epd import epd2in13_V4 as epd_driver
from waveshare_epd import epdconfig

URL = "http://192.168.50.10/get_livedata_info"
ROTATE_180 = True
UPDATE_SECONDS = 60

# Regions in the unrotated landscape drawing coordinates. Keeping these small
# limits partial-refresh flashing to the areas that can actually change.
UPDATE_REGIONS = (
    (0, 0, 118, 42),      # outdoor temperature and humidity
    (122, 0, 250, 42),    # indoor temperature and humidity
    (0, 45, 150, 122),    # text weather details and updated time
    (170, 45, 250, 122),  # wind direction compass
)
REGION_PADDING = 4


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


def padded_box(box, width, height, padding=REGION_PADDING):
    x0, y0, x1, y1 = box
    return (
        max(0, x0 - padding),
        max(0, y0 - padding),
        min(width, x1 + padding),
        min(height, y1 + padding),
    )


def rotate_180_box(box, width, height):
    x0, y0, x1, y1 = box
    return (width - x1, height - y1, width - x0, height - y0)


def update_regions_for(image):
    width, height = image.size
    regions = [padded_box(box, width, height) for box in UPDATE_REGIONS]
    if ROTATE_180:
        regions = [rotate_180_box(box, width, height) for box in regions]
    return regions


def image_to_native(image, epd):
    if image.size == (epd.width, epd.height):
        return image.convert("1")
    if image.size == (epd.height, epd.width):
        return image.rotate(90, expand=True).convert("1")
    raise ValueError(f"Unexpected image size {image.size}")


def landscape_box_to_native(box, source_width):
    x0, y0, x1, y1 = box
    return (y0, source_width - x1, y1, source_width - x0)


def align_native_box(box, epd):
    x0, y0, x1, y1 = box
    x0 = max(0, (x0 // 8) * 8)
    x1 = min(epd.width, ((x1 + 7) // 8) * 8)
    y0 = max(0, y0)
    y1 = min(epd.height, y1)
    if x0 >= x1 or y0 >= y1:
        return None
    return (x0, y0, x1, y1)


def prepare_partial_update(epd):
    epdconfig.digital_write(epd.reset_pin, 0)
    epdconfig.delay_ms(1)
    epdconfig.digital_write(epd.reset_pin, 1)

    epd.send_command(0x3C)  # BorderWaveform
    epd.send_data(0x80)

    epd.send_command(0x01)  # Driver output control
    epd.send_data(0xF9)
    epd.send_data(0x00)
    epd.send_data(0x00)

    epd.send_command(0x11)  # Data entry mode
    epd.send_data(0x03)


def merge_boxes(boxes):
    x0 = min(box[0] for box in boxes)
    y0 = min(box[1] for box in boxes)
    x1 = max(box[2] for box in boxes)
    y1 = max(box[3] for box in boxes)
    return (x0, y0, x1, y1)


def display_partial_window(epd, native_image, box):
    x0, y0, x1, y1 = box
    crop = native_image.crop(box)
    epd.SetWindow(x0, y0, x1 - 1, y1 - 1)
    epd.SetCursor(x0 // 8, y0)
    epd.send_command(0x24)  # WRITE_RAM
    epd.send_data2(bytearray(crop.tobytes("raw")))
    # V4 may still apply a visible full-panel waveform here, but this keeps
    # each minute update to one refresh instead of one refresh per changed box.
    epd.TurnOnDisplayPart()


def display_changed_regions(epd, previous_image, image):
    native_image = image_to_native(image, epd)
    changed_boxes = []

    for region in update_regions_for(image):
        before = previous_image.crop(region)
        after = image.crop(region)
        if ImageChops.difference(before, after).getbbox() is None:
            continue
        native_box = landscape_box_to_native(region, image.size[0])
        native_box = align_native_box(native_box, epd)
        if native_box is not None:
            changed_boxes.append(native_box)

    if not changed_boxes:
        print("No display regions changed")
        return

    merged_box = merge_boxes(changed_boxes)
    prepare_partial_update(epd)
    print(f"Windowed partial refresh {merged_box}")
    display_partial_window(epd, native_image, merged_box)


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
    previous_image = None

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

                if previous_image is None:
                    print("Initializing partial refresh base image")
                    epd.init()
                    epd.displayPartBaseImage(epd.getbuffer(image))
                    previous_image = image
                    continue

                display_changed_regions(epd, previous_image, image)
                previous_image = image

            except Exception as e:
                previous_image = None
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
