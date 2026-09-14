FROM python:3.13-slim

WORKDIR /app

# Faqat requirements.txt'ni avval nusxalash — Docker layer cache samaradorligi uchun
# (kod o'zgarganda ham kutubxonalar qayta o'rnatilmaydi, agar requirements o'zgarmasa)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

CMD ["python", "main.py"]