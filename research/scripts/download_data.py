"""
Download and organize fish datasets for training.

Supported sources:
  - Kaggle 'A Large Scale Fish Dataset':  crowww/a-large-scale-fish-dataset
  - Kaggle fish species dataset:          smit15/fish-species
  - iNaturalist open API (research-grade observations, no auth required)
  - Any dataset with <class>/<image> layout

Prerequisites for Kaggle:
  pip install kaggle
  Place ~/.kaggle/kaggle.json (from https://www.kaggle.com/settings → API)
"""

import argparse
import json
import shutil
import time
import urllib.parse
import urllib.request
from pathlib import Path


def download_kaggle(dataset: str, output_dir: str = "data/raw"):
    try:
        import kaggle
    except ImportError:
        print("Install the Kaggle client:  pip install kaggle")
        print("API key setup:  https://www.kaggle.com/docs/api")
        return

    tmp = Path("data/kaggle_tmp")
    tmp.mkdir(parents=True, exist_ok=True)
    print(f"Downloading {dataset} ...")
    kaggle.api.dataset_download_files(dataset, path=str(tmp), unzip=True)
    print(f"Downloaded to {tmp}")
    print(f"Run 'organize {tmp}' to move images into {output_dir}/<class>/ structure.")


def organize(source_dir: str, output_dir: str = "data/raw"):
    """
    Flatten any nested folder structure into:
        output_dir/<class_name>/<image>
    Class names come from the immediate parent directory of each image.
    Folder names with spaces are preserved; the predictor normalizes them.
    """
    src, out = Path(source_dir), Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    count = 0

    for img in src.rglob("*"):
        if img.suffix.lower() not in {".jpg", ".jpeg", ".png", ".webp"}:
            continue
        dest_dir = out / img.parent.name
        dest_dir.mkdir(exist_ok=True)
        shutil.copy2(img, dest_dir / img.name)
        count += 1

    classes = sorted(d.name for d in out.iterdir() if d.is_dir())
    print(f"Organized {count} images into {out}")
    print(f"Classes ({len(classes)}): {classes}")


