# wallvision
git init git add . 
git commit -m "Initial WallVision project" 
git branch -M main 
git remote add origin YOUR_GITHUB_REPOSITORY_URL 
git push -u origin main

 # Smart Wall Paint Visualizer website
 What this version includes
🏠 Creative landing page
📷 Room image upload
🎨 10 selectable wall colors
✨ Live wall-color preview
🤖 Smart paint recommendations
💾 Save-design button
📱 Mobile responsive design
🌈 Colorful modern UI
Navigation bar
Feature cards
Before/after-style visualization area

I built the complete WallVision project using:

⚛️ React + Vite frontend
🐍 Flask backend
👁️ OpenCV + NumPy wall detection/color visualization
🐘 PostgreSQL database
🔐 JWT registration/login
🎨 Colorful creative UI
📷 Room image upload
🖌️ Wall color visualization
💾 Save/delete designs
📱 Responsive design
🚫 No paid APIs

# To run it

 1. Create PostgreSQL database

CREATE DATABASE wallvision;

2. Backend

cd backend
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

Copy .env.example → .env and put your PostgreSQL password in it.

Then:

python app.py

3. Frontend

Open another terminal:

cd frontend
npm install
npm run dev

Then open the Vite URL, normally:

http://localhost:5173
