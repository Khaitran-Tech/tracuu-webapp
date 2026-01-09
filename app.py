import os
import pandas as pd
import aiohttp
import asyncio
from flask import Flask, render_template, request
from bs4 import BeautifulSoup

app = Flask(__name__)

# ===== 1. ĐỌC FILE EXCEL =====
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(BASE_DIR, "info_product_data.xlsx")

df = pd.read_excel(file_path)
df = df.iloc[:, [0, 3]]
df.columns = ["ma_sp", "url"]

# ===== 2. LẤY THÔNG TIN HTML (CÓ RETRY) =====
async def lay_thong_tin_tu_url(session, url):
    for attempt in range(3):  # retry tối đa 3 lần
        try:
            async with session.get(url, timeout=15) as response:
                html = await response.text()
                soup = BeautifulSoup(html, "html.parser")

                # Tên sản phẩm
                ten_tag = soup.select_one("h1.product_title.entry-title")
                ten_sp = ten_tag.get_text(strip=True) if ten_tag else "Không xác định"

                # Tồn kho
                ton_kho_tag = soup.select_one(
                    "div.availability span.electro-stock-availability p"
                )
                ton_kho = ton_kho_tag.get_text(strip=True) if ton_kho_tag else "Không xác định"

                # Giá
                gia_tag = soup.select_one("p.price span.woocommerce-Price-amount bdi")
                gia = gia_tag.get_text(strip=True) if gia_tag else "Không xác định"

                # ===== ẢNH SẢN PHẨM (LAZY LOAD) =====
                anh_sp_tag = soup.select_one("img.wp-post-image")
                if anh_sp_tag:
                    anh_sp_url = (
                        anh_sp_tag.get("data-lazy-src")
                        or anh_sp_tag.get("data-src")
                        or anh_sp_tag.get("src")
                    )
                else:
                    anh_sp_url = None

                # ===== ẢNH BẢN VẼ =====
                anh_bv_tag = soup.select_one("img[src*='banve']")
                anh_bv_url = anh_bv_tag.get("src") if anh_bv_tag else None

                return ten_sp, ton_kho, gia, anh_sp_url, anh_bv_url

        except Exception:
            if attempt < 2:
                await asyncio.sleep(1)  # chờ trước khi retry
            else:
                return "Lỗi", "Lỗi", "Lỗi", None, None

# ===== 3. TRA 1 SẢN PHẨM =====
async def tra_1_san_pham(session, ma, url):
    ten, ton, gia, anh_sp, anh_bv = await lay_thong_tin_tu_url(session, url)
    return {
        "ma": ma,
        "ten": ten,
        "ton_kho": ton,
        "gia": gia,
        "anh_sp": anh_sp,
        "anh_bv": anh_bv
    }

# ===== 4. TRA NHIỀU MÃ (CÓ DELAY) =====
async def tra_cuu_nhieu(ma_list):
    ket_qua = {}

    headers = {
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://vongbicongnghiep.vn/"
    }

    async with aiohttp.ClientSession(headers=headers) as session:
        tasks = []

        for ma in ma_list:
            row = df[df["ma_sp"].astype(str).str.strip().str.upper() == ma.strip().upper()]

            if row.empty:
                ket_qua[ma] = {
                    "ma": ma,
                    "ten": "Không tìm thấy",
                    "ton_kho": "-",
                    "gia": "-",
                    "anh_sp": None,
                    "anh_bv": None
                }
                continue

            url = row.iloc[0]["url"]
            tasks.append(tra_1_san_pham(session, ma, url))

            # ⏱ delay giữa các request
            await asyncio.sleep(0.5)

        results = await asyncio.gather(*tasks)

        for ma, res in zip(
            [m for m in ma_list if m in df["ma_sp"].astype(str).values], results
        ):
            ket_qua[ma] = res

    return [ket_qua[m] for m in ma_list]

# ===== 5. ROUTE FLASK =====
@app.route("/", methods=["GET", "POST"])
def index():
    ket_qua = None

    if request.method == "POST":
        ma_raw = request.form.get("ma_san_pham", "")
        ma_list = [
            m.strip()
            for m in ma_raw.replace("\r", "").replace("\n", ",").split(",")
            if m.strip()
        ]

        if ma_list:
            ket_qua = asyncio.run(tra_cuu_nhieu(ma_list))

    return render_template("index.html", ket_qua=ket_qua)

# ===== 6. CHẠY APP =====
if __name__ == "__main__":
    app.run(debug=True)
