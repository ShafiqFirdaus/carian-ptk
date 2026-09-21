#!/usr/bin/env python3
"""
Pengumpul data MySPIKE untuk aplikasi Carian Kursus PT&K.

Sumber:
  - Senarai Program Pusat Bertauliah : index.php?r=umum-pb/index-umum-program
  - Senarai Pusat Bertauliah SLaPB    : index.php?r=umum-pb/index-umum
  - Daftar Standard (kod NOSS), PDF   : lampiran/manual/Daftar_Standard_versi_MPKK_Bil_12026.pdf

Hasil: data.json (dibaca oleh aplikasi) dan pilihan CSV.

Penggunaan:
    pip install -r collector/requirements.txt
    python collector/kumpul_data.py --output data.json --csv data.csv
"""

import argparse
import csv
import io
import json
import math
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup

BASE = "https://www.myspike.my/index.php"
R_PROGRAM = "umum-pb/index-umum-program"
R_PUSAT = "umum-pb/index-umum"
LAMAN_UTAMA = "https://www.myspike.my/"
# Digunakan hanya jika pautan terkini tidak dapat dikesan di laman utama
NOSS_PDF_LALAI = "https://www.myspike.my/lampiran/manual/Daftar_Standard_versi_MPKK_Bil_12026.pdf"

NEGERI = ["TERENGGANU", "KELANTAN", "PAHANG"]

PROGRAM_UTAMA = {
    "MP-082-4:2012": "Urut Terapeutik dan Penjagaan",
    "MP-110-3:2011": "Terapi Bekam Angin",
    "Q869-002-4:2016": "Penjagaan Ibu Selepas Bersalin (Mamacare)",
    "Q869-004-4:2017": "Perawatan Ruqyah",
}

# Kata kunci untuk menanda program sebagai berkaitan PT&K
KATA_PTK = [
    "BEKAM", "URUT", "URUTAN", "RUQYAH", "BERSALIN", "MAMACARE", "REFLEKSOLOGI",
    "HERBA", "HERBAL", "AKUPUNKTUR", "PERUBATAN TRADISIONAL", "KOMPLEMENTARI",
    "HOMEOPATI", "NATUROPATI", "KIROPRAKTIK", "SPA",
]
# Padan perkataan penuh sahaja ("URUT" tidak padan "KEJURUTERAAN" atau "JURUTEKNIK")
RE_PTK = re.compile(r"\b(?:" + "|".join(re.escape(k) for k in KATA_PTK) + r")\b")

HEADERS = {"User-Agent": "Mozilla/5.0 (Carian Kursus PT&K; pengumpul data mingguan)"}
MYT = timezone(timedelta(hours=8))


def log(*a):
    print(*a, file=sys.stderr, flush=True)


def norm(teks):
    return re.sub(r"\s+", " ", teks or "").strip()


class Pelayar:
    def __init__(self, delay):
        self.sesi = requests.Session()
        self.delay = delay
        self.kiraan = 0

    def ambil(self, route, params=None):
        p = {"r": route, **(params or {})}
        for cubaan in range(3):
            try:
                resp = self.sesi.get(BASE, params=p, headers=HEADERS, timeout=60)
                resp.raise_for_status()
                self.kiraan += 1
                time.sleep(self.delay)
                return BeautifulSoup(resp.text, "html.parser")
            except requests.RequestException as e:
                if cubaan == 2:
                    raise
                log(f"  ralat ({e}); cuba semula...")
                time.sleep(5 * (cubaan + 1))


def cari_jadual(soup, kata):
    for t in soup.find_all("table"):
        tr = t.find("tr")
        if tr and kata.lower() in tr.get_text(" ").lower():
            return t
    return None


