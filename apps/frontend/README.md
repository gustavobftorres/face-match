# Drive Face Match - Frontend

Drive Face Match is a web application that allows you to perform AI-powered facial recognition across your entire Google Drive. You can upload a reference photo of a face, provide a Google Drive folder link, and the system will scan and find all corresponding photos containing that face.

This repository contains the **Frontend** application, built with Next.js, React, Tailwind CSS, and Framer Motion. 

*For the Python/FastAPI backend, see the Backend repository (not included here).*

## ✨ Features

- **Google OAuth Integration**: Securely sign in to authorize access to your Google Drive.
- **Reference Image Upload**: Drag-and-drop file upload for the target face.
- **Real-time Progress Dashboard**: Watch the scan progress live via WebSocket updates.
- **Results Gallery**: Beautifully animated grid displaying all positively matched photos.
- **Image Lightbox**: Detailed view of matched photos with an integrated download option.
- **Internationalization (i18n)**: Automatically detects browser locale, supporting English (`en`) and Brazilian Portuguese (`pt-BR`).
- **Responsive Layout**: Designed for both desktop and mobile devices.

## 🛠️ Tech Stack

- **Framework**: [Next.js](https://nextjs.org/) (App Router)
- **Styling**: [Tailwind CSS](https://tailwindcss.com/)
- **Animations**: [Framer Motion](https://www.framer.com/motion/)
- **Icons**: [Lucide React](https://lucide.dev/)
- **Components/UI**: Custom minimal interface with glassmorphism touches.
- **State Management**: React Hooks (`useState`, `useEffect`, `useRef`).
- **Communication**: HTTP REST fetching and native `WebSocket` API for live scan results.

## 🚀 Getting Started

### Prerequisites

- Node.js `18.x` or later.
- A running instance of the Drive Face Match **Backend**.

### Local Setup

1. **Clone the repository:**
   ```bash
   git clone https://github.com/BernardoBrugg/Drive-Face-Match-Frontend.git
   cd Drive-Face-Match-Frontend
   ```

2. **Install dependencies:**
   ```bash
   npm install
   ```

3. **Configure Environment Variables:**
   Copy the `.env.example` to `.env` and fill in the values pointing to your backend:
   ```bash
   cp .env.example .env
   ```
   *`.env` variables:*
   ```ini
   NEXT_PUBLIC_API_URL=http://localhost:8000
   NEXT_PUBLIC_WS_URL=ws://localhost:8000/api/v1/ws/updates
   NEXT_PUBLIC_OAUTH_CALLBACK_URL=http://localhost:3000/auth/callback
   ```

4. **Run the Development Server:**
   ```bash
   npm run dev
   ```
   Open [http://localhost:3000](http://localhost:3000) in your browser.

## ☁️ Production Deployment (Vercel)

This project is fully configured for seamless deployment on Vercel.

1. **Push** this repository to GitHub.
2. **Import** the project into your Vercel dashboard.
3. Configure the following **Environment Variables** in the Vercel project settings:
   - `NEXT_PUBLIC_API_URL`: The URL of your deployed backend API (e.g., `https://api.yourdomain.com`).
   - `NEXT_PUBLIC_WS_URL`: The WebSocket URL of your backend (e.g., `wss://api.yourdomain.com/api/v1/ws/updates`).
   - `NEXT_PUBLIC_OAUTH_CALLBACK_URL`: The full URL to the frontend callback (e.g., `https://yourdomain.com/auth/callback`).
4. **Deploy!**

### Build Configuration Notes
- `next.config.ts` extends image domains to trust `drive.google.com`, `www.googleapis.com`, and `localhost` to allow rendering of proxied Google Drive images.
- Strict type-checking and linting are bypassed during Vercel builds (`ignoreBuildErrors: true`) to ensure deployments are perfectly streamlined.

## 🔒 Security & Privacy

This application processes photos purely for match confirmation and integrates directly with Google Drive API scopes. It strictly relies on the backend proxy (`/api/v1/drive/image/...`) to safely circumvent active CORS and redirect token blocks when streaming massive photo caches from Google Drive.
