# Deployment Guide (Render)

Render is one of the easiest ways to deploy a Dockerized application for free.

## 1. Create a Render Account
Go to [render.com](https://render.com) and sign up using your GitHub account.

## 2. Create the Web Service
- Click the **New** button in the top right corner and select **Web Service**.
- Connect your GitHub account if it isn't already.
- Find `BernardoBrugg/Drive-Face-Match-Backend` in the list of repositories and click **Connect**.

## 3. Configuration
Fill in the deployment settings:
- **Name:** Choose a name (e.g., `face-recon-drive-api`)
- **Region:** Choose the one closest to you (e.g., US East)
- **Branch:** `main`
- **Runtime:** **Docker** (This is crucial! Don't select Python, select Docker)
- **Instance Type:** Free (if available) or whatever tier you want.

## 4. Advanced Settings (Crucial)
Scroll down and click **Advanced**.
- Change the **Start Command** to: `./start.sh`

### Add Environment Variables:
Click **Add Environment Variable** and add these (match what you have in your local `.env`):
- `GOOGLE_CLIENT_ID` (your client ID)
- `GOOGLE_CLIENT_SECRET` (your secret)
- `GOOGLE_REDIRECT_URI` (your frontend callback URL)
- `ALLOWED_ORIGINS` (your frontend base URL, e.g., `https://my-frontend.vercel.app`)
- *(Do NOT add `REDIS_URL`. The `start.sh` script installs and runs a local Redis server inside the container automatically since you are using a single container).*

## 5. Deploy!
Click **Create Web Service**. 
Render will read the `Dockerfile`, install the C++ libraries for `dlib`, start Redis and the Celery worker, and boot the FastAPI app.

Once the logs say "Application startup complete", copy the URL that Render gives you (e.g., `https://face-recon-drive-api.onrender.com`) and update your frontend's `NEXT_PUBLIC_API_URL` to point to it!