def baca_grid(soup, kata):
    """Pulangkan (baris, saringan, jumlah_rekod)."""
    jadual = cari_jadual(soup, kata)
    if jadual is None:
        return [], {}, 0

    trs = jadual.find_all("tr")
    tajuk = [norm(c.get_text(" ")) for c in trs[0].find_all(["th", "td"])]
    saringan, baris = {}, []

    for tr in trs[1:]:
        sel = tr.find_all(["td", "th"])
        if tr.find(["input", "select"]):
            for i, c in enumerate(sel):
                el = c.find(["input", "select"])
                if el is None or not el.get("name") or i >= len(tajuk):
                    continue
                pilihan = {}
                if el.name == "select":
                    pilihan = {norm(o.get_text()).upper(): o.get("value", "")
                               for o in el.find_all("option")}
                saringan[tajuk[i].lower()] = {"nama": el["name"], "pilihan": pilihan}
            continue
        if len(sel) < len(tajuk) - 1:
            continue  # baris "Tiada keputusan" dan sebagainya
        rekod = {}
        for i, c in enumerate(sel[: len(tajuk)]):
            rekod[tajuk[i]] = norm(c.get_text(" "))
            a = c.find("a", href=True)
            if a:
                rekod[tajuk[i] + "__href"] = a["href"]
        baris.append(rekod)

    m = re.search(r"daripada\s*([\d,]+)", soup.get_text(" "))
    jumlah = int(m.group(1).replace(",", "")) if m else 0
    return baris, saringan, jumlah


def lajur(rekod, kata):
    for k, v in rekod.items():
        if not k.endswith("__href") and kata in k.lower():
            return v
    return ""


def lajur_href(rekod, kata):
    for k, v in rekod.items():
        if k.endswith("__href") and kata in k.lower():
            return v
    return ""


def kutip(pelayar, route, kata, params, label):
    semua, halaman, bil_halaman, pertama_lepas = [], 1, None, None
    while True:
        soup = pelayar.ambil(route, {**params, "page": halaman})
        baris, _, jumlah = baca_grid(soup, kata)
        if not baris:
            break
        # Yii memulangkan halaman terakhir jika nombor halaman melebihi had
        if halaman > 1 and baris[0] == pertama_lepas:
            break
        pertama_lepas = baris[0]
        if bil_halaman is None:
            bil_halaman = math.ceil(jumlah / len(baris)) if jumlah else None
            log(f"  {label}: {jumlah} rekod, {bil_halaman or '?'} halaman")
        semua.extend(baris)
        if bil_halaman and halaman >= bil_halaman:
            break
        halaman += 1
    return semua


def kumpul_ikut_negeri(pelayar, route, kata, nama):
    log(f"\n[{nama}]")
    soup = pelayar.ambil(route)
    _, saringan, _ = baca_grid(soup, kata)
    medan = next((v for k, v in saringan.items() if "negeri" in k), None)

    hasil = []
    if medan and medan["pilihan"]:
        for n in NEGERI:
            nilai = medan["pilihan"].get(n)
            if nilai is None:
                log(f"  AMARAN: pilihan negeri {n} tiada dalam saringan")
                continue
            hasil += kutip(pelayar, route, kata, {medan["nama"]: nilai}, n)
    else:
        log("  Saringan negeri tidak dikesan; imbas semua halaman (lambat).")
        hasil = kutip(pelayar, route, kata, {}, "Semua")

    return [b for b in hasil if lajur(b, "negeri").upper() in NEGERI]


def pisah_kod(teks):
    m = re.match(r"^(.*?)\s*\[([^\]]+)\]\s*$", teks or "")
    return (norm(m.group(1)), norm(m.group(2))) if m else (norm(teks), "")


def cari_pautan_noss():
    """Cari pautan 'Daftar NOSS' terkini pada menu laman utama MySPIKE."""
    from urllib.parse import urljoin
    try:
        resp = requests.get(LAMAN_UTAMA, headers=HEADERS, timeout=60)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
        calon = []
        for a in soup.find_all("a", href=True):
            teks, href = norm(a.get_text(" ")).upper(), a["href"]
            if "DAFTAR NOSS" in teks or "DAFTAR_STANDARD" in href.upper():
                if href.lower().split("?")[0].endswith(".pdf"):
                    calon.append(urljoin(LAMAN_UTAMA, href))
        if calon:
            return calon[0]
        log("  AMARAN: pautan 'Daftar NOSS' tidak ditemui di laman utama MySPIKE.")
    except requests.RequestException as e:
        log(f"  AMARAN: gagal membuka laman utama MySPIKE ({e}).")
    return None


