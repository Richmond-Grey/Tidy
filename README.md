# Tidy

Keeps a folder tidy by moving each file into a subfolder named after its type (`report.pdf` → `pdf/report.pdf`), then keeps sorting new files as they arrive.

Written in pure Python; it will later be developed into an app for both mobile and PC.

## Run

```
uv sync
uv run main.py
```

Pick a folder with **Browse…**, press **Start sorting**, and Tidy sorts what's already there and watches for new files until you press **Stop**.
This project was written in pure Python, but will later be developed into an app that can be used on PC, mobile version will be made using Kotlin
