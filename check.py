import os
import pdfplumber
from enum import Enum
from collections import defaultdict
import json
from termcolor import colored
import numpy as np
import traceback


TOP_OFFSET = 1
BOTTOM_OFFSET = 1
LEFT_OFFSET = 2
RIGHT_OFFSET = 4.5

MARGIN_TOP = 57
MARGIN_BOTTOM = 73
MARGIN_LEFT = 54
MARGIN_RIGHT = 54

class Error(Enum):
    SIZE = "Size"
    PARSING = "Parsing"
    MARGIN = "Margin"
    SPELLING = "Spelling"
    FONT = "Font"
    PAGELIMIT = "Page Limit"


class Margin(Enum):
    TOP = "top"
    BOTTOM = "bottom"
    RIGHT = "right"
    LEFT = "left"


class Page(Enum):
    """Letter size
    612 pt x 792 pt
    """

    WIDTH = 612
    HEIGHT = 792


class Formatter(object):
    def __init__(self):
        self.background_color = 255
        # self.review_color =

    def format_check(self, paper, output_dir=".", print_only_errors=False):
        print(f"Checking {paper}")

        self.logs = defaultdict(
            list
        )  # reset log before calling the format-checking functions
        self.page_errors = set()
        self.pdf = pdfplumber.open(paper)
        self.filename = os.path.split(paper)[-1]
        output_file = "errors-{0}.json".format(self.filename)
        self.check_size()
        self.check_margin(output_dir=output_dir)

        logs_json = {}
        for k, v in self.logs.items():
            logs_json[str(k)] = v

        if self.logs:
            print(f"Errors. Check {output_file} for details.")
        errors, warnings = 0, 0
        if self.logs.items():
            for e, ms in self.logs.items():
                for m in ms:
                    if isinstance(e, Error) and e != Error.PARSING:
                        print(colored("Error ({0}):".format(e.value), "red") + " " + m)
                        errors += 1
                    elif e == Error.PARSING:
                        print(
                            colored("Parsing Error:".format(e.value), "yellow")
                            + " "
                            + m
                        )
                    else:
                        print(
                            colored("Warning ({0}):".format(e.value), "yellow")
                            + " "
                            + m
                        )
                        warnings += 1

            # English nominal morphology
            error_text = "errors"
            if errors == 1:
                error_text = "error"
            warning_text = "warnings"
            if warnings == 1:
                warning_text = "warning"

            if print_only_errors == False:
                json.dump(
                    logs_json, open(os.path.join(output_dir, output_file), "w")
                )  # always write a log file even if it is empty

            # display to user
            print()
            print(
                "We detected {0} {1} and {2} {3} in your paper.".format(
                    *(errors, error_text, warnings, warning_text)
                )
            )
            print(
                "In general, it is required that you fix errors for your paper to be published. Fixing warnings is optional, but recommended."
            )
            print(
                "Important: Some of the margin errors may be spurious. The library detects the location of images, but not whether they have a white background that blends in."
            )
            print(
                "Important: Some of the warnings generated for citations may be spurious and inaccurate, due to parsing and indexing errors."
            )
            print(
                "We encourage you to double check the citations and update them depending on the latest source. If you believe that your citation is updated and correct, then please ignore those warnings."
            )

            if errors >= 1:
                return logs_json
            else:
                return {}

        else:
            if print_only_errors == False:
                json.dump(logs_json, open(os.path.join(output_dir, output_file), "w"))

            print(colored("All Clear!", "green"))
            return logs_json

    def check_size(self):
        """Letter size"""
        pages = []
        for i, page in enumerate(self.pdf.pages):
            if (round(page.width), round(page.height)) != (Page.WIDTH.value, Page.HEIGHT.value):
                pages.append(i + 1)
        for page in pages:
            error = "Page #{} is not Letter size".format(page)
            self.logs[Error.SIZE] += [error]
        self.page_errors.update(pages)

    def check_margin(self, output_dir):
        pages_image = defaultdict(list)
        pages_text = defaultdict(list)
        perror = []
        for i, page in enumerate(self.pdf.pages):
            if i + 1 in self.page_errors:
                continue
            try:
                # Parse images
                for image in page.images:
                    violation = None
                    if int(image["bottom"]) > 0 and float(image["top"]) < (
                        MARGIN_TOP - TOP_OFFSET
                    ):
                        violation = Margin.TOP
                    elif int(image["x1"]) > 0 and float(image["x0"]) < (
                        MARGIN_LEFT - LEFT_OFFSET
                    ):
                        violation = Margin.LEFT
                    elif int(
                        image["x0"]
                    ) < Page.WIDTH.value and Page.WIDTH.value - float(image["x1"]) < (
                        MARGIN_RIGHT - RIGHT_OFFSET
                    ):
                        violation = Margin.RIGHT

                    if violation:
                        # if the image is completely white, it can be skipped

                        # get the actual visible area
                        x0 = max(0, int(image["x0"]))
                        # check the intersection with the right margin to handle larger images
                        # but with an "overflow" that is of the same color of the backgrond
                        if violation == Margin.RIGHT:
                            x0 = max(x0, Page.WIDTH.value - MARGIN_RIGHT + RIGHT_OFFSET)

                        x1 = min(int(image["x1"]), Page.WIDTH.value)
                        if violation == Margin.LEFT:
                            x1 = min(x1, MARGIN_LEFT - RIGHT_OFFSET)

                        y0 = max(0, int(image["top"]))

                        y1 = min(int(image["bottom"]), Page.HEIGHT.value)
                        if violation == Margin.TOP:
                            y1 = min(y1, MARGIN_TOP - TOP_OFFSET)
                        elif violation == Margin.BOTTOM:
                            y1 = max(y1, Page.HEIGHT.value - (MARGIN_BOTTOM - BOTTOM_OFFSET))

                        bbox = (x0, y0, x1, y1)

                        # avoid problems in cropping images too small
                        if x1 - x0 <= 1 or y1 - y0 <= 1:
                            continue

                        # cropping the image to check if it is white
                        # i.e., all pixels set to 255
                        cropped_page = page.crop(bbox)
                        try:
                            image_obj = cropped_page.to_image(resolution=100)
                            if np.mean(image_obj.original) != self.background_color:
                                pages_image[i] += [(image, violation)]
                        # if there are some errors during cropping, it is better to check
                        except:
                            pages_image[i] += [(image, violation)]

                # Parse texts
                for j, word in enumerate(
                    page.extract_words(
                        extra_attrs=["non_stroking_color", "stroking_color"]
                    )
                ):
                    violation = None

                    # if word["non_stroking_color"] == (0, 0, 0) or word["non_stroking_color"] == 0 or word["stroking_color"] == 0:
                    if word["non_stroking_color"] == (0, 0, 0) or word[
                        "non_stroking_color"
                    ] == [0]:
                        continue

                    if (
                        word["non_stroking_color"] is None
                        and word["stroking_color"] is None
                    ):
                        continue

                    if int(word["bottom"]) > 0 and float(word["top"]) < (
                        MARGIN_TOP - TOP_OFFSET
                    ):
                        violation = Margin.TOP
                    elif int(word["x1"]) > 0 and float(word["x0"]) < (MARGIN_LEFT - LEFT_OFFSET):
                        violation = Margin.LEFT
                    elif int(
                        word["x0"]
                    ) < Page.WIDTH.value and Page.WIDTH.value - float(word["x1"]) < (
                        MARGIN_RIGHT - RIGHT_OFFSET
                    ):
                        violation = Margin.RIGHT
                    elif float(word["bottom"]) > Page.HEIGHT.value - (MARGIN_BOTTOM - BOTTOM_OFFSET):
                        violation = Margin.BOTTOM

                    if (
                        violation
                        and int(word["x0"]) < Page.WIDTH.value
                        and int(word["x1"]) >= 0
                        and int(word["bottom"]) >= 0
                    ):
                        # if the area image is completely white, it can be skipped
                        # get the actual visible area
                        x0 = max(0, int(word["x0"]))
                        # check the intersection with the right margin to handle larger images
                        # but with an "overflow" that is of the same color of the backgrond
                        if violation == Margin.RIGHT:
                            x0 = max(x0, Page.WIDTH.value - MARGIN_RIGHT + RIGHT_OFFSET)

                        x1 = min(int(word["x1"]), Page.WIDTH.value)
                        if violation == Margin.LEFT:
                            x1 = min(x1, MARGIN_LEFT - RIGHT_OFFSET)

                        y0 = max(0, int(word["top"]))

                        y1 = min(int(word["bottom"]), Page.HEIGHT.value)
                        if violation == Margin.TOP:
                            y1 = min(y1, MARGIN_TOP - TOP_OFFSET)

                        bbox = (x0, y0, x1, y1)
                        # avoid problems in cropping images too small
                        if x1 - x0 <= 1 or y1 - y0 <= 1:
                            continue

                        # cropping the image to check if it is white or red (review line number), i.e., rgb is (255, 255, 255) or (255, 0, 0)
                        try:
                            cropped_page = page.crop(bbox)
                            image_obj = cropped_page.to_image(resolution=100)
                            a = np.array(image_obj.original)
                            if not (((a == [255, 255, 255]).sum(2) == 3) + ((a == [255, 0, 0]).sum(2) == 3)).all():
                            # if np.mean(image_obj.original) != self.background_color and np.array(image_obj):
                                print(
                                    "Found text violation:\t"
                                    + str(violation)
                                    + "\t"
                                    + str(word)
                                )
                                pages_text[i] += [(word, violation)]
                        except:
                            # if there are some errors during cropping, it is better to check
                            pages_image[i] += [(word, violation)]

            except:
                traceback.print_exc()
                perror.append(i + 1)

        if perror:
            self.page_errors.update(perror)
            self.logs[Error.PARSING] = [
                "Error occurs when parsing page {}.".format(perror)
            ]

        if pages_text or pages_image:
            pages = sorted(set(pages_text.keys()).union(set((pages_image.keys()))))
            for page in pages:
                im = self.pdf.pages[page].to_image(resolution=150)
                for word, violation in pages_text[page]:

                    bbox = None
                    if violation == Margin.RIGHT:
                        self.logs[Error.MARGIN] += [
                            "Text on page {} bleeds into the right margin.".format(
                                page + 1
                            )
                        ]
                        bbox = (
                            Page.WIDTH.value - 80,
                            int(word["top"] - 20),
                            Page.WIDTH.value - 20,
                            int(word["bottom"] + 20),
                        )
                        im.draw_rect(bbox, fill=None, stroke="red", stroke_width=5)
                    elif violation == Margin.LEFT:
                        self.logs[Error.MARGIN] += [
                            "Text on page {} bleeds into the left margin.".format(
                                page + 1
                            )
                        ]
                        bbox = (20, int(word["top"] - 20), 80, int(word["bottom"] + 20))
                        im.draw_rect(bbox, fill=None, stroke="red", stroke_width=5)
                    elif violation == Margin.TOP:
                        self.logs[Error.MARGIN] += [
                            "Text on page {} bleeds into the top margin.".format(
                                page + 1
                            )
                        ]
                        bbox = (20, int(word["top"] - 20), 80, int(word["bottom"] + 20))
                        im.draw_rect(bbox, fill=None, stroke="red", stroke_width=5)
                    elif violation == Margin.BOTTOM:
                        self.logs[Error.MARGIN] += [
                            "Text on page {} bleeds into the top margin.".format(
                                page + 1
                            )
                        ]
                        bbox = (20, int(word["top"] - 20), 80, int(word["bottom"] + 20))
                        im.draw_rect(bbox, fill=None, stroke="red", stroke_width=5)

                for image, violation in pages_image[page]:

                    self.logs[Error.MARGIN] += [
                        "An image on page {} bleeds into the margin.".format(page + 1)
                    ]
                    bbox = (image["x0"], image["top"], image["x1"], image["bottom"])
                    im.draw_rect(bbox, fill=None, stroke="red", stroke_width=5)

                png_file_name = "errors-{0}-page-{1}.png".format(
                    *(self.filename, page + 1)
                )
                im.save(os.path.join(output_dir, png_file_name), format="PNG")


def parse_args():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("paper_paths", metavar="file_or_dir", nargs="+", default=[])
    parser.add_argument("-o", "--output_dir", default=".", help="Output directory")
    return parser.parse_args()


def main(args):
    paths = {
        os.path.join(root, file_name)
        for path in args.paper_paths
        for root, _, file_names in os.walk(path)
        for file_name in file_names
    }
    paths.update(args.paper_paths)

    fileset = sorted([p for p in paths if os.path.isfile(p) and p.endswith(".pdf")])

    if not fileset:
        print(f"No PDF files found in {paths}")
    for paper in fileset:
        Formatter().format_check(paper=paper, output_dir=args.output_dir)


if __name__ == "__main__":
    args = parse_args()
    main(args)