def baca_noss(url):
    """Senarai baris PT&K dalam Daftar Standard dan semakan kod utama."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log("  pypdf tiada; langkau semakan NOSS.")
        return None
    try:
        resp = requests.get(url, headers=HEADERS, timeout=120)
        resp.raise_for_status()
        teks = "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(resp.content)).pages)
    except Exception as e:  # noqa: BLE001
        log(f"  Gagal membaca PDF NOSS: {e}")
        return None

    padat = re.sub(r"\s+", "", teks).upper()
    semakan = {kod: kod.replace(" ", "").upper() in padat for kod in PROGRAM_UTAMA}
    baris_ptk = []
    for b in teks.splitlines():
        b = norm(b)
        if b and RE_PTK.search(b.upper()) and b not in baris_ptk:
            baris_ptk.append(b)
    return {"url": url, "semakan_kod": semakan, "baris_ptk": baris_ptk[:200]}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="data.json")
    ap.add_argument("--csv", help="simpan juga sebagai CSV (cth. untuk AppSheet)")
    ap.add_argument("--noss-pdf", help="paksa pautan PDF tertentu (lalai: kesan sendiri dari MySPIKE)")
    ap.add_argument("--delay", type=float, default=1.0)
    args = ap.parse_args()

    pelayar = Pelayar(args.delay)

    # 1. Maklumat pusat (alamat, telefon, emel)
    pusat = {}
    for b in kumpul_ikut_negeri(pelayar, R_PUSAT, "Kod Pusat", "Senarai Pusat Bertauliah"):
        kod = lajur(b, "kod pusat")
        m = re.search(r"idpb=(\d+)", lajur_href(b, "senarai program"))
        pusat[kod] = {
            "nama": lajur(b, "nama pusat"),
            "alamat": lajur(b, "alamat"),
            "telefon": lajur(b, "telefon"),
            "emel": lajur(b, "email"),
            "idpb": m.group(1) if m else "",
        }

    # 2. Program bertauliah
    program, kunci = [], set()
    for b in kumpul_ikut_negeri(pelayar, R_PROGRAM, "Institusi Latihan", "Senarai Program"):
        institusi, kod_pusat = pisah_kod(lajur(b, "institusi latihan"))
        nama_prog, kod_noss = pisah_kod(lajur(b, "program ditawarkan"))
        rekod = {
            "negeri": lajur(b, "negeri").upper(),
            "kod_pusat": kod_pusat,
            "institusi": institusi,
            "program": nama_prog,
            "kod_noss": kod_noss,
            "kategori": lajur(b, "kategori"),
            "tahap": lajur(b, "tahap"),
            "status": lajur(b, "status"),
        }
        k = (kod_pusat, kod_noss, rekod["kategori"], rekod["tahap"])
        if k in kunci:
            continue
        kunci.add(k)
        p = pusat.get(kod_pusat, {})
        rekod.update({
            "alamat": p.get("alamat", ""),
            "telefon": p.get("telefon", ""),
            "emel": p.get("emel", ""),
            "idpb": p.get("idpb", ""),
            "utama": kod_noss in PROGRAM_UTAMA,
            "ptk": kod_noss in PROGRAM_UTAMA or bool(RE_PTK.search(nama_prog.upper())),
        })
        program.append(rekod)

    if not program:
        log("\nRALAT: tiada program dikumpul. data.json TIDAK dikemas kini.")
        sys.exit(1)

    # 3. Daftar Standard NOSS
    log("\n[Daftar Standard NOSS]")
    url_noss = args.noss_pdf or cari_pautan_noss() or NOSS_PDF_LALAI
    log(f"  PDF: {url_noss}")
    noss = baca_noss(url_noss)
    if noss:
        for kod, ada in noss["semakan_kod"].items():
            if not ada:
                log(f"  AMARAN: {kod} tidak ditemui dalam Daftar Standard terkini")

    program.sort(key=lambda r: (NEGERI.index(r["negeri"]), r["institusi"], r["program"]))
    data = {
        "dikemaskini": datetime.now(MYT).isoformat(timespec="minutes"),
        "sumber": "MySPIKE, Jabatan Pembangunan Kemahiran (JPK)",
        "negeri": NEGERI,
        "program_utama": [{"kod": k, "nama": v} for k, v in PROGRAM_UTAMA.items()],
        "program": program,
        "noss": noss,
    }
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

    if args.csv:
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=list(program[0].keys()))
            w.writeheader()
            w.writerows(program)

    ptk = sum(1 for r in program if r["ptk"])
    log(f"\nSiap: {len(program)} program ({ptk} berkaitan PT&K), "
        f"{len(pusat)} pusat, {pelayar.kiraan} permintaan. -> {args.output}")


if __name__ == "__main__":
    main()
