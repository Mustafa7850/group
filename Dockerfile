FROM python:3.10-slim

WORKDIR /app

# تثبيت المتطلبات
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# نسخ الكود
COPY . .

# تشغيل البوت مباشرة (بدون أي محاولة لتشغيل pyrogram)
CMD ["python", "group.py"]
