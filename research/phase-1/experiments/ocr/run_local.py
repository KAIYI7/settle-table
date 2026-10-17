"""Disposable CPU OCR runner. No server, upload, application or cloud fallback."""
import argparse
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import time

ROOT = Path(__file__).resolve().parent
os.environ["PADDLE_PDX_CACHE_HOME"] = str(ROOT / "cache/paddlex")
os.environ["PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK"] = "True"
os.environ["HF_HOME"] = str(ROOT / "cache/hf")
os.environ["MODELSCOPE_CACHE"] = str(ROOT / "cache/modelscope")
os.environ["OMP_NUM_THREADS"] = "4"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("engine", choices=["rapidocr", "paddleocr"])
    ap.add_argument("--passes", type=int, default=2)
    args = ap.parse_args()
    import psutil
    t = time.perf_counter()
    if args.engine == "rapidocr":
        from rapidocr import RapidOCR
        engine = RapidOCR(params={"EngineConfig.onnxruntime.intra_op_num_threads": 4,
                                  "EngineConfig.onnxruntime.inter_op_num_threads": 1})
    else:
        from paddleocr import PaddleOCR
        engine = PaddleOCR(device="cpu", enable_mkldnn=False, cpu_threads=4,
                           text_detection_model_name="PP-OCRv5_mobile_det",
                           text_recognition_model_name="en_PP-OCRv5_mobile_rec",
                           use_doc_orientation_classify=False, use_doc_unwarping=False,
                           use_textline_orientation=False)
    init_ms = (time.perf_counter() - t) * 1000
    report = {"engine": args.engine, "init_ms": init_ms, "python": platform.python_version(),
              "cpu_threads": 4, "logical_cpus": os.cpu_count(), "ram_bytes": psutil.virtual_memory().total,
              "init_note": "Process import+constructor with cached models; RapidOCR lazy model init can occur in first predict; not machine-cold disk cache",
              "packages": {p: importlib.metadata.version(p) for p in [args.engine, "numpy", "onnxruntime", "paddlepaddle"]},
              "runs": []}
    images = sorted((ROOT / "data/images").glob("*.jpg")) + sorted((ROOT / "data/images").glob("*.png"))
    out = ROOT / "results" / (args.engine + ".json")
    out.parent.mkdir(exist_ok=True)
    for pass_index in range(args.passes):
        for image in images:
            t = time.perf_counter()
            if args.engine == "rapidocr":
                result = engine(str(image))
                texts, scores, boxes = result.txts or [], result.scores or [], result.boxes if result.boxes is not None else []
            else:
                result = list(engine.predict(str(image)))[0]
                texts, scores, boxes = result["rec_texts"], result["rec_scores"], result["rec_polys"]
            elapsed = (time.perf_counter() - t) * 1000
            lines = [{"text": str(txt), "score": float(score), "box": [[int(x), int(y)] for x, y in box]}
                     for txt, score, box in zip(texts, scores, boxes)]
            run = {"image": image.name, "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
                   "pass": pass_index, "elapsed_ms": elapsed, "rss_bytes_after": psutil.Process().memory_info().rss,
                   "lines": lines}
            report["runs"].append(run)
            out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            print(args.engine, pass_index, image.name, round(elapsed), flush=True)


if __name__ == "__main__":
    main()
