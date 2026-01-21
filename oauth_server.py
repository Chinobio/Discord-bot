from flask import Flask, request
import os
import json
from google_auth_oauthlib.flow import Flow

app = Flask(__name__)

CLIENT_SECRET_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/gmail.send"]
REDIRECT_URI = "http://YOUR_VM_IP:8000/oauth/callback"

@app.route("/oauth/callback")
def oauth_callback():
    code = request.args.get("code")
    discord_id = request.args.get("state")

    flow = Flow.from_client_secrets_file(
        CLIENT_SECRET_FILE,
        scopes=SCOPES,
        redirect_uri=REDIRECT_URI
    )
    flow.fetch_token(code=code)

    creds = flow.credentials

    os.makedirs("tokens", exist_ok=True)
    with open(f"tokens/{discord_id}.json", "w") as f:
        f.write(creds.to_json())

    return "✅ Gmail 授權成功，你可以回 Discord 使用機器人了"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
