# Carian Kursus PT&K

Aplikasi telefon (PWA) untuk mencari pusat bertauliah JPK bagi kursus PT&K di
Terengganu, Kelantan dan Pahang, menggunakan data MySPIKE.

## Kandungan

| Fail | Fungsi |
|---|---|
| `index.html` | Aplikasi carian (2 medan: nama kursus, negeri) |
| `sw.js`, `manifest.webmanifest`, `icon-*.png` | Membolehkan aplikasi dipasang dan digunakan offline |
| `data.json` | Data yang dicari oleh aplikasi (kini **data contoh**) |
| `collector/kumpul_data.py` | Mengumpul data sebenar daripada MySPIKE |
| `.github/workflows/kemaskini-data.yml` | Menjalankan pengumpul setiap Isnin secara automatik |

## Pemasangan (sekali sahaja)

1. Cipta repositori baharu di GitHub (cth. `carian-ptk`) dan muat naik semua fail ini,
   termasuk folder `.github`.
2. **Settings → Pages**: Source = *Deploy from a branch*, Branch = `main`, folder `/ (root)`.
3. **Settings → Actions → General → Workflow permissions**: pilih *Read and write permissions*.
4. Tab **Actions → Kemas kini data MySPIKE → Run workflow** untuk mengumpul data pertama
   (mengambil masa beberapa minit).
5. Buka `https://<nama-pengguna>.github.io/carian-ptk/` di Chrome telefon →
   menu ⋮ → **Tambah ke skrin utama / Install app**.

Selepas itu data dikemas kini setiap Isnin 4 pagi secara automatik.

## Menjalankan pengumpul di komputer sendiri

```
pip install -r collector/requirements.txt
python collector/kumpul_data.py --output data.json --csv data.csv
```

Gunakan cara ini jika GitHub Actions gagal mencapai MySPIKE (sesetengah laman kerajaan
menyekat alamat IP luar negara). Muat naik `data.json` yang terhasil ke repositori.
`data.csv` boleh digunakan terus sebagai sumber data AppSheet.

## Kod NOSS

Kod program utama ditetapkan dalam `PROGRAM_UTAMA` di `collector/kumpul_data.py`.
Setiap kali dijalankan, pengumpul menyemak Daftar Standard NOSS dan memberi amaran jika
sesuatu kod tidak lagi tersenarai. Jika nama fail PDF Daftar Standard berubah, jalankan:

```
python collector/kumpul_data.py --noss-pdf "<pautan PDF baharu>"
```

atau kemas kini `NOSS_PDF_LALAI` dalam skrip.

Carian di aplikasi berdasarkan nama program, bukan kod, jadi kod NOSS versi baharu
tetap akan dijumpai.

## Mahu fail APK?

Masukkan pautan GitHub Pages ke https://www.pwabuilder.com → *Package for stores* →
Android. Ia menghasilkan APK yang membuka aplikasi yang sama.
