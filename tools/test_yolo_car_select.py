import argparse
import csv
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np
from ultralytics import YOLO


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}
CLASS_NAMES = {
    0: "new_tag",
    1: "class_b600",
    2: "target_car",
}
COLORS = {
    "new_tag": (0, 255, 255),
    "class_b600": (0, 128, 255),
    "target_car": (0, 255, 0),
    "selected": (0, 0, 255),
}


@dataclass
class Box:
    cls_id: int
    name: str
    conf: float
    x1: float
    y1: float
    x2: float
    y2: float

    @property
    def w(self):
        return self.x2 - self.x1

    @property
    def h(self):
        return self.y2 - self.y1

    @property
    def cx(self):
        return (self.x1 + self.x2) / 2

    @property
    def cy(self):
        return (self.y1 + self.y2) / 2

    def xywh_int(self):
        return int(self.x1), int(self.y1), int(self.w), int(self.h)


@dataclass
class Candidate:
    tag: Box
    class_box: Box
    car: Box
    score: float
    reason: str

    @property
    def click(self):
        return int(self.car.cx), int(self.car.cy)


def collect_images(path: Path):
    if path.is_file():
        return [path]
    return sorted(p for p in path.rglob("*") if p.suffix.lower() in IMAGE_SUFFIXES)


def read_image(path: Path):
    data = np.fromfile(str(path), dtype=np.uint8)
    if data.size == 0:
        return None
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def write_image(path: Path, img):
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix, img)
    if not ok:
        raise RuntimeError(f"Cannot encode image: {path}")
    buf.tofile(str(path))


def parse_boxes(result, conf_threshold):
    boxes = []
    if result.boxes is None:
        return boxes
    for item in result.boxes:
        conf = float(item.conf[0])
        if conf < conf_threshold:
            continue
        cls_id = int(item.cls[0])
        name = CLASS_NAMES.get(cls_id, f"class_{cls_id}")
        x1, y1, x2, y2 = [float(v) for v in item.xyxy[0].tolist()]
        boxes.append(Box(cls_id, name, conf, x1, y1, x2, y2))
    return boxes


def distance(a, b):
    return float(np.hypot(a.cx - b.cx, a.cy - b.cy))


def yellow_tag_ratio(img, box):
    x1 = max(0, int(box.x1))
    y1 = max(0, int(box.y1))
    x2 = min(img.shape[1], int(box.x2))
    y2 = min(img.shape[0], int(box.y2))
    roi = img[y1:y2, x1:x2]
    if roi.size == 0:
        return 0.0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    # Real "new" tags are bright yellow; orange rarity bars should not pass this.
    mask = cv2.inRange(hsv, np.array([24, 90, 170]), np.array([42, 255, 255]))
    return float(np.count_nonzero(mask)) / max(1, mask.size)


def find_best_candidate(img, boxes, image_w, image_h, min_tag_yellow_ratio):
    tags = [b for b in boxes if b.name == "new_tag"]
    classes = [b for b in boxes if b.name == "class_b600"]
    cars = [b for b in boxes if b.name == "target_car"]

    candidates = []
    failures = []

    for tag in sorted(tags, key=lambda b: (b.y1, b.x1)):
        if tag.x1 < image_w * 0.20 or tag.y1 < image_h * 0.16 or tag.y1 > image_h * 0.92:
            failures.append(f"tag out of target area conf={tag.conf:.2f}")
            continue
        tag_yellow_ratio = yellow_tag_ratio(img, tag)
        if tag_yellow_ratio < min_tag_yellow_ratio:
            failures.append(f"tag color low conf={tag.conf:.2f} yellow={tag_yellow_ratio:.2f}")
            continue

        near_classes = []
        for cls_box in classes:
            # B600 should be around the lower-left/lower-right area near the new tag.
            dx = cls_box.cx - tag.cx
            dy = cls_box.cy - tag.cy
            if -120 <= dx <= 80 and -12 <= dy <= 80:
                near_classes.append((abs(dx) + abs(dy), cls_box))
        if not near_classes:
            failures.append(f"no B600 near tag conf={tag.conf:.2f}")
            continue
        near_classes.sort(key=lambda item: item[0])
        cls_box = near_classes[0][1]

        near_cars = []
        for car in cars:
            rel_x = tag.cx - car.x1
            rel_y = tag.cy - car.y1
            if car.w <= 0 or car.h <= 0:
                continue
            # Based on the template logic: the new tag should be in the lower-right
            # area of the target card, not on a distant neighbor.
            if 0.58 * car.w <= rel_x <= 1.12 * car.w and 0.50 * car.h <= rel_y <= 1.12 * car.h:
                near_cars.append((distance(tag, car), car))
        if not near_cars:
            failures.append(f"no target_car linked to tag conf={tag.conf:.2f}")
            continue
        near_cars.sort(key=lambda item: item[0])
        car = near_cars[0][1]

        score = tag.conf * 0.34 + cls_box.conf * 0.28 + car.conf * 0.38
        candidates.append(Candidate(tag=tag, class_box=cls_box, car=car, score=score, reason="pass"))

    if not candidates:
        return None, "; ".join(failures[-4:]) if failures else "no candidates"

    candidates.sort(key=lambda c: (-c.score, c.tag.y1, c.tag.x1))
    return candidates[0], "pass"


