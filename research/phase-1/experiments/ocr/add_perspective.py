"""Disposable geometric stress fixture; known synthetic text, never a real photo.

Run after prepare.py. Pixel geometry uses nonmonetary floating-point coefficients;
all receipt money remains copied integer sen. No network or model call.
"""
import copy
import hashlib
import json
from pathlib import Path

import numpy as np
from PIL import Image

ROOT = Path(__file__).resolve().parent
source = Image.open(ROOT / "data/images/synthetic_clear.png").convert("RGB")
w, h = source.size
# Map a full source rectangle into a visibly skewed quadrilateral with margins.
corners = [(90, 50), (30, 810), (1060, 780), (990, 20)]
original = [(0, 0), (0, h), (w, h), (w, 0)]
matrix, target = [], []
for (x, y), (u, v) in zip(corners, original):
    matrix.extend([[x, y, 1, 0, 0, 0, -u*x, -u*y],
                   [0, 0, 0, x, y, 1, -v*x, -v*y]])
    target.extend([u, v])
coefficients = np.linalg.solve(np.array(matrix), np.array(target))
result = source.transform((1100, 860), Image.Transform.PERSPECTIVE,
                          coefficients, Image.Resampling.BICUBIC, fillcolor="white")
name = "synthetic_perspective"
image = ROOT / "data/images" / (name + ".png")
result.save(image)
corpus = json.loads((ROOT / "data/corpus.json").read_text(encoding="utf-8"))
corpus = [entry for entry in corpus if entry["id"] != name]
corpus.append({"id": name, "kind": "synthetic_not_field_evidence",
               "image": image.relative_to(ROOT).as_posix(),
               "sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
               "license": "Project-authored synthetic fixture; font not redistributed",
               "transform": "Pillow output-to-input perspective; full source retained",
               "coefficients": coefficients.tolist()})
truth = json.loads((ROOT / "data/truth.json").read_text(encoding="utf-8"))
truth[name] = copy.deepcopy(truth["synthetic_clear"])
(ROOT / "data/corpus.json").write_text(json.dumps(corpus, indent=2), encoding="utf-8")
(ROOT / "data/truth.json").write_text(json.dumps(truth, indent=2), encoding="utf-8")
print("Added deterministic synthetic perspective case; no new real-receipt evidence.")