def stats(data_dir: str = "data/raw"):
    root = Path(data_dir)
    if not root.exists():
        print(f"{data_dir} does not exist.")
        return

    rows = {}
    for cls_dir in sorted(root.iterdir()):
        if cls_dir.is_dir():
            n = sum(1 for p in cls_dir.iterdir() if p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"})
            rows[cls_dir.name] = n

    total = sum(rows.values())
    print(f"\n{data_dir}  —  {total} images  |  {len(rows)} classes\n")
    for cls, n in sorted(rows.items(), key=lambda x: -x[1]):
        bar = "█" * min(40, max(1, n * 40 // max(total, 1)))
        print(f"  {cls:<35s} {n:5d}  {bar}")


# ---------------------------------------------------------------------------
# The 118 freshwater/migratory fish species of Quebec, per the MFFP species
# distribution atlas (Aires de répartition des poissons d'eau douce).
# taxon: scientific name used to query iNaturalist; label: data/raw folder name.
# French/English common names and family live in data/metadata/fish_info.json.
# ---------------------------------------------------------------------------
QC_FRESHWATER_SPECIES = [
    {"taxon": 'Alosa pseudoharengus', "label": 'alewife'},
    {"taxon": 'Lethenteron appendix', "label": 'american_brook_lamprey'},
    {"taxon": 'Anguilla rostrata', "label": 'american_eel'},
    {"taxon": 'Alosa sapidissima', "label": 'american_shad'},
    {"taxon": 'Salvelinus alpinus', "label": 'arctic_char'},
    {"taxon": 'Salmo salar', "label": 'atlantic_salmon'},
    {"taxon": 'Acipenser oxyrinchus', "label": 'atlantic_sturgeon'},
    {"taxon": 'Microgadus tomcod', "label": 'atlantic_tomcod'},
    {"taxon": 'Fundulus diaphanus', "label": 'banded_killifish'},
    {"taxon": 'Notropis heterodon', "label": 'blackchin_shiner'},
    {"taxon": 'Rhinichthys atratulus', "label": 'blacknose_dace'},
    {"taxon": 'Notropis heterolepis', "label": 'blacknose_shiner'},
    {"taxon": 'Gasterosteus wheatlandi', "label": 'blackspotted_stickleback'},
    {"taxon": 'Alosa aestivalis', "label": 'blueback_herring'},
    {"taxon": 'Lepomis macrochirus', "label": 'bluegill'},
    {"taxon": 'Pimephales notatus', "label": 'bluntnose_minnow'},
    {"taxon": 'Amia calva', "label": 'bowfin'},
    {"taxon": 'Hybognathus hankinsoni', "label": 'brassy_minnow'},
    {"taxon": 'Notropis bifrenatus', "label": 'bridle_shiner'},
    {"taxon": 'Labidesthes sicculus', "label": 'brook_silverside'},
    {"taxon": 'Culaea inconstans', "label": 'brook_stickleback'},
    {"taxon": 'Salvelinus fontinalis', "label": 'brook_trout'},
    {"taxon": 'Ameiurus nebulosus', "label": 'brown_bullhead'},
    {"taxon": 'Salmo trutta', "label": 'brown_trout'},
    {"taxon": 'Lota lota', "label": 'burbot'},
    {"taxon": 'Umbra limi', "label": 'central_mudminnow'},
    {"taxon": 'Esox niger', "label": 'chain_pickerel'},
    {"taxon": 'Ictalurus punctatus', "label": 'channel_catfish'},
    {"taxon": 'Percina copelandi', "label": 'channel_darter'},
    {"taxon": 'Ichthyomyzon castaneus', "label": 'chestnut_lamprey'},
    {"taxon": 'Oncorhynchus tshawytscha', "label": 'chinook_salmon'},
    {"taxon": 'Oncorhynchus kisutch', "label": 'coho_salmon'},
    {"taxon": 'Cyprinus carpio', "label": 'common_carp'},
    {"taxon": 'Luxilus cornutus', "label": 'common_shiner'},
    {"taxon": 'Moxostoma hubbsi', "label": 'copper_redhorse'},
    {"taxon": 'Pomoxis nigromaculatus', "label": 'crappie'},
    {"taxon": 'Semotilus atromaculatus', "label": 'creek_chub'},
    {"taxon": 'Exoglossum maxillingua', "label": 'cutlip_minnow'},
    {"taxon": 'Oncorhynchus clarkii', "label": 'cutthroat_trout'},
    {"taxon": 'Myoxocephalus thompsonii', "label": 'deepwater_sculpin'},
    {"taxon": 'Ammocrypta pellucida', "label": 'eastern_sand_darter'},
    {"taxon": 'Hybognathus regius', "label": 'eastern_silvery_minnow'},
    {"taxon": 'Notropis atherinoides', "label": 'emerald_shiner'},
    {"taxon": 'Semotilus corporalis', "label": 'fallfish'},
    {"taxon": 'Etheostoma flabellare', "label": 'fantail_darter'},
    {"taxon": 'Pimephales promelas', "label": 'fathead_minnow'},
    {"taxon": 'Chrosomus neogaeus', "label": 'finescale_dace'},
    {"taxon": 'Myoxocephalus quadricornis', "label": 'fourhorn_sculpin'},
    {"taxon": 'Apeltes quadracus', "label": 'fourspine_stickleback'},
    {"taxon": 'Aplodinotus grunniens', "label": 'freshwater_drum'},
    {"taxon": 'Dorosoma cepedianum', "label": 'gizzard_shad'},
    {"taxon": 'Notemigonus crysoleucas', "label": 'golden_shiner'},
    {"taxon": 'Hiodon alosoides', "label": 'goldeye'},
    {"taxon": 'Carassius auratus', "label": 'goldfish'},
    {"taxon": 'Ctenopharyngodon idella', "label": 'grass_carp'},
    {"taxon": 'Esox americanus vermiculatus', "label": 'grass_pickerel'},
    {"taxon": 'Moxostoma valenciennesi', "label": 'greater_redhorse'},
    {"taxon": 'Lepomis cyanellus', "label": 'green_sunfish'},
    {"taxon": 'Etheostoma exile', "label": 'iowa_darter'},
    {"taxon": 'Etheostoma nigrum', "label": 'johnny_darter'},
    {"taxon": 'Couesius plumbeus', "label": 'lake_chub'},
    {"taxon": 'Coregonus artedi', "label": 'lake_cisco'},
    {"taxon": 'Acipenser fulvescens', "label": 'lake_sturgeon'},
    {"taxon": 'Salvelinus namaycush', "label": 'lake_trout'},
    {"taxon": 'Coregonus clupeaformis', "label": 'lake_whitefish'},
    {"taxon": 'Micropterus salmoides', "label": 'largemouth_bass'},
    {"taxon": 'Percina caprodes', "label": 'logperch'},
    {"taxon": 'Rhinichthys cataractae', "label": 'longnose_dace'},
    {"taxon": 'Lepisosteus osseus', "label": 'longnose_gar'},
    {"taxon": 'Catostomus catostomus', "label": 'longnose_sucker'},
    {"taxon": 'Noturus insignis', "label": 'margined_madtom'},
    {"taxon": 'Notropis volucellus', "label": 'mimic_shiner'},
    {"taxon": 'Hiodon tergisus', "label": 'mooneye'},
    {"taxon": 'Cottus bairdii', "label": 'mottled_sculpin'},
    {"taxon": 'Fundulus heteroclitus', "label": 'mummichog'},
    {"taxon": 'Esox masquinongy', "label": 'muskellunge'},
    {"taxon": 'Pungitius pungitius', "label": 'ninespine_stickleback'},
    {"taxon": 'Ichthyomyzon fossor', "label": 'northern_brook_lamprey'},
    {"taxon": 'Margariscus margarita', "label": 'northern_pearl_dace'},
    {"taxon": 'Esox lucius', "label": 'northern_pike'},
    {"taxon": 'Chrosomus eos', "label": 'northern_redbelly_dace'},
    {"taxon": 'Lepomis peltastes', "label": 'northern_sunfish'},
    {"taxon": 'Lepomis gibbosus', "label": 'pumpkinseed'},
    {"taxon": 'Carpiodes cyprinus', "label": 'quillback'},
    {"taxon": 'Osmerus mordax', "label": 'rainbow_smelt'},
    {"taxon": 'Oncorhynchus mykiss', "label": 'rainbow_trout'},
    {"taxon": 'Esox americanus americanus', "label": 'redfin_pickerel'},
    {"taxon": 'Moxostoma carinatum', "label": 'river_redhorse'},
    {"taxon": 'Ambloplites rupestris', "label": 'rock_bass'},
    {"taxon": 'Notropis rubellus', "label": 'rosyface_shiner'},
    {"taxon": 'Neogobius melanostomus', "label": 'round_goby'},
    {"taxon": 'Prosopium cylindraceum', "label": 'round_whitefish'},
    {"taxon": 'Scardinius erythrophthalmus', "label": 'rudd'},
    {"taxon": 'Notropis stramineus', "label": 'sand_shiner'},
    {"taxon": 'Sander canadensis', "label": 'sauger'},
    {"taxon": 'Petromyzon marinus', "label": 'sea_lamprey'},
    {"taxon": 'Moxostoma macrolepidotum', "label": 'shorthead_redhorse'},
    {"taxon": 'Ichthyomyzon unicuspis', "label": 'silver_lamprey'},
    {"taxon": 'Moxostoma anisurum', "label": 'silver_redhorse'},
    {"taxon": 'Cottus cognatus', "label": 'slimy_sculpin'},
    {"taxon": 'Micropterus dolomieu', "label": 'smallmouth_bass'},
    {"taxon": 'Oncorhynchus nerka', "label": 'sockeye_salmon'},
    {"taxon": 'Cottus ricei', "label": 'spoonhead_sculpin'},
    {"taxon": 'Cyprinella spiloptera', "label": 'spotfin_shiner'},
    {"taxon": 'Notropis hudsonius', "label": 'spottail_shiner'},
    {"taxon": 'Noturus flavus', "label": 'stonecat'},
    {"taxon": 'Morone saxatilis', "label": 'striped_bass'},
    {"taxon": 'Noturus gyrinus', "label": 'tadpole_madtom'},
    {"taxon": 'Tinca tinca', "label": 'tench'},
    {"taxon": 'Etheostoma olmstedi', "label": 'tessellated_darter'},
    {"taxon": 'Gasterosteus aculeatus', "label": 'threespine_stickleback'},
    {"taxon": 'Percopsis omiscomaycus', "label": 'trout_perch'},
    {"taxon": 'Sander vitreus', "label": 'walleye'},
    {"taxon": 'Morone chrysops', "label": 'white_bass'},
    {"taxon": 'Morone americana', "label": 'white_perch'},
    {"taxon": 'Catostomus commersonii', "label": 'white_sucker'},
    {"taxon": 'Ameiurus natalis', "label": 'yellow_bullhead'},
    {"taxon": 'Perca flavescens', "label": 'yellow_perch'},
]


def download_inaturalist(taxon: str, label: str, count: int = 400, output_dir: str = "data/raw"):
    """
    Download research-grade observation photos from iNaturalist (no auth required).
    Photos are saved as data/raw/<label>/inat_<photo_id>.jpg.
    Rate-limited to ~1 req/sec to respect API guidelines.
    """
    dest = Path(output_dir) / label
    dest.mkdir(parents=True, exist_ok=True)

    existing = {p.name for p in dest.glob("inat_*.jpg")}
    needed = count - len(existing)
    if needed <= 0:
        print(f"{label}: {len(existing)} images already present, skipping.")
        return

    print(f"Fetching up to {needed} images for '{label}' (taxon: {taxon}) ...")
    collected = 0
    page = 1

    while collected < needed:
        params = urllib.parse.urlencode({
            "taxon_name": taxon,
            "quality_grade": "research",
            "photos": "true",
            "per_page": 200,
            "page": page,
        })
        req = urllib.request.Request(
            f"https://api.inaturalist.org/v1/observations?{params}",
            headers={"Accept": "application/json", "User-Agent": "OMyFish/1.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read())
        except Exception as exc:
            print(f"  API error on page {page}: {exc}")
            break

        results = data.get("results", [])
        if not results:
            print(f"  No more results after page {page - 1}.")
            break

        for obs in results:
            if collected >= needed:
                break
            for photo in obs.get("photos", [])[:1]:
                url = photo.get("url", "")
                if not url:
                    continue
                # iNaturalist square URLs → medium for better resolution
                url = url.replace("/square.", "/medium.")
                photo_id = str(photo.get("id", ""))
                fname = f"inat_{photo_id}.jpg"
                if fname in existing:
                    continue
                try:
                    urllib.request.urlretrieve(url, dest / fname)
                    existing.add(fname)
                    collected += 1
                    if collected % 50 == 0:
                        print(f"  {label}: {collected}/{needed}")
                except Exception as exc:
                    print(f"  Download failed ({url}): {exc}")

        page += 1
        time.sleep(1.0)

    total = sum(1 for _ in dest.glob("inat_*.jpg"))
    print(f"  {label}: {total} iNaturalist images in {dest}")


def download_qc_freshwater(count: int = 400, output_dir: str = "data/raw"):
    """Download all 118 Quebec freshwater/migratory fish species from iNaturalist."""
    print(f"Downloading {len(QC_FRESHWATER_SPECIES)} Quebec freshwater species ({count} images each) ...\n")
    for sp in QC_FRESHWATER_SPECIES:
        download_inaturalist(sp["taxon"], sp["label"], count=count, output_dir=output_dir)
        print()
    stats(output_dir)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dataset download and organization helpers.")
    sub = parser.add_subparsers(dest="cmd")

    p_dl = sub.add_parser("download", help="Download a Kaggle dataset by slug")
    p_dl.add_argument("dataset", help="e.g. crowww/a-large-scale-fish-dataset")
    p_dl.add_argument("--output", default="data/raw")

    p_org = sub.add_parser("organize", help="Flatten nested folders into class/<image> layout")
    p_org.add_argument("source")
    p_org.add_argument("--output", default="data/raw")

    p_st = sub.add_parser("stats", help="Print per-class image counts")
    p_st.add_argument("--dir", default="data/raw")

    p_inat = sub.add_parser("inaturalist", help="Download research-grade photos from iNaturalist")
    p_inat.add_argument("--taxon",  required=True, help="Scientific name, e.g. 'Micropterus salmoides'")
    p_inat.add_argument("--label",  required=True, help="Output folder name, e.g. largemouth_bass")
    p_inat.add_argument("--count",  type=int, default=400, help="Target image count (default 400)")
    p_inat.add_argument("--output", default="data/raw")

    p_qc = sub.add_parser("download-qc-freshwater", help="Download all 118 Quebec freshwater species from iNaturalist")
    p_qc.add_argument("--count",  type=int, default=400, help="Images per species (default 400)")
    p_qc.add_argument("--output", default="data/raw")

    args = parser.parse_args()
    if args.cmd == "download":
        download_kaggle(args.dataset, args.output)
    elif args.cmd == "organize":
        organize(args.source, args.output)
    elif args.cmd == "stats":
        stats(args.dir)
    elif args.cmd == "inaturalist":
        download_inaturalist(args.taxon, args.label, count=args.count, output_dir=args.output)
    elif args.cmd == "download-qc-freshwater":
        download_qc_freshwater(count=args.count, output_dir=args.output)
    else:
        parser.print_help()