def draw_boxes(img, boxes, candidate=None, reason=""):
    out = img.copy()
    for b in boxes:
        color = COLORS.get(b.name, (255, 255, 255))
        x1, y1, x2, y2 = [int(v) for v in (b.x1, b.y1, b.x2, b.y2)]
        cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
        cv2.putText(
            out,
            f"{b.name} {b.conf:.2f}",
            (x1, max(18, y1 - 5)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
            cv2.LINE_AA,
        )

    if candidate:
        for b in [candidate.tag, candidate.class_box, candidate.car]:
            x1, y1, x2, y2 = [int(v) for v in (b.x1, b.y1, b.x2, b.y2)]
            cv2.rectangle(out, (x1, y1), (x2, y2), COLORS["selected"], 3)
        click_x, click_y = candidate.click
        cv2.drawMarker(out, (click_x, click_y), COLORS["selected"], cv2.MARKER_CROSS, 30, 2)
        cv2.putText(
            out,
            f"CLICK {click_x},{click_y} score={candidate.score:.2f}",
            (click_x + 8, max(20, click_y - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            COLORS["selected"],
            2,
            cv2.LINE_AA,
        )

    if reason:
        cv2.putText(
            out,
            reason[:130],
            (12, 28),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.65,
            (0, 255, 0) if candidate else (0, 0, 255),
            2,
            cv2.LINE_AA,
        )
    return out


def expected_from_name(path: Path):
    if "_pass" in path.name:
        return "PASS"
    if "_miss" in path.name:
        return "MISS"
    return ""


def main():
    parser = argparse.ArgumentParser(description="Offline YOLO + rule-based FH6 car-select tester.")
    parser.add_argument("--model", required=True, help="Path to YOLO best.pt.")
    parser.add_argument("--input", default="datasets/fh6_car_select/images/draft", help="Image file or directory.")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", default="0")
    parser.add_argument("--output-dir", default="debug/yolo_car_select_test")
    parser.add_argument("--min-tag-yellow-ratio", type=float, default=0.18)
    parser.add_argument("--save-debug", action="store_true")
    parser.add_argument("--csv", default="")
    args = parser.parse_args()

    model_path = Path(args.model)
    input_path = Path(args.input)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not input_path.exists():
        raise FileNotFoundError(f"Input not found: {input_path}")

    model = YOLO(str(model_path))
    images = collect_images(input_path)
    rows = []

    print("image,result,expected,click,detections,reason")
    for image_path in images:
        img = read_image(image_path)
        if img is None:
            row = {
                "image": str(image_path),
                "result": "ERROR",
                "expected": expected_from_name(image_path),
                "click_x": "",
                "click_y": "",
                "new_tag_count": 0,
                "class_b600_count": 0,
                "target_car_count": 0,
                "score": "",
                "reason": "cannot read image",
            }
            rows.append(row)
            continue

        result = model.predict(
            source=img,
            imgsz=args.imgsz,
            conf=args.conf,
            device=args.device,
            verbose=False,
        )[0]
        boxes = parse_boxes(result, args.conf)
        candidate, reason = find_best_candidate(img, boxes, img.shape[1], img.shape[0], args.min_tag_yellow_ratio)
        status = "PASS" if candidate else "MISS"
        expected = expected_from_name(image_path)
        click = "-" if not candidate else f"{candidate.click[0]},{candidate.click[1]}"
        counts = {
            "new_tag": sum(1 for b in boxes if b.name == "new_tag"),
            "class_b600": sum(1 for b in boxes if b.name == "class_b600"),
            "target_car": sum(1 for b in boxes if b.name == "target_car"),
        }
        print(
            f"{image_path.name},{status},{expected},{click},"
            f"new={counts['new_tag']} b600={counts['class_b600']} car={counts['target_car']},{reason}"
        )

        row = {
            "image": str(image_path),
            "result": status,
            "expected": expected,
            "click_x": candidate.click[0] if candidate else "",
            "click_y": candidate.click[1] if candidate else "",
            "new_tag_count": counts["new_tag"],
            "class_b600_count": counts["class_b600"],
            "target_car_count": counts["target_car"],
            "score": f"{candidate.score:.4f}" if candidate else "",
            "reason": reason,
        }
        rows.append(row)

        if args.save_debug:
            sub = "pass" if candidate else "miss"
            out = draw_boxes(img, boxes, candidate, reason)
            out_path = Path(args.output_dir) / sub / f"{image_path.stem}.png"
            write_image(out_path, out)

    if args.csv:
        csv_path = Path(args.csv)
        csv_path.parent.mkdir(parents=True, exist_ok=True)
        with csv_path.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()) if rows else [])
            if rows:
                writer.writeheader()
                writer.writerows(rows)

    if rows:
        expected_rows = [r for r in rows if r["expected"]]
        matched = sum(1 for r in expected_rows if r["result"] == r["expected"])
        print(f"\nsummary: {matched}/{len(expected_rows)} matched expected labels")


if __name__ == "__main__":
    main()
