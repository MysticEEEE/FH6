import argparse
from pathlib import Path

from ultralytics import YOLO


def main():
    parser = argparse.ArgumentParser(description="Run YOLO prediction on FH6 car-select draft images.")
    parser.add_argument("--model", default="runs/fh6_car_select/yolo11n_draft/weights/best.pt")
    parser.add_argument("--source", default="datasets/fh6_car_select/images/draft")
    parser.add_argument("--imgsz", type=int, default=960)
    parser.add_argument("--conf", type=float, default=0.25)
    parser.add_argument("--device", default="0")
    parser.add_argument("--project", default="fh6_car_select_predict")
    parser.add_argument("--name", default="draft_check")
    args = parser.parse_args()

    model_path = Path(args.model)
    source = Path(args.source)
    if not model_path.exists():
        raise FileNotFoundError(f"Model not found: {model_path}")
    if not source.exists():
        raise FileNotFoundError(f"Source not found: {source}")

    model = YOLO(str(model_path))
    model.predict(
        source=str(source),
        imgsz=args.imgsz,
        conf=args.conf,
        device=args.device,
        project=args.project,
        name=args.name,
        save=True,
        save_txt=True,
        exist_ok=True,
    )


if __name__ == "__main__":
    main()
