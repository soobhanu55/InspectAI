"""Inference optimisation of the NEU-DET YOLOv8n: ONNX export, INT8 quantisation, and a before/after benchmark.

    python finetune/optimize.py --weights ../backend/vision/weights/neu_det_yolov8n.pt --images DIR/images --labels DIR/labels

Needs the 180 held-out NEU-DET test images with YOLO labels (the set finetune/eval.py scores). They are split once, per class and with a
fixed seed, into 60 calibration images (used only to calibrate INT8) and 120 evaluation images; every variant is scored on the same 120,
so calibration data never leaks into the accuracy numbers. Writes the ONNX files next to the weights and results to docs/ (JSON).

Measures, for every variant: file size, mAP50 and mAP50-95 on the 120, and single-image latency of the network alone (no
pre/post-processing) with ONNX Runtime on CPU at 1 and 4 threads. The PyTorch .pt model is the baseline. All variants are scored with
`rect=False` (every image letterboxed to 224x224), because an ONNX model has a fixed input shape; PyTorch's default rectangular
batching scores higher (0.735 vs 0.688 mAP50 on these 120 images) and is not available to the exported models."""
from __future__ import annotations

import argparse
import json
import random
import shutil
import statistics
import time
from pathlib import Path

import cv2
import numpy as np

IMGSZ = 224
CLASSES = ["crazing", "inclusion", "patches", "pitted_surface", "rolled-in_scale", "scratches"]


def split_images(images: Path, seed: int = 0) -> tuple[list[Path], list[Path]]:
    """60 calibration / 120 evaluation images, 10 / 20 per class (the class is the file-name prefix)."""
    rng, calib, evaluation = random.Random(seed), [], []
    for cls in CLASSES:
        files = sorted(images.glob(f"{cls}_*.jpg"))
        rng.shuffle(files)
        calib += files[:10]
        evaluation += files[10:30]
    return calib, evaluation


