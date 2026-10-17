"""Disposable corpus acquisition. Public SROIE downloads only; no image uploads."""
import hashlib
import json
import pathlib
import urllib.parse
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent
KEYS = ["X51008030563", "X51006828201", "X51008042787", "X51006401977", "X51006647984", "X51006334766"]
DATASET = "jsdnrs/ICDAR2019-SROIE"
EXPECTED_REVISION = "bffe40c26759f3376ec2b3ae9031dbba54cd587c"


def read_json(url):
    with urllib.request.urlopen(url, timeout=60) as response:
        return json.load(response)


def main():
    target = ROOT / "data" / "images"
    target.mkdir(parents=True, exist_ok=True)
    revision = read_json("https://huggingface.co/api/datasets/" + DATASET)["sha"]
    if revision != EXPECTED_REVISION:
        raise RuntimeError("Dataset server revision changed; resolve pinned historical assets explicitly before reacquisition. Existing hashes remain authoritative.")
    records = []
    for key in KEYS:
        query = urllib.parse.urlencode({"dataset": DATASET, "config": "default", "split": "test", "where": '"key" = ' + repr(key), "length": 1})
        row = read_json("https://datasets-server.huggingface.co/filter?" + query)["rows"][0]["row"]
        assert row["key"] == key
        img = target / (key + ".jpg")
        if not img.exists():
            urllib.request.urlretrieve(row["image"]["src"], img)
        record = {"id": key, "kind": "real_historical_malaysian_dining", "image": "data/images/" + img.name,
                  "sha256": hashlib.sha256(img.read_bytes()).hexdigest(), "dataset": DATASET,
                  "dataset_revision": revision, "split": "test", "source_entities": row["entities"],
                  "source_words": row["words"], "source_bboxes": row["bboxes"], "source_image_size": row["image_size"],
                  "rights": "Curator CC-BY-4.0 claim and NOTICE; original download terms not independently verified; research-local/nonredistributed"}
        records.append(record)
        (ROOT / "data" / "corpus.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")
        print(key, img, flush=True)


if __name__ == "__main__":
    main()
