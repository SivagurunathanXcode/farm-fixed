# 🌾 Farm Workers Due Maintenance App

A Flask web application to manage farm workers, track work batches, and maintain payment dues.

## Features
- User registration & login with hashed passwords
- Password reset via OTP (email or console fallback)
- Dashboard with totals (workers, works, expenses, dues)
- Add / Edit / Delete workers
- Create work batches and assign workers
- Track per-worker payments and dues
- Pay workers per-work or pay off total dues
- Clean green glass UI with responsive design

## Tech Stack
- **Backend**: Python 3 + Flask
- **Database**: SQLite (file-based, no setup needed)
- **Frontend**: Jinja2 templates, vanilla CSS + JS

## Setup & Run

```bash
# 1. Navigate to backend folder
cd backend

# 2. Install Flask (if not already installed)
pip install flask

# 3. Run the app
python app.py
```

Then open your browser at: **http://127.0.0.1:5000**

The SQLite database (`farm_workers.db`) is created automatically on first run inside the `backend/` folder.

## Project Structure

```
farm-workers-app-complete/
├── backend/
│   ├── app.py            ← Main Flask application
│   ├── requirements.txt
│   └── farm_workers.db   ← Auto-created on first run
└── frontend/
    ├── templates/
    │   ├── base_public.html
    │   ├── base_dashboard.html
    │   ├── about.html
    │   ├── login.html
    │   ├── register.html
    │   ├── forgot.html
    │   ├── verify.html
    │   ├── reset.html
    │   ├── dashboard.html
    │   ├── workers.html
    │   ├── worker_detail.html
    │   ├── add_worker.html
    │   ├── work.html
    │   ├── work_detail.html
    │   └── add_work.html
    └── static/
        ├── css/style.css
        └── js/script.js
```

## Notes
- The OTP is printed to the server console if email is not configured.
- To enable email OTP, set your Gmail credentials in `app.py` → `send_email_otp()`.