def build_eval_dir(files: list[Path], labels: Path, out: Path) -> Path:
    for sub in ("images", "labels"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    for f in files:
        shutil.copy(f, out / "images" / f.name)
        shutil.copy(labels / f"{f.stem}.txt", out / "labels" / f"{f.stem}.txt")
    yaml = out / "data.yaml"
    yaml.write_text(f"path: {out.as_posix()}\ntrain: images\nval: images\nnames:\n" + "".join(f"  {i}: {c}\n" for i, c in enumerate(CLASSES)))
    return yaml


def load(path: Path) -> np.ndarray:
    """Same preprocessing as inference: BGR image -> 224x224 RGB, scaled to 0..1, NCHW float32."""
    img = cv2.resize(cv2.imread(str(path)), (IMGSZ, IMGSZ))
    return np.ascontiguousarray(img[:, :, ::-1].transpose(2, 0, 1)[None], dtype=np.float32) / 255.0


def export_onnx(weights: Path) -> Path:
    from ultralytics import YOLO

    return Path(YOLO(str(weights)).export(format="onnx", imgsz=IMGSZ, opset=17, simplify=False, dynamic=False, batch=1))


class Calibration:
    def __init__(self, files: list[Path], input_name: str):
        self.it, self.name = iter(files), input_name

    def get_next(self):
        f = next(self.it, None)
        return None if f is None else {self.name: load(f)}


def quantize(fp32: Path, out: Path, calib: list[Path], method: str, exclude_head: bool) -> Path:
    import onnx
    from onnxruntime.quantization import CalibrationDataReader, CalibrationMethod, QuantFormat, QuantType, quantize_static

    class Reader(Calibration, CalibrationDataReader):
        pass

    model = onnx.load(str(fp32))
    name = model.graph.input[0].name
    # the last convolutions that produce box and class scores are the most sensitive to rounding: optionally keep them in FP32
    head = [n.name for n in model.graph.node if n.op_type == "Conv" and "/model.22/" in n.name and ("cv2.2" in n.name or "cv3.2" in n.name or "cv2.1" in n.name or "cv3.1" in n.name or "cv2.0" in n.name or "cv3.0" in n.name)] if exclude_head else []
    quantize_static(
        str(fp32), str(out), Reader(calib, name), quant_format=QuantFormat.QDQ, per_channel=True,
        activation_type=QuantType.QUInt8, weight_type=QuantType.QInt8,
        # Conv only: quantising the SiLU's Sigmoid and Mul as well collapses every class score to 0 (measured, see docs)
        op_types_to_quantize=["Conv"],
        calibrate_method={"minmax": CalibrationMethod.MinMax, "percentile": CalibrationMethod.Percentile, "entropy": CalibrationMethod.Entropy}[method],
        nodes_to_exclude=head, extra_options={"ActivationSymmetric": False, "WeightSymmetric": True})
    return out


def bench_cpu(weights: Path, variants: dict[str, Path], files: list[Path], threads: int, rounds: int = 8, runs: int = 100) -> dict:
    """Single-image latency of the network alone on CPU. The variants are timed in alternating rounds, so a laptop's changing clock
    speed hits all of them equally; reported are the median and p95 over all rounds and the median of the best round."""
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    torch.set_num_threads(threads)
    net = YOLO(str(weights)).model.fuse().float().eval()  # fused conv+BN, as in deployment
    xs = [load(f) for f in files[:20]]
    tx = [torch.from_numpy(x) for x in xs]
    fns = {"pytorch_fp32": lambda i: net(tx[i % len(tx)])}
    for name, path in variants.items():
        opts = ort.SessionOptions()
        opts.intra_op_num_threads, opts.inter_op_num_threads = threads, 1
        sess = ort.InferenceSession(str(path), opts, providers=["CPUExecutionProvider"])
        inp = sess.get_inputs()[0].name
        fns[name] = (lambda sess, inp: lambda i: sess.run(None, {inp: xs[i % len(xs)]}))(sess, inp)
    times: dict[str, list[float]] = {n: [] for n in fns}
    round_p50: dict[str, list[float]] = {n: [] for n in fns}
    with torch.inference_mode():
        for fn in fns.values():
            for i in range(30):
                fn(i)  # warm-up
        for _ in range(rounds):
            for name, fn in fns.items():
                ts = []
                for i in range(runs):
                    t = time.perf_counter()
                    fn(i)
                    ts.append((time.perf_counter() - t) * 1000)
                times[name] += ts
                round_p50[name].append(statistics.median(ts))
    out = {}
    for name, ts in times.items():
        ts.sort()
        out[name] = {"p50_ms": round(statistics.median(ts), 2), "p95_ms": round(ts[int(0.95 * len(ts)) - 1], 2), "best_round_p50_ms": round(min(round_p50[name]), 2)}
    return out


def bench_gpu(weights: Path, files: list[Path], half: bool, runs: int = 500) -> dict:
    import torch
    from ultralytics import YOLO

    torch.backends.cudnn.benchmark = True
    net = YOLO(str(weights)).model.fuse().to("cuda").eval()
    net = net.half() if half else net.float()
    xs = [torch.from_numpy(load(f)).to("cuda", torch.float16 if half else torch.float32) for f in files[:20]]
    times = []
    with torch.inference_mode():
        for i in range(50 + runs):
            torch.cuda.synchronize()
            t = time.perf_counter()
            net(xs[i % len(xs)])
            torch.cuda.synchronize()
            if i >= 50:
                times.append((time.perf_counter() - t) * 1000)
    times.sort()
    return {"p50_ms": round(statistics.median(times), 2), "p95_ms": round(times[int(0.95 * runs) - 1], 2)}


def score(model_path: Path, data_yaml: Path) -> dict:
    from ultralytics import YOLO

    m = YOLO(str(model_path), task="detect").val(data=str(data_yaml), imgsz=IMGSZ, batch=1, device="cpu", plots=False, verbose=False, rect=False)
    return {"map50": round(float(m.box.map50), 4), "map50_95": round(float(m.box.map), 4)}


def parity(fp32_pt: Path, onnx_path: Path, files: list[Path]) -> float:
    """Largest absolute difference between the PyTorch and ONNX raw outputs over 20 images."""
    import onnxruntime as ort
    import torch
    from ultralytics import YOLO

    net = YOLO(str(fp32_pt)).model.float().eval()
    sess = ort.InferenceSession(str(onnx_path), providers=["CPUExecutionProvider"])
    name, worst = sess.get_inputs()[0].name, 0.0
    with torch.inference_mode():
        for f in files[:20]:
            x = load(f)
            ref = net(torch.from_numpy(x))
            ref = ref[0] if isinstance(ref, (list, tuple)) else ref
            worst = max(worst, float(np.abs(ref.numpy() - sess.run(None, {name: x})[0]).max()))
    return worst


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--weights", type=Path, required=True)
    ap.add_argument("--images", type=Path, required=True)
    ap.add_argument("--labels", type=Path, required=True)
    ap.add_argument("--work", type=Path, default=Path("opt_work"))
    ap.add_argument("--out", type=Path, default=Path("../docs/inference_optimization.json"))
    ap.add_argument("--bench-only", action="store_true", help="keep the accuracy numbers in --out and redo only the latency measurements")
    a = ap.parse_args()

    calib, evaluation = split_images(a.images)
    if a.bench_only:
        results = json.loads(a.out.read_text())
        weights_dir = a.weights.parent
        variants = {n: weights_dir / f"neu_det_yolov8n{'' if n == 'onnx_fp32' else '_' + n}.onnx" for n in results["variants"] if n.startswith(("onnx", "int8"))}
        for threads in (1, 4):
            for name, r in bench_cpu(a.weights, variants, evaluation, threads).items():
                results["variants"][name][f"cpu_{threads}t"] = r
        a.out.write_text(json.dumps(results, indent=1))
        print(json.dumps(results["variants"], indent=1))
        return
    yaml = build_eval_dir(evaluation, a.labels, a.work / "eval120")
    fp32 = export_onnx(a.weights)
    variants = {"onnx_fp32": fp32}
    for tag, method, head in (("int8_minmax", "minmax", False), ("int8_percentile", "percentile", False), ("int8_percentile_fp32_head", "percentile", True)):  # all Conv-only
        variants[tag] = quantize(fp32, fp32.with_name(f"neu_det_yolov8n_{tag}.onnx"), calib, method, head)

    results: dict = {"calibration_images": len(calib), "evaluation_images": len(evaluation), "variants": {}}
    results["variants"]["pytorch_fp32"] = {"size_mb": round(a.weights.stat().st_size / 1e6, 2), **score(a.weights, yaml)}
    for name, path in variants.items():
        results["variants"][name] = {"size_mb": round(path.stat().st_size / 1e6, 2), **score(path, yaml)}
    results["parity_max_abs_diff_fp32_onnx_vs_pytorch"] = parity(a.weights, fp32, evaluation)
    for threads in (1, 4):
        for name, r in bench_cpu(a.weights, variants, evaluation, threads).items():
            results["variants"][name][f"cpu_{threads}t"] = r
    import torch

    if torch.cuda.is_available():
        results["variants"]["pytorch_fp32"]["gpu"] = bench_gpu(a.weights, evaluation, False)
        results["variants"]["pytorch_fp16"] = {"size_mb": None, "gpu": bench_gpu(a.weights, evaluation, True)}
    a.out.write_text(json.dumps(results, indent=1))
    print(json.dumps(results, indent=1))


if __name__ == "__main__":
    main()
