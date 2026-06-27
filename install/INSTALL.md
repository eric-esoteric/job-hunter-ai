# ⚙️ Installation and Setup Guide for Job Hunter AI

Deploying the project is fully optimized and takes just 4 simple steps.

### Step 1. Installing the application on your computer
1. Download the installer `JobHunterAI_Setup.exe` from the **[Releases](../../releases)** section (or build it manually with the `build_exe.py` script).
2. Run the installer and complete the file copying process.
3. At the end of installation, the `extension` folder will open automatically — don't close it, you'll need it in the next step.

### Step 2. Installing the extension in Google Chrome
The extension handles job listing parsing and instant delivery to the local application:
1. Open Google Chrome and navigate to the extensions management page: `chrome://extensions/`.
2. In the top right corner, enable the **"Developer mode"** toggle.
3. In the top left corner, click the **"Load unpacked"** button.
4. In the dialog that opens, navigate to the `extension` folder (from Step 1) and click **"Select Folder"**.
5. On the Chrome toolbar, click the puzzle icon and pin the extension for quick access.

### Step 3. Getting a free Gemini API key
> ⚠️ **Note for users in restricted regions:** Since the engine uses official Google API servers, a VPN may be required to obtain the key and run the application.

1. Go to [Google AI Studio](https://aistudio.google.com/) and sign in with your Google account.
2. Click the **"Get API key"** button in the top left corner.
3. Click **"Create API key"**, then select **"Create API key in new project"**.
4. Copy the long generated token (it starts with `AIzaSy...`).

### Step 4. First launch and setup
1. Launch the **Job Hunter AI** application from the Desktop shortcut.
2. Fill in the three key fields in your profile:
   * **Name and Last Name:** Will be automatically inserted into the final signature of cover letters.
   * **Work Experience and Skills:** Describe your stack in detail — the AI uses these criteria to filter vacancies and generate a relevant response.
   * **License and AI Access:** Paste the API key copied in Step 3.
3. Check the desired work formats (Remote, Office, Hybrid, Russia Location Filter).
4. Click the large green **"START ASSISTANT"** button (status will change to *"Waiting for vacancies..."*).

### How to use:
* Open any job listing page in your browser and click the extension icon.
* The icon will change to a loading status `(...)`, and after processing will show **OK** (or **ERR** if you forgot to start the app or the key is invalid).
* All history, AI filter verdicts, and ready-made custom cover letters are saved in the **"Open approved vacancies (Selected)"** section of the app.

---
[Back to project description](../README.md)
