# How to Run the Braein-AI-GIS Project

This guide explains how to start the three backend services and the frontend application.

## Prerequisites

1.  **Python 3.8+**
2.  **Node.js & npm**
3.  **Virtual Environment**: Ensure you have a virtual environment set up in the `backend` folder.

---

## Step 1: Start Backend Services

All backends should be run from the `backend` directory. Open three separate terminal windows or use the provided automation script.

### 1. Building Detection (UNet)
- **Port**: 8000
- **Command**:
  ```powershell
  cd backend
  # Activate venv if not already active
  .\venv\Scripts\activate
  python unetnew.py
  ```

### 2. Object/Tree Detection (MaskRCNN)
- **Port**: 8001
- **Command**:
  ```powershell
  cd backend
  # Activate venv if not already active
  .\venv\Scripts\activate
  python finalmain.py
  ```

### 3. Super-Resolution (SRGAN)
- **Port**: 8002
- **Command**:
  ```powershell
  cd backend
  # Activate venv if not already active
  .\venv\Scripts\activate
  python super_resolution.py
  ```

---

## Step 2: Start Frontend Application

The frontend is a React application built with Vite.

- **Directory**: `frontend`
- **Command**:
  ```powershell
  cd frontend
  npm install   # Only needed once
  npm run dev
  ```
- **Access**: Typically accessible at `http://localhost:5173`.

---

## Automation: One-Click Startup

A `start_all.bat` file is provided in the root directory. Double-click it to launch all three backends and the frontend in separate terminal windows automatically.

> [!NOTE]
> Ensure your virtual environment is located at `backend\venv`. If it's named differently, you may need to update the `.bat` file or the commands above.
